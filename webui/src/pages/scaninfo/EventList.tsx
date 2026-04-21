import { useMemo, useState } from 'react';
import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Loader,
  Menu,
  SegmentedControl,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { IconDotsVertical, IconDownload } from '@tabler/icons-react';
import {
  fetchScanEvents,
  fetchScanEventsUnique,
  searchScanEvents,
  toggleFalsePositive,
} from '../../api/scaninfo';
import type { ScanEventRow } from '../../api/scaninfo';
import type { EventRisk, EventViewMode } from '../../types';

type EventListProps = {
  id: string;
  onBack: () => void;
  backLabel: string;
  headerTitle: React.ReactNode;
  eventType?: string;      // Browse path — required for unique/search/export scope
  correlationId?: string;  // Correlation path
  hideViewModeToggle?: boolean;
};

const RISK_COLORS: Record<EventRisk, string> = {
  NONE: 'gray',
  INFO: 'blue',
  LOW: 'yellow',
  MEDIUM: 'orange',
  HIGH: 'red',
};

export function EventList({
  id,
  onBack,
  backLabel,
  headerTitle,
  eventType,
  correlationId,
  hideViewModeToggle = false,
}: EventListProps) {
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<EventViewMode>('full');
  const [filterFp, setFilterFp] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);

  const searchActive = Boolean(debouncedSearch.trim()) && Boolean(eventType);

  const queryKey = [
    'events',
    id,
    { eventType, correlationId, viewMode, filterFp, search: debouncedSearch },
  ] as const;

  const query = useQuery({
    queryKey,
    queryFn: () => {
      if (searchActive && eventType) {
        return searchScanEvents({
          id,
          eventType,
          value: debouncedSearch.trim(),
        });
      }
      if (viewMode === 'unique' && eventType) {
        return fetchScanEventsUnique({ id, eventType, filterFp });
      }
      return fetchScanEvents({ id, eventType, correlationId, filterFp });
    },
  });

  const fpMutation = useMutation({
    mutationFn: (row: ScanEventRow) =>
      toggleFalsePositive({ id, resultIds: [row.hash], fp: !row.fp }),
    onSuccess: (_data, row) => {
      notifications.show({
        color: 'green',
        title: row.fp ? 'False-positive flag removed' : 'Marked as false positive',
        message: row.data,
      });
      void queryClient.invalidateQueries({ queryKey: ['events', id] });
    },
  });

  const exportHref = useMemo(() => {
    if (!eventType) return null;
    return (filetype: 'csv' | 'excel') =>
      `/scaneventresultexport?id=${encodeURIComponent(id)}&type=${encodeURIComponent(
        eventType,
      )}&filetype=${filetype}`;
  }, [id, eventType]);

  if (query.isLoading) {
    return (
      <Group justify="center" mt="md">
        <Loader />
      </Group>
    );
  }

  if (query.isError) {
    return (
      <Alert color="red" title="Failed to load events">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = query.data ?? [];

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <Stack gap={4}>
          <Anchor component="button" type="button" onClick={onBack} size="sm">
            ← {backLabel}
          </Anchor>
          <Title order={3}>{headerTitle}</Title>
        </Stack>
        {exportHref && (
          <Menu shadow="md">
            <Menu.Target>
              <Button
                leftSection={<IconDownload size={14} />}
                variant="light"
              >
                Export
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item component="a" href={exportHref('csv')} download>
                Export CSV
              </Menu.Item>
              <Menu.Item component="a" href={exportHref('excel')} download>
                Export Excel
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        )}
      </Group>

      <Group>
        {!hideViewModeToggle && eventType && (
          <SegmentedControl
            value={viewMode}
            onChange={(v) => setViewMode(v as EventViewMode)}
            data={[
              { label: 'Full', value: 'full' },
              { label: 'Unique', value: 'unique' },
            ]}
          />
        )}
        <Switch
          label="Hide false positives"
          checked={filterFp}
          onChange={(e) => setFilterFp(e.currentTarget.checked)}
        />
        {eventType && (
          <TextInput
            placeholder="Find events containing..."
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            style={{ flex: 1 }}
            aria-label="Search events"
          />
        )}
      </Group>

      {fpMutation.isError && (
        <Alert color="red" title="Failed to toggle false-positive">
          {(fpMutation.error as Error).message}
        </Alert>
      )}

      {rows.length === 0 ? (
        <Alert color="gray">No events match the current filters.</Alert>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 160 }}>Last seen</Table.Th>
              <Table.Th>Data</Table.Th>
              <Table.Th>Source data</Table.Th>
              <Table.Th style={{ width: 160 }}>Source module</Table.Th>
              <Table.Th style={{ width: 90 }}>Risk</Table.Th>
              <Table.Th style={{ width: 60 }}>FP</Table.Th>
              <Table.Th style={{ width: 40 }} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row) => (
              <Table.Tr key={row.hash}>
                <Table.Td>
                  <Text size="xs">{row.lastSeen}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" style={{ wordBreak: 'break-word' }}>
                    {row.data}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed" style={{ wordBreak: 'break-word' }}>
                    {row.sourceData}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{row.sourceModule}</Text>
                </Table.Td>
                <Table.Td>
                  {row.risk === 'NONE' ? (
                    <Text size="xs" c="dimmed">—</Text>
                  ) : (
                    <Badge color={RISK_COLORS[row.risk]} variant="light">
                      {row.risk}
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  {row.fp ? (
                    <Text size="xs" c="dimmed">✓</Text>
                  ) : null}
                </Table.Td>
                <Table.Td>
                  <Menu shadow="md">
                    <Menu.Target>
                      <ActionIcon
                        variant="subtle"
                        aria-label={`Actions for ${row.data}`}
                      >
                        <IconDotsVertical size={16} />
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item onClick={() => fpMutation.mutate(row)}>
                        {row.fp ? 'Unmark false positive' : 'Mark false positive'}
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Text size="xs" c="dimmed">
        {rows.length} {rows.length === 1 ? 'event' : 'events'}
      </Text>
    </Stack>
  );
}
