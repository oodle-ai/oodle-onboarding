import { defineTool } from 'eve/tools';
import { z } from 'zod';

const CONDITIONS = ['clear', 'cloudy', 'light rain', 'windy'];

export default defineTool({
  description: 'Get the current weather for a city.',
  inputSchema: z.object({
    city: z.string().describe('City name, for example "Lisbon".'),
  }),
  execute: async ({ city }) => ({
    city,
    tempC: 12 + (city.length % 15),
    conditions: CONDITIONS[city.length % CONDITIONS.length],
  }),
});
