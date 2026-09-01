import { defineTool } from 'eve/tools';
import { z } from 'zod';

const BY_CITY: Record<string, string[]> = {
  lisbon: ['Belem Tower', 'Alfama', 'Tram 28'],
  paris: ['Louvre', 'Musee d Orsay', 'Canal Saint-Martin'],
  tokyo: ['Meiji Shrine', 'Tsukiji Outer Market', 'Shimokitazawa'],
};

export default defineTool({
  description: 'Find things to do in a city.',
  inputSchema: z.object({
    city: z.string(),
    limit: z.number().int().min(1).max(5).default(3),
  }),
  execute: async ({ city, limit }) => {
    const found = BY_CITY[city.toLowerCase()] ?? [
      `${city} old town`,
      `${city} central market`,
      `${city} riverside walk`,
    ];
    return { city, attractions: found.slice(0, limit) };
  },
});
