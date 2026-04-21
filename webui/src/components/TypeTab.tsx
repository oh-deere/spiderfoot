import { useMemo } from 'react';
import {
  Button,
  Checkbox,
  Group,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import type { EventType } from '../types';

export function TypeTab({
  types,
  selected,
  onChange,
  filter,
  onFilterChange,
}: {
  types: EventType[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  filter: string;
  onFilterChange: (v: string) => void;
}) {
  const filtered = useMemo(
    () =>
      types.filter((t) => t.label.toLowerCase().includes(filter.toLowerCase())),
    [types, filter],
  );

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  const selectAll = () => onChange(new Set(types.map((t) => t.id)));
  const deselectAll = () => onChange(new Set());

  return (
    <Stack>
      <Group>
        <TextInput
          placeholder="Filter types..."
          value={filter}
          onChange={(e) => onFilterChange(e.currentTarget.value)}
          style={{ flex: 1 }}
          aria-label="Filter event types"
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
          No types match &quot;{filter}&quot;.
        </Text>
      ) : (
        <SimpleGrid cols={2}>
          {filtered.map((t) => (
            <Checkbox
              key={t.id}
              label={t.label}
              checked={selected.has(t.id)}
              onChange={() => toggle(t.id)}
            />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
