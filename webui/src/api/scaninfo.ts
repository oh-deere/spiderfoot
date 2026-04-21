import { ApiError, fetchJson } from './client';
import type {
  ScanStatusPayload,
  ScanSummaryRow,
  ScanOptsPayload,
  ScanLogEntry,
  ScanStatus,
  RiskMatrix,
} from '../types';

type ScanStatusTuple = [string, string, string, string, string, ScanStatus, RiskMatrix];

export async function fetchScanStatus(id: string): Promise<ScanStatusPayload> {
  const result = await fetchJson<ScanStatusTuple | []>(
    `/scanstatus?id=${encodeURIComponent(id)}`,
  );
  if (!Array.isArray(result) || result.length === 0) {
    throw new ApiError(404, `Scan ${id} not found`);
  }
  const [name, target, created, started, ended, status, riskMatrix] = result;
  return { name, target, created, started, ended, status, riskMatrix };
}

type ScanSummaryTuple = [string, string, string, number, number, ScanStatus];

export async function fetchScanSummary(id: string): Promise<ScanSummaryRow[]> {
  const rows = await fetchJson<ScanSummaryTuple[]>(
    `/scansummary?id=${encodeURIComponent(id)}&by=type`,
  );
  return rows.map(([typeId, typeLabel, lastSeen, count, uniqueCount]) => ({
    typeId,
    typeLabel,
    lastSeen,
    count,
    uniqueCount,
  }));
}

export async function fetchScanOpts(id: string): Promise<ScanOptsPayload> {
  return fetchJson<ScanOptsPayload>(`/scanopts?id=${encodeURIComponent(id)}`);
}

type ScanLogTuple = [number, string, string, string, string];
const LOG_LIMIT = 500;

export async function fetchScanLog(
  id: string,
  limit: number = LOG_LIMIT,
): Promise<ScanLogEntry[]> {
  const rows = await fetchJson<ScanLogTuple[]>(
    `/scanlog?id=${encodeURIComponent(id)}&limit=${limit}`,
  );
  return rows.map(([generatedMs, component, level, message]) => ({
    generatedMs,
    component,
    level,
    message,
  }));
}

export async function stopScan(id: string): Promise<void> {
  const body = await fetchJson<string | { error: { message: string } }>(
    `/stopscan?id=${encodeURIComponent(id)}`,
  );
  if (typeof body === 'object' && body && 'error' in body) {
    throw new Error(body.error.message ?? 'Failed to stop scan');
  }
}
