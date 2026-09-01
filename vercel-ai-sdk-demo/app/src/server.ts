// Import the instrumentation first: registerTelemetry must run
// before any AI SDK call, or those calls emit nothing.
import { provider } from './instrumentation.ts';

import { createOpenAI } from '@ai-sdk/openai';
import { createServer } from 'node:http';
import { Experimental_Agent as Agent, generateText, stepCountIs, tool } from 'ai';
import { z } from 'zod';

// The knob is deliberately not called OPENAI_BASE_URL: the provider
// package builds a default client from that variable while it is
// being imported, and rejects the empty string Compose passes when
// the variable is unset.
const gateway = process.env.OPENAI_GATEWAY_URL;

const openai = createOpenAI({
  apiKey: process.env.OPENAI_API_KEY!,
  ...(gateway ? { baseURL: gateway } : {}),
});

// `.chat()` selects the Chat Completions API. The provider defaults
// to the Responses API, which OpenAI-compatible gateways do not all
// implement, and this demo is meant to run against any of them.
const model = openai.chat(process.env.MODEL ?? 'gpt-4o-mini');

const CONDITIONS = ['clear', 'cloudy', 'light rain', 'windy'];

const getWeather = tool({
  description: 'Get the current weather for a city.',
  inputSchema: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city,
    tempC: 12 + (city.length % 15),
    conditions: CONDITIONS[city.length % CONDITIONS.length],
  }),
});

const searchAttractions = tool({
  description: 'Find things to do in a city.',
  inputSchema: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city,
    attractions: [
      `${city} old town`,
      `${city} central market`,
      `${city} riverside walk`,
    ],
  }),
});

const travelAgent = new Agent({
  model,
  system:
    'You are a concise travel assistant. Call the tools rather than ' +
    'answering from memory, and keep replies to a few sentences.',
  tools: { getWeather, searchAttractions },
  stopWhen: stepCountIs(5),
});

async function readJson(req: any): Promise<any> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  return JSON.parse(Buffer.concat(chunks).toString() || '{}');
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost');
  const send = (code: number, body: unknown) => {
    res.writeHead(code, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body, null, 2));
  };

  try {
    if (url.pathname === '/health') return send(200, { status: 'ok' });

    // One model call, no tools: the smallest traced unit.
    if (url.pathname === '/generate' && req.method === 'POST') {
      const { prompt } = await readJson(req);
      const { text, usage } = await generateText({
        model,
        system: 'You are a helpful assistant. Answer in one sentence.',
        prompt: prompt ?? 'Say hello.',
      });
      return send(200, { text, usage });
    }

    // Multi-step agent run: model calls and tool executions under
    // one invoke_agent span.
    if (url.pathname === '/agent' && req.method === 'POST') {
      const { message } = await readJson(req);
      const result = await travelAgent.generate({
        prompt: message ?? 'What is the weather in Lisbon?',
      });
      return send(200, { text: result.text, steps: result.steps.length });
    }

    send(404, { error: 'not found' });
  } catch (err) {
    send(500, { error: String(err) });
  }
});

const port = Number(process.env.PORT ?? 8097);
server.listen(port, () => console.log(`listening on :${port}`));

// Flush on shutdown so a stopped container does not drop its spans.
for (const sig of ['SIGTERM', 'SIGINT'] as const) {
  process.on(sig, async () => {
    await provider.forceFlush();
    await provider.shutdown();
    process.exit(0);
  });
}
