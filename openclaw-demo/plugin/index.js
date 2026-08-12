/**
 * OpenClaw plugin that traces agent runs with the Langfuse SDK and exports
 * the spans over OTLP.
 *
 * Every `langfuse.*` attribute on the resulting spans is written by
 * `@langfuse/tracing` itself -- this plugin only decides which observation
 * each OpenClaw hook maps to and hands over the payload OpenClaw already
 * carries:
 *
 *   before_agent_start  -> `openclaw.agent_run` (root observation, type span)
 *   llm_input           -> `openclaw.llm_generation` starts (type generation)
 *   llm_output          -> the generation ends, with usage and the reply
 *   after_tool_call     -> `openclaw.tool_call` (type tool)
 *   agent_end           -> the run observation ends
 *
 * The tracer provider is a plain OTel one with an OTLP exporter, so the spans
 * go to the collector and on to Oodle. Point `LANGFUSE_*` at a Langfuse
 * instance as well and the same spans reach both -- the SDK writes one set of
 * attributes either way.
 */

import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { BatchSpanProcessor, NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from "@opentelemetry/semantic-conventions";
import {
  LangfuseOtelSpanAttributes,
  createTraceAttributes,
  setLangfuseTracerProvider,
  startObservation,
} from "@langfuse/tracing";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const DEFAULT_ENDPOINT = "http://otel-collector:4318";

/**
 * Live observations, keyed by OpenClaw's run id. A run's generation and tool
 * calls are parented to its root observation explicitly rather than through
 * the ambient OTel context: the hooks fire on whatever async context the
 * harness is on, which is not the one the root observation started in.
 */
const runs = new Map();

/**
 * OpenClaw calls `register()` once per load phase, so the provider is built
 * once per process and reused. Two providers would mean two exporters and a
 * duplicate span for every run.
 */
let tracing;

/** Drop undefined values so an absent field is not stored as a null. */
function compact(obj) {
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value !== undefined && value !== null) out[key] = value;
  }
  return out;
}

/**
 * Token counts in the shape Langfuse records them. OpenClaw reports cache
 * reads and writes separately from the input count, which is what makes them
 * worth forwarding: they are usually most of the priced input.
 */
function usageDetails(usage) {
  if (!usage) return undefined;
  const details = compact({
    input: usage.input,
    output: usage.output,
    cache_read_input_tokens: usage.cacheRead,
    cache_creation_input_tokens: usage.cacheWrite,
    total: usage.total,
  });
  return Object.keys(details).length > 0 ? details : undefined;
}

function startTracing(api) {
  if (tracing) return tracing;
  const config = api.pluginConfig ?? {};
  const endpoint =
    config.endpoint ??
    process.env.OTEL_EXPORTER_OTLP_ENDPOINT ??
    DEFAULT_ENDPOINT;
  const serviceName =
    config.serviceName ?? process.env.OTEL_SERVICE_NAME ?? "openclaw";

  const provider = new NodeTracerProvider({
    resource: resourceFromAttributes({
      [ATTR_SERVICE_NAME]: serviceName,
      [ATTR_SERVICE_VERSION]: api.version ?? "0.0.0",
    }),
    spanProcessors: [
      new BatchSpanProcessor(
        new OTLPTraceExporter({ url: `${endpoint}/v1/traces` }),
      ),
    ],
  });

  // Hand the provider to the Langfuse SDK. Everything the SDK records from
  // here on is exported through this provider.
  setLangfuseTracerProvider(provider);
  api.logger.info(`langfuse tracing -> ${endpoint} (service ${serviceName})`);

  // A one-shot `openclaw agent --local` exits as soon as the turn is done,
  // and a run that fails hard never reaches `agent_end`, so the last word on
  // flushing belongs to process exit.
  process.once("beforeExit", async () => {
    for (const [runId, run] of runs) {
      runs.delete(runId);
      run.generation?.end();
      run.span.end();
    }
    await provider.forceFlush().catch(() => {});
  });

  tracing = provider;
  return provider;
}

