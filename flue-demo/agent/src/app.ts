// Import telemetry first: it registers the Flue instrumentation before
// any agent runs.
import './telemetry.ts';
import { createProvider, envApiKeyAuth } from '@earendil-works/pi-ai';
import { openAIResponsesApi } from '@earendil-works/pi-ai/api/openai-responses.lazy';
import { openaiProvider } from '@earendil-works/pi-ai/providers/openai';
import { setProvider } from '@flue/runtime';
import { createAgentRouter } from '@flue/runtime/routing';
import { Hono } from 'hono';
import { TripPlanner } from './agents/trip-planner.ts';

// Optional: send OpenAI requests through a gateway or proxy. The model
// catalog (prices, context window) stays the same, so token costs in
// Oodle are still correct.
const openaiBaseUrl = process.env.OPENAI_BASE_URL;
if (openaiBaseUrl) {
  setProvider(
    createProvider({
      id: 'openai',
      baseUrl: openaiBaseUrl,
      auth: { apiKey: envApiKeyAuth('OpenAI API key', ['OPENAI_API_KEY']) },
      models: openaiProvider()
        .getModels()
        .map((model) => ({ ...model, baseUrl: openaiBaseUrl })),
      api: openAIResponsesApi(),
    }),
  );
}

const app = new Hono();
app.get('/health', (c) => c.json({ ok: true }));
app.route('/agents/trip-planner', createAgentRouter(TripPlanner));

export default app;
