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
import { fetchScanSummary } from '../../api/scaninfo';
import type { ScanSummaryRow } from '../../types';

export function EventTypeList({
  id,
  onSelect,
}: {
  id: string;
  onSelect: (type: ScanSummaryRow) => void;
}) {
  const query = useQuery({
    queryKey: ['scansummary', id],
    queryFn: () => fetchScanSummary(id),
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
      <Alert color="red" title="Failed to load event types">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = (query.data ?? []).slice().sort((a, b) => b.count - a.count);

  if (rows.length === 0) {
    return <Alert color="gray">No events produced yet.</Alert>;
  }

  return (
    <Stack>
      <Title order={3}>Browse by event type</Title>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Event type</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>Count</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>Unique</Table.Th>
            <Table.Th>Last seen</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.typeId}>
              <Table.Td>
                <Anchor
                  component="button"
                  type="button"
                  onClick={() => onSelect(r)}
                >
                  <Stack gap={0} align="flex-start">
                    <Text size="sm" fw={500}>{r.typeLabel}</Text>
                    <Text size="xs" c="dimmed">{r.typeId}</Text>
                  </Stack>
                </Anchor>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>{r.count}</Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>{r.uniqueCount}</Table.Td>
              <Table.Td>{r.lastSeen}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
