'use strict';

const http = require('http');
const { trace } = require('@opentelemetry/api');
const { HumanMessage } = require('@langchain/core/messages');
const { tool } = require('@langchain/core/tools');
const { StateGraph, MessagesAnnotation, START } = require('@langchain/langgraph');
const { ToolNode, toolsCondition } = require('@langchain/langgraph/prebuilt');
const { ChatOpenAI } = require('@langchain/openai');
const { z } = require('zod');

const PORT = Number(process.env.PORT || 8101);
const MODEL = process.env.MODEL || 'gpt-4o-mini';

// --- Tools ---

const WEATHER = {
  tokyo: 'Clear, 22°C',
  paris: 'Cloudy, 18°C',
  'new york': 'Sunny, 25°C',
  london: 'Rainy, 14°C',
  sydney: 'Warm, 28°C',
};

const getWeather = tool(
  async ({ city }) => WEATHER[city.toLowerCase()] || `Mild, 20°C (no data for ${city})`,
  {
    name: 'get_weather',
    description: 'Get current weather for a city (simulated).',
    schema: z.object({ city: z.string() }),
  }
);

const getCurrentTime = tool(async () => new Date().toISOString(), {
  name: 'get_current_time',
  description: 'Get the current UTC time.',
  schema: z.object({}),
});

const TOOLS = [getWeather, getCurrentTime];

// --- Graph: a ReAct loop on StateGraph ---

const llm = new ChatOpenAI({
  model: MODEL,
  temperature: 0,
  configuration: process.env.OPENAI_API_BASE
    ? { baseURL: process.env.OPENAI_API_BASE }
    : undefined,
}).bindTools(TOOLS);

const agent = new StateGraph(MessagesAnnotation)
  .addNode('model', async (state) => ({
    messages: [await llm.invoke(state.messages)],
  }))
  .addNode('tools', new ToolNode(TOOLS))
  .addEdge(START, 'model')
  // toolsCondition routes to "tools" when the last message carries
  // tool calls, and to the end otherwise.
  .addConditionalEdges('model', toolsCondition)
  .addEdge('tools', 'model')
  .compile();

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (url.pathname === '/health') {
    return json(res, 200, { status: 'ok', service: 'langgraph-agent-demo-ts' });
  }
  if (url.pathname === '/chat' && req.method === 'POST') {
    const message = url.searchParams.get('message') || 'What time is it?';
    // Name the agent on the request span so the trace lists under it.
    trace.getActiveSpan()?.setAttributes({
      'gen_ai.operation.name': 'invoke_agent',
      'gen_ai.agent.name': 'weather-agent',
    });
    try {
      const result = await agent.invoke({ messages: [new HumanMessage(message)] });
      return json(res, 200, { reply: result.messages.at(-1).content, model: MODEL });
    } catch (err) {
      return json(res, 500, { error: err.message });
    }
  }
  json(res, 404, { error: 'not found' });
});

server.listen(PORT, () => {
  console.log(`langgraph-agent-demo-ts listening on ${PORT}`);
});
