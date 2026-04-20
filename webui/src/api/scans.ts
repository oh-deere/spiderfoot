import { fetchJson } from './client';
import { ApiError } from './client';
import type { Scan, ScanStatus, RiskMatrix } from '../types';

export async function listScans(): Promise<Scan[]> {
  const rows = await fetchJson<unknown[][]>('/scanlist');
  return rows.map((r) => {
    if (!Array.isArray(r) || r.length < 9) {
      throw new ApiError(
        0,
        `Malformed /scanlist row (expected >=9 fields, got ${Array.isArray(r) ? r.length : typeof r}): ${JSON.stringify(r).slice(0, 120)}`,
      );
    }
    return {
      guid: r[0] as string,
      name: r[1] as string,
      target: r[2] as string,
      created: r[3] as string,
      started: r[4] as string,
      finished: r[5] as string,
      status: r[6] as ScanStatus,
      eventCount: r[7] as number,
      riskMatrix: r[8] as RiskMatrix,
    };
  });
}

export async function deleteScan(guid: string): Promise<void> {
  // SpiderFoot's CherryPy router exposes /scandelete as GET (see
  // sfwebui.py). Semantic DELETE would require a backend route change;
  // revisit in a later milestone.
  await fetchJson(`/scandelete?id=${encodeURIComponent(guid)}`, {
    method: 'GET',
  });
}
