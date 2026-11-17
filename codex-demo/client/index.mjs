#!/usr/bin/env node
//
// Instrumented Codex app-server client.
// Spawns `codex app-server` over stdio, sends a prompt, streams the
// response, and exports OTel spans for every turn, item, and tool call.
//
// Usage:
//   node index.mjs "Read hello.txt and tell me what it says"
//   CODEX_MODEL=gpt-6-astra node index.mjs "Explain this repo"

import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { randomUUID } from "node:crypto";

import { NodeSDK } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { Resource } from "@opentelemetry/resources";
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from "@opentelemetry/semantic-conventions";
import { trace, context, SpanStatusCode, SpanKind } from "@opentelemetry/api";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";

// ── Config ──────────────────────────────────────────────────
const OTLP_ENDPOINT =
  process.env.OTEL_EXPORTER_OTLP_ENDPOINT || "http://localhost:4318";
const MODEL = process.env.CODEX_MODEL || "gpt-6-astra";
const CWD = process.env.CODEX_CWD || process.cwd();
const SANDBOX = process.env.CODEX_SANDBOX || "read-only";
const PROMPT = process.argv[2];

if (!PROMPT) {
  console.error("Usage: node index.mjs <prompt>");
  process.exit(1);
}

// ── OTel SDK ────────────────────────────────────────────────
const exporter = new OTLPTraceExporter({ url: `${OTLP_ENDPOINT}/v1/traces` });

const sdk = new NodeSDK({
  resource: new Resource({
    [ATTR_SERVICE_NAME]: "codex-app-server-client",
    [ATTR_SERVICE_VERSION]: "0.1.0",
  }),
  spanProcessors: [new BatchSpanProcessor(exporter)],
});
sdk.start();

const tracer = trace.getTracer("codex-client", "0.1.0");

// ── JSON-RPC helpers ────────────────────────────────────────
let nextId = 1;
let proc;

function send(method, params, id) {
  const msg = { jsonrpc: "2.0", method, params };
  if (id !== undefined) msg.id = id;
  proc.stdin.write(JSON.stringify(msg) + "\n");
}

function respond(id, result) {
  proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
}

function request(method, params) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pendingRequests.set(id, { resolve, reject });
    send(method, params, id);
  });
}

const pendingRequests = new Map();

// ── State ───────────────────────────────────────────────────
const spans = new Map();
let sessionSpan = null;
let threadId = null;
let turnId = null;
let agentText = "";
let resolveCompletion = null;

