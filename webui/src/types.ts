export type ScanStatus =
  | 'CREATED'
  | 'STARTING'
  | 'STARTED'
  | 'RUNNING'
  | 'ABORT-REQUESTED'
  | 'ABORTED'
  | 'FINISHED'
  | 'ERROR-FAILED';

export type RiskMatrix = {
  HIGH: number;
  MEDIUM: number;
  LOW: number;
  INFO: number;
};

export type Scan = {
  guid: string;
  name: string;
  target: string;
  created: string;          // formatted date string, e.g. "2026-04-20 14:23:15"
  started: string;          // formatted date string OR literal "Not yet"
  finished: string;         // formatted date string OR literal "Not yet"
  status: ScanStatus;
  eventCount: number;
  riskMatrix: RiskMatrix;
};

export type Module = {
  name: string;
  descr: string;
  api_key: boolean;
};

export type EventType = {
  id: string;
  label: string;
};

export type SelectionMode = 'usecase' | 'type' | 'module';

export type UseCase = 'all' | 'Footprint' | 'Investigate' | 'Passive';

export type SettingValue = number | string | boolean | string[] | number[];

export type ModuleMeta = {
  name: string;
  descr: string;
  cats: string[];
  labels: string[];
  dataSourceWebsite?: string;
  dataSourceDescription?: string;
  apiKeyInstructions?: string[];
};

export type SettingsGroup = {
  key: string;                              // "global" or "module.sfp_foo"
  label: string;                            // "Global" or ModuleMeta.name
  settings: Record<string, SettingValue>;   // flat key -> current value
  descs: Record<string, string>;            // flat key -> description
  meta?: ModuleMeta;                        // present only for module groups
};

export type SettingsPayload = {
  token: number;
  groups: SettingsGroup[];                  // Global first, then modules sorted by name
  settings: Record<string, SettingValue>;   // flat master (for diff + serialize)
};

export type ScanStatusPayload = {
  name: string;
  target: string;
  created: string;
  started: string;
  ended: string;
  status: ScanStatus;
  riskMatrix: RiskMatrix;
};

export type ScanSummaryRow = {
  typeId: string;
  typeLabel: string;
  lastSeen: string;
  count: number;
  uniqueCount: number;
};

export type ScanOptsPayload = {
  meta: string[];
  config: Record<string, unknown>;
  configdesc: Record<string, string>;  // matches backend key (sfwebui.py:815)
};

export type ScanLogEntry = {
  generatedMs: number;
  component: string;
  level: string;
  message: string;
};

export function isScanRunning(status: ScanStatus): boolean {
  return (
    status === 'CREATED' ||
    status === 'STARTING' ||
    status === 'STARTED' ||
    status === 'RUNNING'
  );
}

export type EventRisk = 'NONE' | 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH';

export type CorrelationRisk = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH';

export type CorrelationRow = {
  id: string;
  headline: string;
  collection: string;
  ruleId: string;
  ruleName: string;
  ruleDescr: string;
  ruleRisk: CorrelationRisk;
  eventsCount: number;
};

export type EventViewMode = 'full' | 'unique';

export type GraphNode = {
  id: string;
  label: string;
  isRoot: boolean;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
};

export type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type GraphLayoutMode = 'force' | 'random';
