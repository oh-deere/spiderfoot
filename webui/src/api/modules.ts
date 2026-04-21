import { fetchJson } from './client';
import type { Module, EventType } from '../types';

export async function listModules(): Promise<Module[]> {
  const rows = await fetchJson<Module[]>('/modules');
  // Sort client-side for stable display. Server sorts by name already,
  // but we can't rely on that contract.
  return rows.slice().sort((a, b) => a.name.localeCompare(b.name));
}

export async function listEventTypes(): Promise<EventType[]> {
  // /eventtypes returns [[label, id], ...] — map to typed objects.
  const rows = await fetchJson<[string, string][]>('/eventtypes');
  return rows.map(([label, id]) => ({ id, label }));
}
