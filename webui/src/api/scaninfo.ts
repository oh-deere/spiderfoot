import { ApiError, fetchJson } from './client';
import type {
  ScanStatusPayload,
  ScanSummaryRow,
  ScanOptsPayload,
  ScanLogEntry,
  ScanStatus,
  RiskMatrix,
  EventRisk,
  CorrelationRow,
  CorrelationRisk,
} from '../types';

export type ScanEventRow = {
  hash: string;
  lastSeen: string;
  data: string;
  sourceData: string;
  sourceModule: string;
  sourceEventHash: string;
  sourceModuleHash: string;
  fp: boolean;
  risk: EventRisk;
  eventType: string;
};

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

// /scaneventresults returns an 11-tuple per row; field ordering:
// 0 lastseen, 1 data, 2 source_data, 3 source_module,
// 4 source_event_hash, 5 hash, 6 _lastseen_raw, 7 source_module_hash,
// 8 fp, 9 risk, 10 event_type
type ScanEventTuple = [
  string,
  string,
  string,
  string,
  string,
  string,
  number,
  string,
  number,
  EventRisk,
  string,
];

function mapEventRow(row: ScanEventTuple): ScanEventRow {
  return {
    lastSeen: row[0],
    data: row[1],
    sourceData: row[2],
    sourceModule: row[3],
    sourceEventHash: row[4],
    hash: row[5],
    sourceModuleHash: row[7],
    fp: Boolean(row[8]),
    risk: row[9],
    eventType: row[10],
  };
}

export async function fetchScanEvents(args: {
  id: string;
  eventType?: string;
  correlationId?: string;
  filterFp?: boolean;
}): Promise<ScanEventRow[]> {
  const params = new URLSearchParams({ id: args.id });
  if (args.eventType) params.set('eventType', args.eventType);
  if (args.correlationId) params.set('correlationId', args.correlationId);
  if (args.filterFp !== undefined) {
    params.set('filterfp', args.filterFp ? 'true' : 'false');
  }
  const rows = await fetchJson<ScanEventTuple[]>(
    `/scaneventresults?${params.toString()}`,
  );
  return rows.map(mapEventRow);
}

export async function fetchScanEventsUnique(args: {
  id: string;
  eventType: string;
  filterFp?: boolean;
}): Promise<ScanEventRow[]> {
  const params = new URLSearchParams({
    id: args.id,
    eventType: args.eventType,
  });
  if (args.filterFp !== undefined) {
    params.set('filterfp', args.filterFp ? 'true' : 'false');
  }
  const rows = await fetchJson<ScanEventTuple[]>(
    `/scaneventresultsunique?${params.toString()}`,
  );
  return rows.map(mapEventRow);
}

export async function searchScanEvents(args: {
  id: string;
  eventType: string;
  value: string;
}): Promise<ScanEventRow[]> {
  const params = new URLSearchParams({
    id: args.id,
    eventType: args.eventType,
    value: args.value,
  });
  const rows = await fetchJson<ScanEventTuple[]>(
    `/search?${params.toString()}`,
  );
  return rows.map(mapEventRow);
}

type CorrelationTuple = [
  string,
  string,
  string,
  string,
  string,
  string,
  CorrelationRisk,
  number,
];

export async function fetchCorrelations(id: string): Promise<CorrelationRow[]> {
  const rows = await fetchJson<CorrelationTuple[]>(
    `/scancorrelations?id=${encodeURIComponent(id)}`,
  );
  return rows.map(
    ([id, headline, collection, ruleId, ruleName, ruleDescr, ruleRisk, eventsCount]) => ({
      id,
      headline,
      collection,
      ruleId,
      ruleName,
      ruleDescr,
      ruleRisk,
      eventsCount,
    }),
  );
}

export async function toggleFalsePositive(args: {
  id: string;
  resultIds: string[];
  fp: boolean;
}): Promise<void> {
  const params = new URLSearchParams({
    id: args.id,
    fp: args.fp ? '1' : '0',
    resultids: JSON.stringify(args.resultIds),
  });
  const result = await fetchJson<[string, string?]>(
    `/resultsetfp?${params.toString()}`,
  );
  if (!Array.isArray(result) || result[0] !== 'SUCCESS') {
    throw new Error(result?.[1] ?? 'Failed to toggle false positive flag');
  }
}
