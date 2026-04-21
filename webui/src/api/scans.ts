import { fetchJson, ApiError } from './client';
import type { Scan, ScanStatus, RiskMatrix, SelectionMode, UseCase } from '../types';

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

export type StartScanParams = {
  scanName: string;
  scanTarget: string;
  mode: SelectionMode;
  usecase: UseCase;
  moduleList: string[];
  typeList: string[];
};

export async function startScan(params: StartScanParams): Promise<string> {
  const body = new URLSearchParams();
  body.set('scanname', params.scanName);
  body.set('scantarget', params.scanTarget);
  body.set(
    'modulelist',
    params.mode === 'module' ? params.moduleList.join(',') : '',
  );
  body.set(
    'typelist',
    // Server expects event type ids wrapped as "type_<ID>" — see
    // sfwebui.startscan() which strips the prefix via .replace('type_', '').
    params.mode === 'type' ? params.typeList.map((t) => `type_${t}`).join(',') : '',
  );
  body.set('usecase', params.mode === 'usecase' ? params.usecase : '');

  const result = await fetchJson<[string, string]>('/startscan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!Array.isArray(result) || result.length < 2) {
    throw new Error(`Malformed /startscan response: ${JSON.stringify(result)}`);
  }
  if (result[0] !== 'SUCCESS') {
    throw new Error(result[1] ?? 'Unknown error starting scan');
  }
  return result[1];
}
