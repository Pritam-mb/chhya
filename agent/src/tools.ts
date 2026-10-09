import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const API = process.env.CHHAYA_API_URL ?? 'http://localhost:8000';

async function apiGet(path: string): Promise<any> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

async function apiPost(path: string, body: unknown): Promise<any> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
  return res.json();
}

export const planRoute = createTool({
  id: 'plan_route',
  description:
    'Compute the shortest and the shade-aware walking route with sun-minutes for the Park Street / Camac Street demo area.',
  inputSchema: z.object({
    origin: z.string().describe("Start place name (e.g. home, flurys) or 'lat,lon'"),
    destination: z.string().describe("End place name (e.g. clinic, oxford bookstore) or 'lat,lon'"),
    departTime: z.string().optional().describe('Departure time HH:MM in IST, e.g. 15:00'),
    sunTolerance: z.enum(['low', 'medium', 'high']).optional(),
    speedKmh: z.number().optional(),
  }),
  execute: async (inputData) => {
    const { origin, destination, departTime, sunTolerance, speedKmh } = inputData;
    return apiPost('/route', {
      origin,
      destination,
      depart_time: departTime ?? '15:00',
      sun_tolerance: sunTolerance ?? 'low',
      speed_kmh: speedKmh ?? 3.0,
    });
  },
});

export const bestWindow = createTool({
  id: 'best_window',
  description:
    'Rank the 2-hour daylight walking windows for a date using the TabPFN best-window forecaster.',
  inputSchema: z.object({
    date: z.string().optional().describe('Date YYYY-MM-DD; defaults to today'),
  }),
  execute: async (inputData) => {
    const q = inputData.date ? `?date=${encodeURIComponent(inputData.date)}` : '';
    return apiGet(`/window${q}`);
  },
});

export const getShadows = createTool({
  id: 'get_shadows',
  description: 'Return building shadow polygons (GeoJSON) for a time of day.',
  inputSchema: z.object({
    time: z.string().optional().describe('Time HH:MM in IST, e.g. 15:00'),
  }),
  execute: async (inputData) => {
    const q = inputData.time ? `?time=${encodeURIComponent(inputData.time)}` : '';
    return apiGet(`/shadows${q}`);
  },
});

export const listPois = createTool({
  id: 'list_pois',
  description: 'List the known landmarks and aliases in the demo area.',
  inputSchema: z.object({}),
  execute: async () => apiGet('/pois'),
});
