import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionIcon,
  Alert,
  Anchor,
  Button,
  Group,
  Loader,
  Menu,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { listScans, deleteScan } from '../api/scans';
import { ScanStatusBadge } from '../components/ScanStatusBadge';
import type { Scan, ScanStatus } from '../types';

type FilterKey = 'all' | 'running' | 'finished' | 'aborted' | 'failed';

const FILTER_GROUPS: Record<FilterKey, ScanStatus[] | null> = {
  all: null,
  running: ['CREATED', 'STARTING', 'STARTED', 'RUNNING'],
  finished: ['FINISHED'],
  aborted: ['ABORT-REQUESTED', 'ABORTED'],
  failed: ['ERROR-FAILED'],
};

function matches(scan: Scan, filter: FilterKey): boolean {
  const statuses = FILTER_GROUPS[filter];
  return statuses === null || statuses.includes(scan.status);
}

export function ScanListPage() {
  const [filter, setFilter] = useState<FilterKey>('all');
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['scans'],
    queryFn: listScans,
    refetchInterval: 5_000, // poll while scans may be running
  });

  const deleteMutation = useMutation({
    mutationFn: deleteScan,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scans'] }),
  });

  const openDeleteConfirm = (scan: Scan) =>
    modals.openConfirmModal({
      title: 'Delete scan',
      children: (
        <Text size="sm">
          Delete scan <strong>{scan.name}</strong> (target {scan.target})? This
          cannot be undone.
        </Text>
      ),
      labels: { confirm: 'Delete', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(scan.guid),
    });

  if (query.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }

  if (query.isError) {
    return (
      <Alert color="red" title="Failed to load scans" mt="md">
        {(query.error as Error).message}
        <Group mt="sm">
          <Button size="xs" onClick={() => query.refetch()}>
            Retry
          </Button>
        </Group>
      </Alert>
    );
  }

  const filtered = (query.data ?? []).filter((s) => matches(s, filter));

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Scans</Title>
        <Button component="a" href="/newscan">
          + New Scan
        </Button>
      </Group>

      <SegmentedControl
        data={[
          { label: 'All', value: 'all' },
          { label: 'Running', value: 'running' },
          { label: 'Finished', value: 'finished' },
          { label: 'Aborted', value: 'aborted' },
          { label: 'Failed', value: 'failed' },
        ]}
        value={filter}
        onChange={(v) => setFilter(v as FilterKey)}
      />

      {filtered.length === 0 ? (
        <Text c="dimmed" ta="center" mt="xl">
          No scans{filter === 'all' ? ' yet' : ' match this filter'}.
        </Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Status</Table.Th>
              <Table.Th>Name</Table.Th>
              <Table.Th>Target</Table.Th>
              <Table.Th>Events</Table.Th>
              <Table.Th>Started</Table.Th>
              <Table.Th aria-label="Actions" />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map((scan) => (
              <Table.Tr key={scan.guid} data-testid={`scan-row-${scan.guid}`}>
                <Table.Td>
                  <ScanStatusBadge status={scan.status} />
                </Table.Td>
                <Table.Td>
                  {/* Plain <a>: full-page reload into Mako /scaninfo until that page migrates. */}
                  <Anchor href={`/scaninfo?id=${scan.guid}`}>
                    {scan.name}
                  </Anchor>
                </Table.Td>
                <Table.Td>{scan.target}</Table.Td>
                <Table.Td>{scan.eventCount}</Table.Td>
                <Table.Td>{scan.started}</Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>
                  <Menu shadow="md" width={200}>
                    <Menu.Target>
                      <ActionIcon
                        variant="subtle"
                        aria-label={`Actions for ${scan.name}`}
                      >
                        ⋮
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item
                        component="a"
                        href={`/scaninfo?id=${scan.guid}`}
                      >
                        View
                      </Menu.Item>
                      <Menu.Item
                        component="a"
                        href={`/newscan?clone=${encodeURIComponent(scan.guid)}`}
                      >
                        Clone
                      </Menu.Item>
                      <Menu.Item
                        color="red"
                        onClick={() => openDeleteConfirm(scan)}
                      >
                        Delete
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
