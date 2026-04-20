export type ScanStatus =
  | 'CREATED'
  | 'STARTING'
  | 'STARTED'
  | 'RUNNING'
  | 'ABORT-REQUESTED'
  | 'ABORTED'
  | 'FINISHED'
  | 'ERROR-FAILED';

export type Scan = {
  guid: string;
  name: string;
  target: string;
  createdAt: number;
  startedAt: number;
  endedAt: number;
  status: ScanStatus;
  eventCount: number;
};