// ── Notification handlers ───────────────────────────────────
const handlers = {
  "turn/started"(params) {
    turnId = params.turn?.id;
    agentText = "";
    const parentSpan = spans.get("thread") || sessionSpan;
    const ctx = parentSpan
      ? trace.setSpan(context.active(), parentSpan)
      : context.active();
    const span = tracer.startSpan(
      "codex.turn",
      {
        kind: SpanKind.CLIENT,
        attributes: {
          "codex.turn.id": turnId,
          "codex.thread.id": threadId,
        },
      },
      ctx
    );
    spans.set(`turn:${turnId}`, span);
  },

  "item/started"(params) {
    const item = params.item || params;
    const itemId = item.id || randomUUID();
    const type = item.type || "unknown";
    const turnSpan = spans.get(`turn:${turnId}`);
    const ctx = turnSpan
      ? trace.setSpan(context.active(), turnSpan)
      : undefined;
    const attrs = {
      "codex.item.id": itemId,
      "codex.item.type": type,
      "codex.turn.id": turnId || "",
      "codex.thread.id": threadId || "",
    };
    if (type === "commandExecution" && item.command)
      attrs["codex.command"] = item.command;
    if (type === "mcpToolCall") {
      attrs["codex.mcp.server"] = item.server || "";
      attrs["codex.mcp.tool"] = item.tool || "";
    }
    if (type === "collabAgentToolCall")
      attrs["codex.collab.tool"] = item.tool || "";
    if (type === "fileChange") {
      const paths = (item.changes || []).map((c) => c.path);
      attrs["codex.file_change.paths"] = paths.join(", ");
    }

    const span = tracer.startSpan(
      `codex.item.${type}`,
      { kind: SpanKind.INTERNAL, attributes: attrs },
      ctx,
    );
    spans.set(`item:${itemId}`, span);
  },

  "item/agentMessage/delta"(params) {
    const delta = params.delta || "";
    agentText += delta;
    process.stdout.write(delta);
  },

  "commandExecution/outputDelta"(params) {
    process.stderr.write(params.delta || "");
  },

  "item/completed"(params) {
    const item = params.item || params;
    const itemId = item.id;
    const span = spans.get(`item:${itemId}`);
    if (!span) return;

    if (item.type === "commandExecution") {
      span.setAttributes({
        "codex.command": item.command || "",
        "codex.command.status": item.status || "",
        "codex.command.exit_code": item.exitCode ?? -1,
        "codex.command.duration_ms": item.durationMs ?? 0,
      });
    }
    if (item.type === "fileChange") {
      const paths = (item.changes || []).map((c) => c.path).join(", ");
      span.setAttribute("codex.file_change.paths", paths);
      span.setAttribute("codex.file_change.status", item.status || "");
    }
    if (item.type === "mcpToolCall") {
      span.setAttributes({
        "codex.mcp.status": item.status || "",
        "codex.mcp.duration_ms": item.durationMs ?? 0,
      });
      if (item.error) span.setAttribute("codex.mcp.error", item.error.message);
    }
    if (item.type === "agentMessage")
      span.setAttribute("codex.message.length", (item.text || "").length);
    if (item.type === "subAgentActivity") {
      span.setAttributes({
        "codex.sub_agent.kind": item.kind || "",
        "codex.sub_agent.path": item.agentPath || "",
        "codex.sub_agent.model": item.model || "",
      });
    }
    if (params.completedAtMs)
      span.setAttribute("codex.item.completed_at_ms", params.completedAtMs);

    const failed =
      item.status === "failed" || item.status === "declined" || !!item.error;
    span.setStatus({
      code: failed ? SpanStatusCode.ERROR : SpanStatusCode.OK,
      message: item.error?.message,
    });
    span.end();
    spans.delete(`item:${itemId}`);
  },

  "thread/tokenUsage/updated"(params) {
    const usage = params.tokenUsage || params;
    const turnSpan = spans.get(`turn:${turnId}`);
    if (turnSpan && usage) {
      if (usage.inputTokens != null)
        turnSpan.setAttribute("codex.tokens.input", usage.inputTokens);
      if (usage.outputTokens != null)
        turnSpan.setAttribute("codex.tokens.output", usage.outputTokens);
      if (usage.totalTokens != null)
        turnSpan.setAttribute("codex.tokens.total", usage.totalTokens);
      if (usage.cachedInputTokens != null)
        turnSpan.setAttribute(
          "codex.tokens.cached_input",
          usage.cachedInputTokens
        );
    }
  },

  "turn/completed"(params) {
    const turn = params.turn || params;
    const status = turn.status || "unknown";
    const tid = turn.id || turnId;
    const span = spans.get(`turn:${tid}`);
    if (span) {
      span.setAttribute("codex.turn.status", status);
      if (turn.durationMs != null)
        span.setAttribute("codex.turn.duration_ms", turn.durationMs);
      if (turn.error)
        span.setAttribute("codex.turn.error", turn.error.message || "");
      span.setStatus({
        code: status === "completed" ? SpanStatusCode.OK : SpanStatusCode.ERROR,
        message: turn.error?.message,
      });
      span.end();
      spans.delete(`turn:${tid}`);
    }
    if (resolveCompletion) resolveCompletion();
  },

  "error"(params) {
    const msg = params?.error?.message || JSON.stringify(params);
    console.error(`\n[error] ${msg}`);
  },
};

