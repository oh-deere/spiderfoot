import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Card,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { fetchScanSummary } from '../../api/scaninfo';
import { isScanRunning } from '../../types';
import type { ScanStatusPayload } from '../../types';

export function StatusTab({ id, status }: { id: string; status: ScanStatusPayload }) {
  const query = useQuery({
    queryKey: ['scansummary', id],
    queryFn: () => fetchScanSummary(id),
    refetchInterval: () => (isScanRunning(status.status) ? 5_000 : false),
  });

  const totalEvents = useMemo(
    () => (query.data ?? []).reduce((sum, r) => sum + r.count, 0),
    [query.data],
  );

  if (query.isLoading) {
    return (
      <Group justify="center" mt="md">
        <Loader />
      </Group>
    );
  }

  if (query.isError) {
    return (
      <Alert color="red" title="Failed to load summary">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = (query.data ?? []).slice().sort((a, b) => b.count - a.count);

  return (
    <Stack>
      <Card withBorder>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Stat label="Target" value={status.target} />
          <Stat label="Started" value={status.started} />
          <Stat label="Ended" value={status.ended} />
          <Stat label="Total events" value={totalEvents.toString()} />
        </SimpleGrid>
      </Card>

      {rows.length === 0 ? (
        <Alert color="gray">No events produced yet.</Alert>
      ) : (
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
                  <Stack gap={0}>
                    <Text size="sm" fw={500}>{r.typeLabel}</Text>
                    <Text size="xs" c="dimmed">{r.typeId}</Text>
                  </Stack>
                </Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>{r.count}</Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>{r.uniqueCount}</Table.Td>
                <Table.Td>{r.lastSeen}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" fw={500}>{value}</Text>
    </Stack>
  );
}
