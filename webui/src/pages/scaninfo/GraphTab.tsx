import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Group,
  Loader,
  SegmentedControl,
  Stack,
  Text,
} from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { fetchScanGraph } from '../../api/scaninfo';
import { useForceLayout } from './graph/useForceLayout';
import { GraphRenderer } from './GraphRenderer';
import type { GraphLayoutMode } from '../../types';

const MAX_INTERACTIVE_NODES = 500;

export function GraphTab({ id }: { id: string }) {
  const [mode, setMode] = useState<GraphLayoutMode>('force');

  const query = useQuery({
    queryKey: ['scangraph', id],
    queryFn: () => fetchScanGraph(id),
  });

  const layout = useForceLayout(
    query.data?.nodes ?? [],
    query.data?.edges ?? [],
    mode,
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
      <Alert color="red" title="Failed to load graph">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const data = query.data!;

  if (data.nodes.length === 0) {
    return <Alert color="gray">This scan produced no events yet.</Alert>;
  }

  if (data.nodes.length > MAX_INTERACTIVE_NODES) {
    return (
      <Alert color="blue" title="Graph too large for interactive render">
        <Stack gap="sm">
          <Text size="sm">
            This graph has {data.nodes.length} nodes — the SPA caps
            interactive rendering at {MAX_INTERACTIVE_NODES} for performance.
            Download the GEXF file below and open it in a dedicated graph
            tool (e.g. Gephi, Cytoscape) for a usable view of larger scans.
          </Text>
          <Group>
            <Button
              component="a"
              href={`/scanviz?id=${encodeURIComponent(id)}&gexf=1`}
              leftSection={<IconDownload size={14} />}
              variant="light"
            >
              Download GEXF ({data.nodes.length} nodes)
            </Button>
          </Group>
        </Stack>
      </Alert>
    );
  }

  return (
    <Stack>
      <Group justify="space-between" align="center">
        <Group gap="md">
          <SegmentedControl
            value={mode}
            onChange={(v) => setMode(v as GraphLayoutMode)}
            data={[
              { label: 'Force', value: 'force' },
              { label: 'Random', value: 'random' },
            ]}
          />
          <Group gap={4}>
            <Text size="xs" c="red">●</Text>
            <Text size="xs" c="dimmed">Target</Text>
            <Text size="xs" c="blue">●</Text>
            <Text size="xs" c="dimmed">Other data</Text>
          </Group>
        </Group>
        <Text size="xs" c="dimmed">
          {data.nodes.length} nodes, {data.edges.length} edges
        </Text>
      </Group>
      <GraphRenderer
        nodes={data.nodes}
        edges={data.edges}
        layout={layout}
        scanId={id}
      />
    </Stack>
  );
}
