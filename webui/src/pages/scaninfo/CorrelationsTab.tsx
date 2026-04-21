import { useState } from 'react';
import { Group, Stack, Text } from '@mantine/core';
import { CorrelationsList } from './CorrelationsList';
import { CorrelationRiskBadge } from './CorrelationRiskBadge';
import { EventList } from './EventList';
import type { CorrelationRow } from '../../types';

export function CorrelationsTab({ id }: { id: string }) {
  const [selected, setSelected] = useState<CorrelationRow | null>(null);

  if (!selected) {
    return <CorrelationsList id={id} onSelect={setSelected} />;
  }

  const headerTitle = (
    <Stack gap={4}>
      <Group gap="xs" align="center">
        <Text fw={600}>{selected.headline}</Text>
        <CorrelationRiskBadge risk={selected.ruleRisk} />
      </Group>
      <Text size="xs" c="dimmed">
        {selected.ruleDescr}
      </Text>
    </Stack>
  );

  return (
    <EventList
      id={id}
      correlationId={selected.id}
      onBack={() => setSelected(null)}
      backLabel="All correlations"
      headerTitle={headerTitle}
      hideViewModeToggle
    />
  );
}
