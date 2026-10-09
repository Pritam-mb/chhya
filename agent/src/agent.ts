import { Agent } from '@mastra/core/agent';
import { createGroq } from '@ai-sdk/groq';
import { planRoute, bestWindow, getShadows, listPois } from './tools.js';

const groq = createGroq({ apiKey: process.env.GROQ_API_KEY });

export const chhayaAgent = new Agent({
  id: 'chhaya',
  name: 'Chhaya',
  instructions: [
    'You are Chhaya, a shade-aware walking agent for Park Street, Kolkata.',
    'Use plan_route to draw a shaded walking route and always report the sun-minutes',
    'saved versus the shortest path in one friendly sentence. Use best_window when the',
    'user asks when to walk. If a place cannot be resolved, ask the user to clarify',
    'instead of guessing. Never invent distances or sun-minutes.',
  ].join(' '),
  model: groq(process.env.GROQ_MODEL || 'openai/gpt-oss-120b'),
  tools: { planRoute, bestWindow, getShadows, listPois },
});