// ── Main ────────────────────────────────────────────────────
async function main() {
  sessionSpan = tracer.startSpan("codex.session", {
    kind: SpanKind.CLIENT,
    attributes: {
      "codex.model": MODEL,
      "codex.prompt": PROMPT,
      "codex.cwd": CWD,
      "codex.sandbox": SANDBOX,
    },
  });

  proc = spawn("codex", ["app-server", "--stdio"], {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env },
  });

  proc.stderr.on("data", (chunk) => {
    const line = chunk.toString().trim();
    if (line) console.error(`[codex stderr] ${line}`);
  });

  const rl = createInterface({ input: proc.stdout, crlfDelay: Infinity });

  rl.on("line", (line) => {
    if (!line.trim()) return;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      return;
    }

    // Response to a request we sent
    if ("id" in msg && pendingRequests.has(msg.id)) {
      const { resolve, reject } = pendingRequests.get(msg.id);
      pendingRequests.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message || "RPC error"));
      else resolve(msg.result);
      return;
    }

    // Server-initiated request (approval prompts) — auto-approve for demo
    if ("id" in msg && msg.method) {
      console.error(`[server request] ${msg.method}`);
      respond(msg.id, { decision: "accept" });
      return;
    }

    // Notification (no id)
    if (msg.method && !("id" in msg)) {
      const handler = handlers[msg.method];
      if (handler) handler(msg.params || {});
    }
  });

  proc.on("exit", async (code) => {
    for (const [, span] of spans) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: "process exited" });
      span.end();
    }
    spans.clear();
    if (sessionSpan) {
      sessionSpan.setStatus({ code: SpanStatusCode.OK });
      sessionSpan.end();
    }
    await sdk.shutdown();
    process.exit(code ?? 0);
  });

  // 1. Initialize
  await request("initialize", {
    clientInfo: {
      name: "codex-otel-client",
      title: "Codex OTel Client",
      version: "0.1.0",
    },
    capabilities: { experimentalApi: true },
  });
  send("initialized", {});
  console.error(`[init] Connected to codex app-server`);

  // 2. Start thread
  const threadResult = await request("thread/start", {
    model: MODEL,
    cwd: CWD,
    sandbox: SANDBOX,
    approvalPolicy: "never",
  });
  threadId = threadResult?.thread?.id || threadResult?.threadId;
  if (!threadId) {
    console.error("[error] No threadId in thread/start response:");
    console.error(JSON.stringify(threadResult, null, 2));
    process.exit(1);
  }

  const threadSpan = tracer.startSpan(
    "codex.thread",
    {
      kind: SpanKind.CLIENT,
      attributes: { "codex.thread.id": threadId, "codex.model": MODEL },
    },
    trace.setSpan(context.active(), sessionSpan),
  );
  spans.set("thread", threadSpan);
  console.error(`[thread] ${threadId}`);

  // 3. Start turn with user prompt
  console.error(`[turn] Sending: ${PROMPT}\n`);
  await request("turn/start", {
    threadId,
    input: [{ type: "text", text: PROMPT }],
  });

  // Wait for turn/completed
  await new Promise((resolve) => {
    resolveCompletion = resolve;
  });

  console.log();
  console.error(`[done] Turn complete`);

  // End thread + session spans
  const tSpan = spans.get("thread");
  if (tSpan) {
    tSpan.setStatus({ code: SpanStatusCode.OK });
    tSpan.end();
    spans.delete("thread");
  }
  sessionSpan.setStatus({ code: SpanStatusCode.OK });
  sessionSpan.end();
  sessionSpan = null;

  // Flush and exit
  proc.stdin.end();
  await new Promise((r) => setTimeout(r, 2000));
  await sdk.shutdown();
  process.exit(0);
}

main().catch(async (err) => {
  console.error(err);
  if (sessionSpan) {
    sessionSpan.setStatus({
      code: SpanStatusCode.ERROR,
      message: err.message,
    });
    sessionSpan.end();
  }
  await sdk.shutdown();
  process.exit(1);
});
