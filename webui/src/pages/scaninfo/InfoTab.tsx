import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Accordion,
  Alert,
  Code,
  Group,
  Loader,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { fetchScanOpts } from '../../api/scaninfo';

const META_LABELS = ['Name', 'Target', 'Target type', 'Modules', 'Created', 'Started', 'Ended'];

export function InfoTab({ id }: { id: string }) {
  const query = useQuery({
    queryKey: ['scanopts', id],
    queryFn: () => fetchScanOpts(id),
  });

  const { globalKvs, moduleKvs } = useMemo(() => {
    const config = (query.data?.config ?? {}) as Record<string, unknown>;
    const globalKvs: [string, unknown][] = [];
    const moduleKvs: [string, unknown][] = [];
    for (const [k, v] of Object.entries(config)) {
      if (k.startsWith('global.')) globalKvs.push([k, v]);
      else if (k.startsWith('module.')) moduleKvs.push([k, v]);
    }
    globalKvs.sort(([a], [b]) => a.localeCompare(b));
    moduleKvs.sort(([a], [b]) => a.localeCompare(b));
    return { globalKvs, moduleKvs };
  }, [query.data]);

  if (query.isLoading) {
    return (
      <Group justify="center" mt="md">
        <Loader />
      </Group>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Alert color="red" title="Failed to load scan config">
        {(query.error as Error)?.message ?? 'Unknown error'}
      </Alert>
    );
  }

  const meta = query.data.meta ?? [];

  return (
    <Stack>
      <Table withTableBorder>
        <Table.Tbody>
          {meta.map((v, i) => (
            <Table.Tr key={i}>
              <Table.Td style={{ width: 180 }}>
                <Text size="sm" fw={500}>{META_LABELS[i] ?? `Field ${i}`}</Text>
              </Table.Td>
              <Table.Td>
                <Code>{String(v)}</Code>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <Accordion variant="separated">
        <Accordion.Item value="global">
          <Accordion.Control>
            Global settings ({globalKvs.length})
          </Accordion.Control>
          <Accordion.Panel>
            <KvTable rows={globalKvs} />
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="module">
          <Accordion.Control>
            Module settings ({moduleKvs.length})
          </Accordion.Control>
          <Accordion.Panel>
            <KvTable rows={moduleKvs} />
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}

function KvTable({ rows }: { rows: [string, unknown][] }) {
  if (rows.length === 0) return <Text size="sm" c="dimmed">No entries.</Text>;
  return (
    <Table striped>
      <Table.Tbody>
        {rows.map(([k, v]) => (
          <Table.Tr key={k}>
            <Table.Td style={{ width: '40%' }}>
              <Code>{k}</Code>
            </Table.Td>
            <Table.Td>
              <Code>{Array.isArray(v) ? v.join(', ') : String(v)}</Code>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
