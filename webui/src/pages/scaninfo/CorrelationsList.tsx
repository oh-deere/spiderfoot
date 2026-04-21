import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Anchor,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { fetchCorrelations } from '../../api/scaninfo';
import { CorrelationRiskBadge } from './CorrelationRiskBadge';
import type { CorrelationRow } from '../../types';

export function CorrelationsList({
  id,
  onSelect,
}: {
  id: string;
  onSelect: (row: CorrelationRow) => void;
}) {
  const query = useQuery({
    queryKey: ['scancorrelations', id],
    queryFn: () => fetchCorrelations(id),
  });

  if (query.isLoading) {
    return (
      <Group justify="center" mt="md">
        <Loader />
      </Group>
    );
  }
  if (query.isError) {
    return (
      <Alert color="red" title="Failed to load correlations">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = query.data ?? [];

  if (rows.length === 0) {
    return (
      <Stack>
        <Title order={3}>Triggered correlations</Title>
        <Alert color="gray">No correlations triggered for this scan.</Alert>
      </Stack>
    );
  }

  return (
    <Stack>
      <Title order={3}>Triggered correlations</Title>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th style={{ width: 90 }}>Risk</Table.Th>
            <Table.Th>Headline</Table.Th>
            <Table.Th>Rule</Table.Th>
            <Table.Th style={{ width: 90, textAlign: 'right' }}>Events</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>
                <CorrelationRiskBadge risk={r.ruleRisk} />
              </Table.Td>
              <Table.Td>
                <Anchor
                  component="button"
                  type="button"
                  onClick={() => onSelect(r)}
                >
                  <Text size="sm" fw={500}>{r.headline}</Text>
                </Anchor>
              </Table.Td>
              <Table.Td>
                <Stack gap={0}>
                  <Text size="xs">{r.ruleName}</Text>
                  <Text size="xs" c="dimmed">{r.ruleId}</Text>
                </Stack>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>{r.eventsCount}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