export default definePluginEntry({
  id: "langfuse-tracer",
  name: "Langfuse Tracer",
  description:
    "Traces OpenClaw agent runs as Langfuse observations and exports them over OTLP.",
  configSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      endpoint: {
        type: "string",
        description: "OTLP HTTP base endpoint, e.g. http://otel-collector:4318",
      },
      serviceName: {
        type: "string",
        description: "service.name on the exported spans",
      },
      environment: {
        type: "string",
        description: "Value for langfuse.environment on every observation",
      },
    },
  },
  register(api) {
    const provider = startTracing(api);
    const environment = api.pluginConfig?.environment;

    /**
     * End the run's root observation and flush.
     *
     * `agent_end` and `llm_output` both fire at the end of a turn and the
     * order is not fixed -- on the embedded harness `agent_end` comes first.
     * Whichever arrives last finishes the run, so the generation is never
     * orphaned and the trace output is never lost.
     */
    const finishRun = async (runId) => {
      const run = runs.get(runId);
      if (!run) return;
      runs.delete(runId);
      run.generation?.end();
      if (run.output !== undefined) {
        run.span.otelSpan.setAttributes(
          createTraceAttributes({ output: run.output }),
        );
        run.span.update({ output: run.output });
      }
      run.span.end();
      // A one-shot `openclaw agent --local` exits as soon as the turn is
      // done, so the batch processor is flushed per run rather than only at
      // shutdown: otherwise the spans die with the process.
      await provider.forceFlush().catch((err) => {
        api.logger.warn(`langfuse span flush failed: ${err}`);
      });
    };

    api.on("before_agent_start", (event, ctx) => {
      const runId = event.runId ?? ctx.runId;
      if (!runId || runs.has(runId)) return;
      api.logger.debug(`agent run started: ${runId}`);

      const span = startObservation(
        "openclaw.agent_run",
        compact({ input: event.prompt, environment }),
        { asType: "span" },
      );

      // Trace-level attributes: the run is the root observation, so these
      // describe the whole trace. `createTraceAttributes` and
      // `LangfuseOtelSpanAttributes` are the SDK's own spellings.
      span.otelSpan.setAttributes(
        compact({
          [LangfuseOtelSpanAttributes.TRACE_NAME]: "OpenClaw agent run",
          [LangfuseOtelSpanAttributes.TRACE_COMPAT_SESSION_ID]:
            ctx.sessionId ?? ctx.sessionKey,
          [LangfuseOtelSpanAttributes.TRACE_TAGS]: JSON.stringify(["openclaw"]),
          [`${LangfuseOtelSpanAttributes.TRACE_METADATA}.agent_id`]: ctx.agentId,
          [`${LangfuseOtelSpanAttributes.TRACE_METADATA}.channel_id`]:
            ctx.channelId,
          [`${LangfuseOtelSpanAttributes.TRACE_METADATA}.trigger`]: ctx.trigger,
          [`${LangfuseOtelSpanAttributes.TRACE_METADATA}.message_provider`]:
            ctx.messageProvider,
          [`${LangfuseOtelSpanAttributes.TRACE_METADATA}.model`]: ctx.modelId,
          [`${LangfuseOtelSpanAttributes.TRACE_METADATA}.provider`]:
            ctx.modelProviderId,
          "openclaw.run.id": runId,
          "openclaw.agent.id": ctx.agentId,
          "openclaw.channel.id": ctx.channelId,
          "openclaw.trigger": ctx.trigger,
        }),
      );
      span.otelSpan.setAttributes(
        createTraceAttributes({ input: event.prompt }),
      );

      runs.set(runId, { span, parent: span.otelSpan.spanContext() });
    });

    // The model call. OpenClaw hands over the whole prompt payload it built,
    // which is what lands in langfuse.observation.input.
    api.on("llm_input", (event) => {
      const run = runs.get(event.runId);
      if (!run) return;
      run.generation = startObservation(
        "openclaw.llm_generation",
        compact({
          model: event.model,
          environment,
          input: compact({
            systemPrompt: event.systemPrompt,
            prompt: event.prompt,
            historyMessages: event.historyMessages,
            imagesCount: event.imagesCount,
          }),
          metadata: compact({ provider: event.provider }),
        }),
        { asType: "generation", parentSpanContext: run.parent },
      );
    });

    api.on("llm_output", async (event) => {
      const run = runs.get(event.runId);
      if (!run) return;
      run.output = compact({
        assistantTexts: event.assistantTexts,
        lastAssistant: event.lastAssistant,
      });
      if (run.generation) {
        run.generation.update(
          compact({
            model: event.resolvedRef ?? event.model,
            usageDetails: usageDetails(event.usage),
            output: run.output,
          }),
        );
        run.generation.end();
        run.generation = undefined;
      }
      if (run.agentEnded) await finishRun(event.runId);
    });

    api.on("after_tool_call", (event, ctx) => {
      const run = runs.get(ctx.runId);
      if (!run) return;
      startObservation(
        "openclaw.tool_call",
        compact({
          environment,
          input: event.params,
          output: event.result,
          level: event.error ? "ERROR" : undefined,
          statusMessage: event.error ? String(event.error) : undefined,
          metadata: compact({ tool: ctx.toolName, toolCallId: ctx.toolCallId }),
        }),
        { asType: "tool", parentSpanContext: run.parent },
      ).end();
    });

    api.on("agent_end", async (event, ctx) => {
      const runId = event.runId ?? ctx.runId;
      const run = runs.get(runId);
      if (!run) return;
      run.agentEnded = true;
      if (!event.success) {
        run.span.update(compact({ level: "ERROR", statusMessage: event.error }));
      }
      // A successful turn still owes us its `llm_output`; let that finish the
      // run so the reply and the token counts make it onto the spans.
      if (!run.generation && (run.output !== undefined || !event.success)) {
        await finishRun(runId);
      }
    });

    api.on("gateway_stop", async () => {
      for (const runId of [...runs.keys()]) await finishRun(runId);
      await provider.shutdown().catch(() => {});
    });
  },
});
