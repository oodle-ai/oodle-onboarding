'use agent';
import { defineTool, useModel, useSubagent, useTool } from '@flue/runtime';
import * as v from 'valibot';

const FORECASTS: Record<string, { conditions: string; highC: number; lowC: number }> = {
  lisbon: { conditions: 'sunny', highC: 24, lowC: 15 },
  tokyo: { conditions: 'light rain', highC: 18, lowC: 12 },
  reykjavik: { conditions: 'windy, snow showers', highC: 2, lowC: -3 },
};

const getWeather = defineTool({
  name: 'get_weather',
  description: 'Get the weather forecast for a city.',
  input: v.object({ city: v.string() }),
  run: async ({ data, log }) => {
    const forecast = FORECASTS[data.city.toLowerCase()];
    if (!forecast) {
      log.warn('no forecast for city', { city: data.city });
      return { output: { city: data.city, error: 'No forecast is available for this city.' } };
    }
    return { output: { city: data.city, ...forecast } };
  },
});

const ACTIVITIES: Record<string, string[]> = {
  lisbon: ['Ride tram 28 through Alfama', 'Watch sunset at Miradouro da Senhora do Monte'],
  tokyo: ['Visit the teamLab Planets museum', 'Eat at a standing sushi bar in Ginza'],
  reykjavik: ['Swim in a geothermal pool', 'Look for the northern lights at Grotta'],
};

const findActivities = defineTool({
  name: 'find_activities',
  description: 'List things to do in a city. Pass the weather conditions to get suitable ideas.',
  input: v.object({ city: v.string(), conditions: v.string() }),
  run: async ({ data }) => ({
    output: {
      city: data.city,
      activities: ACTIVITIES[data.city.toLowerCase()] ?? ['Take a walking tour of the old town'],
    },
  }),
});

// Not exported: a delegate is a capability of TripPlanner, not an
// agent with its own HTTP route.
function PackingAssistant() {
  return 'You write a short packing list (at most five items) for the trip described in the task. Reply with the list only.';
}

export function TripPlanner() {
  useModel(process.env.MODEL ?? 'openai/gpt-4.1-mini');
  useTool(getWeather);
  useTool(findActivities);
  useSubagent({
    name: 'packing',
    description: 'Writes a packing list for one trip. Give it the city and the forecast.',
    agent: PackingAssistant,
  });
  return `You are a trip planner. For each city the user asks about:
1. Call get_weather.
2. Call find_activities with the conditions from the forecast.
3. Delegate a packing list to the packing subagent with the task tool. Give it the city and the full forecast.
Then reply with the forecast, two activities and the packing list. Keep the reply short.`;
}
