import { Badge } from '@mantine/core';
import type { ScanStatus } from '../types';

const STATUS_COLORS: Record<ScanStatus, string> = {
  CREATED: 'gray',
  STARTING: 'blue',
  STARTED: 'blue',
  RUNNING: 'blue',
  'ABORT-REQUESTED': 'orange',
  ABORTED: 'orange',
  FINISHED: 'green',
  'ERROR-FAILED': 'red',
};

export function ScanStatusBadge({ status }: { status: ScanStatus }) {
  return <Badge color={STATUS_COLORS[status] ?? 'gray'}>{status}</Badge>;
}
