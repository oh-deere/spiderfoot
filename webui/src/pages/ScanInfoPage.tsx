import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Anchor,
  Breadcrumbs,
  Button,
  Group,
  Loader,
  Stack,
  Tabs,
  Title,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { useSearchParams } from 'react-router-dom';
import { fetchScanStatus, stopScan } from '../api/scaninfo';
import { ScanStatusBadge } from '../components/ScanStatusBadge';
import { ApiError } from '../api/client';
import { isScanRunning } from '../types';
import { PlaceholderTab } from './scaninfo/PlaceholderTab';
import { StatusTab } from './scaninfo/StatusTab';
import { InfoTab } from './scaninfo/InfoTab';
import { LogTab } from './scaninfo/LogTab';
import { BrowseTab } from './scaninfo/BrowseTab';
import { CorrelationsTab } from './scaninfo/CorrelationsTab';

type TabKey =
  | 'status'
  | 'correlations'
  | 'browse'
  | 'graph'
  | 'info'
  | 'log';

export function ScanInfoPage() {
  const [params] = useSearchParams();
  const id = params.get('id') ?? '';
  const [activeTab, setActiveTab] = useState<TabKey>('status');
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ['scanstatus', id],
    queryFn: () => fetchScanStatus(id),
    enabled: id.length > 0,
    refetchInterval: (query) =>
      query.state.data && isScanRunning(query.state.data.status) ? 5_000 : false,
  });

  const abortMutation = useMutation({
    mutationFn: () => stopScan(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scanstatus', id] });
    },
  });

  if (!id) {
    return (
      <Alert color="red" title="Missing scan id" mt="md">
        The scan-detail URL requires an <code>?id=&lt;guid&gt;</code> query
        parameter. <Anchor href="/">Back to scan list</Anchor>.
      </Alert>
    );
  }

  if (statusQuery.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }

  if (statusQuery.isError) {
    const err = statusQuery.error;
    const is404 = err instanceof ApiError && err.status === 404;
    return (
      <Alert color="red" title={is404 ? 'Scan not found' : 'Failed to load scan'} mt="md">
        {is404
          ? `No scan with id "${id}" exists.`
          : (err as Error).message ?? 'Unknown error'}
        <Group mt="sm">
          <Button size="xs" component="a" href="/">
            Back to scan list
          </Button>
        </Group>
      </Alert>
    );
  }

  const status = statusQuery.data!;
  const running = isScanRunning(status.status);

  const openAbortConfirm = () =>
    modals.openConfirmModal({
      title: 'Abort scan?',
      children: `This aborts "${status.name}" — running modules stop and the scan is marked ABORTED.`,
      labels: { confirm: 'Abort', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => abortMutation.mutate(),
    });

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['scanstatus', id] });
    void queryClient.invalidateQueries({ queryKey: ['scansummary', id] });
    void queryClient.invalidateQueries({ queryKey: ['scanopts', id] });
    void queryClient.invalidateQueries({ queryKey: ['scanlog', id] });
  };

  return (
    <Stack>
      <Breadcrumbs>
        {/* Plain <a>: full-page reload back to SPA scan list. */}
        <Anchor href="/">Scans</Anchor>
        <span>{status.name}</span>
      </Breadcrumbs>

      <Group justify="space-between">
        <Group>
          <Title order={2}>{status.name}</Title>
          <ScanStatusBadge status={status.status} />
        </Group>
        <Group>
          {running && (
            <Button
              color="red"
              variant="light"
              disabled={abortMutation.isPending}
              loading={abortMutation.isPending}
              onClick={openAbortConfirm}
            >
              Abort
            </Button>
          )}
          <Button variant="subtle" onClick={refreshAll}>
            Refresh
          </Button>
        </Group>
      </Group>

      {abortMutation.isError && (
        <Alert color="red" title="Abort failed">
          {(abortMutation.error as Error).message}
        </Alert>
      )}

      <Tabs value={activeTab} onChange={(v) => setActiveTab((v ?? 'status') as TabKey)}>
        <Tabs.List>
          <Tabs.Tab value="status">Status</Tabs.Tab>
          <Tabs.Tab value="correlations">Correlations</Tabs.Tab>
          <Tabs.Tab value="browse">Browse</Tabs.Tab>
          <Tabs.Tab value="graph">Graph</Tabs.Tab>
          <Tabs.Tab value="info">Info</Tabs.Tab>
          <Tabs.Tab value="log">Log</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="status" pt="md">
          <StatusTab id={id} status={status} />
        </Tabs.Panel>
        <Tabs.Panel value="correlations" pt="md">
          <CorrelationsTab id={id} />
        </Tabs.Panel>
        <Tabs.Panel value="browse" pt="md">
          <BrowseTab id={id} />
        </Tabs.Panel>
        <Tabs.Panel value="graph" pt="md">
          <PlaceholderTab tabLabel="Graph" scanId={id} />
        </Tabs.Panel>
        <Tabs.Panel value="info" pt="md">
          <InfoTab id={id} />
        </Tabs.Panel>
        <Tabs.Panel value="log" pt="md">
          <LogTab id={id} status={status} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
