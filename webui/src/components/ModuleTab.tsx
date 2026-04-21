import { useMemo } from 'react';
import {
  Button,
  Checkbox,
  Group,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { IconKey } from '@tabler/icons-react';
import type { Module } from '../types';

export function ModuleTab({
  modules,
  selected,
  onChange,
  filter,
  onFilterChange,
}: {
  modules: Module[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  filter: string;
  onFilterChange: (v: string) => void;
}) {
  const filtered = useMemo(
    () => modules.filter((m) => m.name.toLowerCase().includes(filter.toLowerCase())),
    [modules, filter],
  );

  const toggle = (name: string) => {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  };

  const selectAll = () => onChange(new Set(modules.map((m) => m.name)));
  const deselectAll = () => onChange(new Set());

  return (
    <Stack>
      <Group>
        <TextInput
          placeholder="Filter modules..."
          value={filter}
          onChange={(e) => onFilterChange(e.currentTarget.value)}
          style={{ flex: 1 }}
          aria-label="Filter modules"
        />
        <Button variant="light" onClick={selectAll}>
          Select All
        </Button>
        <Button variant="light" onClick={deselectAll}>
          De-Select All
        </Button>
      </Group>

      {filtered.length === 0 ? (
        <Text c="dimmed" ta="center" mt="md">
          No modules match &quot;{filter}&quot;.
        </Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 40 }} />
              <Table.Th>Module</Table.Th>
              <Table.Th>Description</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map((m) => (
              <Table.Tr key={m.name}>
                <Table.Td>
                  <Checkbox
                    checked={selected.has(m.name)}
                    onChange={() => toggle(m.name)}
                    aria-label={`Toggle ${m.name}`}
                  />
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <Text>{m.name}</Text>
                    {m.api_key && (
                      <Tooltip label="Needs API key">
                        <IconKey size={14} />
                      </Tooltip>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{m.descr}</Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
