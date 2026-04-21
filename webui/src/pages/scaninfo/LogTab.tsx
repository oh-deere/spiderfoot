import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { fetchScanLog } from '../../api/scaninfo';
import { isScanRunning } from '../../types';
import type { ScanStatusPayload } from '../../types';

const LOG_LIMIT = 500;

function levelColor(level: string): string {
  switch (level.toUpperCase()) {
    case 'ERROR':
      return 'red';
    case 'WARN':
    case 'WARNING':
      return 'orange';
    case 'INFO':
      return 'blue';
    case 'DEBUG':
      return 'gray';
    default:
      return 'gray';
  }
}

export function LogTab({ id, status }: { id: string; status: ScanStatusPayload }) {
  const query = useQuery({
    queryKey: ['scanlog', id],
    queryFn: () => fetchScanLog(id),
    refetchInterval: () => (isScanRunning(status.status) ? 5_000 : false),
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
      <Alert color="red" title="Failed to load log">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = query.data ?? [];
  const truncated = rows.length >= LOG_LIMIT;

  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          {truncated
            ? `Showing ${rows.length} of many lines — download for the full log.`
            : `${rows.length} log ${rows.length === 1 ? 'entry' : 'entries'}`}
        </Text>
        <Button
          component="a"
          href={`/scanexportlogs?id=${encodeURIComponent(id)}`}
          leftSection={<IconDownload size={14} />}
          variant="light"
        >
          Download logs
        </Button>
      </Group>

      {rows.length === 0 ? (
        <Alert color="gray">No log entries yet.</Alert>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 180 }}>Timestamp</Table.Th>
              <Table.Th style={{ width: 160 }}>Component</Table.Th>
              <Table.Th style={{ width: 80 }}>Level</Table.Th>
              <Table.Th>Message</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r, i) => (
              <Table.Tr key={i}>
                <Table.Td>{new Date(r.generatedMs).toISOString()}</Table.Td>
                <Table.Td>
                  <Text size="xs">{r.component}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge color={levelColor(r.level)} variant="light">
                    {r.level}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" style={{ wordBreak: 'break-word' }}>
                    {r.message}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
