import { Badge } from '@mantine/core';
import type { CorrelationRisk } from '../../types';

const RISK_COLORS: Record<CorrelationRisk, string> = {
  INFO: 'blue',
  LOW: 'yellow',
  MEDIUM: 'orange',
  HIGH: 'red',
};

export function CorrelationRiskBadge({ risk }: { risk: CorrelationRisk }) {
  return (
    <Badge color={RISK_COLORS[risk] ?? 'gray'} variant="light">
      {risk}
    </Badge>
  );
}
