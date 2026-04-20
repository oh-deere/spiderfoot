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
