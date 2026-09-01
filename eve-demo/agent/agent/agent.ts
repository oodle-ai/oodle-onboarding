import { createOpenAI } from '@ai-sdk/openai';
import { defineAgent } from 'eve';

// The knob is deliberately not called OPENAI_BASE_URL: the provider
// package builds a default client from that variable while it is
// being imported, and rejects the empty string Compose passes when
// the variable is unset.
const gateway = process.env.OPENAI_GATEWAY_URL;

const openai = createOpenAI({
  apiKey: process.env.OPENAI_API_KEY!,
  ...(gateway ? { baseURL: gateway } : {}),
});

export default defineAgent({
  // `.chat()` selects the Chat Completions API. The provider
  // defaults to the Responses API, which OpenAI-compatible
  // gateways do not all implement, and this demo is meant to run
  // against any of them.
  model: openai.chat(process.env.MODEL ?? 'gpt-4o-mini'),
  modelContextWindowTokens: 128000,

  // `agent/instrumentation/` is read only behind this flag.
  // Without it the instrumentation files compile and never run.
  experimental: { instrumentationProviders: true },
});
