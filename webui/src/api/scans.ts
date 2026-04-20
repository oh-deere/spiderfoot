import { fetchJson } from './client';
import type { Scan, ScanStatus } from '../types';

export async function listScans(): Promise<Scan[]> {
  const rows = await fetchJson<unknown[][]>('/scanlist');
  return rows.map((r) => ({
    guid: r[0] as string,
    name: r[1] as string,
    target: r[2] as string,
    createdAt: r[3] as number,
    startedAt: r[4] as number,
    endedAt: r[5] as number,
    status: r[6] as ScanStatus,
    eventCount: r[7] as number,
  }));
}

export async function deleteScan(guid: string): Promise<void> {
  await fetchJson(`/scandelete?id=${encodeURIComponent(guid)}`, {
    method: 'GET',  // CherryPy's /scandelete handler accepts GET
  });
}
