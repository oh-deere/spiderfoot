import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Grid,
  Group,
  Loader,
  Menu,
  NavLink,
  Popover,
  ScrollArea,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconDotsVertical, IconHelp, IconKey } from '@tabler/icons-react';
import {
  fetchSettings,
  saveSettings,
  resetSettings,
  parseConfigFile,
  coerceToOriginalType,
} from '../api/settings';
import { SettingInput } from '../components/SettingInput';
import type { SettingValue, SettingsGroup } from '../types';

function isEqualValue(a: SettingValue, b: SettingValue): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((v, i) => v === b[i]);
  }
  return a === b;
}

export function OptsPage() {
  const queryClient = useQueryClient();
  const [activeGroup, setActiveGroup] = useState<string>('global');
  const [filter, setFilter] = useState('');
  const [current, setCurrent] = useState<Record<string, SettingValue>>({});
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const query = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
    staleTime: Infinity,
  });

  // Seed `current` whenever the server sends a fresh settings snapshot
  // (initial load + any post-save refetch). We rely on useQuery giving
  // us a new object reference each refetch, so this only runs when the
  // server state actually changes.
  useEffect(() => {
    if (query.data) {
      setCurrent({ ...query.data.settings });
    }
  }, [query.data]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!query.data) throw new Error('Settings not loaded');
      await saveSettings(query.data.token, current);
    },
    onSuccess: () => {
      notifications.show({
        color: 'green',
        title: 'Settings saved',
        message: 'Changes take effect on the next scan.',
      });
      void queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      if (!query.data) throw new Error('Settings not loaded');
      await resetSettings(query.data.token);
    },
    onSuccess: () => {
      notifications.show({
        color: 'green',
        title: 'Reset complete',
        message: 'Settings have been restored to factory defaults.',
      });
      void queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  const dirtyKeys = useMemo(() => {
    if (!query.data) return new Set<string>();
    const s = new Set<string>();
    for (const [k, v] of Object.entries(current)) {
      const orig = query.data.settings[k];
      if (orig === undefined || !isEqualValue(v, orig)) s.add(k);
    }
    return s;
  }, [current, query.data]);

  const isGroupDirty = (group: SettingsGroup): boolean =>
    Object.keys(group.settings).some((k) => dirtyKeys.has(k));

  if (query.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Alert color="red" title="Failed to load settings" mt="md">
        {(query.error as Error)?.message ?? 'Unknown error'}
        <Group mt="sm">
          <Button size="xs" onClick={() => void query.refetch()}>
            Retry
          </Button>
        </Group>
      </Alert>
    );
  }

  const groups = query.data.groups;
  const visibleGroups = groups.filter((g) =>
    g.key === 'global' ||
    g.label.toLowerCase().includes(filter.toLowerCase()) ||
    g.key.toLowerCase().includes(filter.toLowerCase()),
  );
  const selected = groups.find((g) => g.key === activeGroup) ?? groups[0];

  const openResetConfirm = () =>
    modals.openConfirmModal({
      title: 'Reset settings to factory default?',
      children: (
        <Text size="sm">
          This wipes every API key and every custom value and restores the
          defaults. Cannot be undone.
        </Text>
      ),
      labels: { confirm: 'Reset', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => resetMutation.mutate(),
    });

  const handleImportClick = () => fileInputRef.current?.click();
  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const contents = await file.text();
    const parsed = parseConfigFile(contents);
    const next = { ...current };
    let skipped = 0;
    for (const [k, raw] of Object.entries(parsed)) {
      if (!(k in next)) {
        skipped += 1;
        continue;
      }
      next[k] = coerceToOriginalType(raw, next[k]);
    }
    setCurrent(next);
    notifications.show({
      color: 'blue',
      title: 'Config imported',
      message: `${Object.keys(parsed).length - skipped} applied, ${skipped} skipped. Review and click Save.`,
    });
  };

  const hasApiKeyDataForSelected = (s: typeof selected): boolean =>
    !!s.meta?.apiKeyInstructions && s.meta.apiKeyInstructions.length > 0;

  return (
    <Stack>
      <Group justify="space-between" align="center">
        <Title order={2}>Settings</Title>
        <Group>
          <Button
            color="red"
            disabled={dirtyKeys.size === 0 || saveMutation.isPending}
            loading={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save Changes {dirtyKeys.size > 0 ? `(${dirtyKeys.size})` : ''}
          </Button>
          <Menu shadow="md" width={220}>
            <Menu.Target>
              <ActionIcon variant="subtle" aria-label="Settings actions">
                <IconDotsVertical size={18} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item onClick={handleImportClick}>Import API Keys</Menu.Item>
              <Menu.Item component="a" href="/optsexport" download>
                Export API Keys
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item color="red" onClick={openResetConfirm}>
                Reset to Factory Default
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>

      <input
        ref={fileInputRef}
        type="file"
        style={{ display: 'none' }}
        accept=".cfg,.txt,text/plain"
        onChange={handleImportFile}
        aria-label="Import config file"
      />

      {saveMutation.isError && (
        <Alert color="red" title="Save failed">
          {(saveMutation.error as Error).message}
        </Alert>
      )}
      {resetMutation.isError && (
        <Alert color="red" title="Reset failed">
          {(resetMutation.error as Error).message}
        </Alert>
      )}

      <Grid>
        <Grid.Col span={3}>
          <Stack>
            <TextInput
              placeholder="Filter modules..."
              value={filter}
              onChange={(e) => setFilter(e.currentTarget.value)}
              aria-label="Filter settings groups"
            />
            <ScrollArea h={600}>
              <Stack gap={2}>
                {visibleGroups.map((g) => (
                  <NavLink
                    key={g.key}
                    active={g.key === activeGroup}
                    label={g.label}
                    rightSection={
                      isGroupDirty(g) ? (
                        <Badge size="xs" color="red" variant="dot" aria-label="Has unsaved changes" />
                      ) : null
                    }
                    leftSection={
                      g.meta?.apiKeyInstructions ? <IconKey size={12} /> : null
                    }
                    onClick={() => setActiveGroup(g.key)}
                  />
                ))}
              </Stack>
            </ScrollArea>
          </Stack>
        </Grid.Col>

        <Grid.Col span={9}>
          {selected && (
            <Stack>
              <Group align="baseline">
                <Title order={3}>{selected.label}</Title>
                {selected.meta?.dataSourceWebsite && (
                  <Anchor href={selected.meta.dataSourceWebsite} target="_blank" size="sm">
                    {selected.meta.dataSourceWebsite}
                  </Anchor>
                )}
              </Group>

              {selected.meta && (
                <Stack gap={4}>
                  {selected.meta.descr && <Text size="sm">{selected.meta.descr}</Text>}
                  {selected.meta.dataSourceDescription && (
                    <Text size="sm" c="dimmed">
                      {selected.meta.dataSourceDescription}
                    </Text>
                  )}
                  {selected.meta.cats.length > 0 && (
                    <Text size="xs" c="dimmed">Categories: {selected.meta.cats.join(', ')}</Text>
                  )}
                </Stack>
              )}

              <Table striped withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th style={{ width: '40%' }}>Option</Table.Th>
                    <Table.Th>Value</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {Object.keys(selected.settings)
                    .sort()
                    .map((k) => {
                      const desc = selected.descs[k] ?? 'No description available.';
                      const isApiKey = k.includes('api_key');
                      const showInstructions =
                        isApiKey && hasApiKeyDataForSelected(selected);
                      return (
                        <Table.Tr key={k}>
                          <Table.Td>
                            <Group gap="xs" align="center">
                              <Text size="sm">{desc}</Text>
                              {showInstructions && (
                                <Popover width={320} position="right" withArrow>
                                  <Popover.Target>
                                    <ActionIcon variant="subtle" size="sm" aria-label="API key instructions">
                                      <IconHelp size={14} />
                                    </ActionIcon>
                                  </Popover.Target>
                                  <Popover.Dropdown>
                                    <Stack gap={4}>
                                      {selected.meta!.apiKeyInstructions!.map((step, i) => (
                                        <Text key={i} size="xs">{i + 1}. {step}</Text>
                                      ))}
                                    </Stack>
                                  </Popover.Dropdown>
                                </Popover>
                              )}
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <SettingInput
                              settingKey={k}
                              value={current[k] ?? selected.settings[k]}
                              onChange={(v) =>
                                setCurrent((prev) => ({ ...prev, [k]: v }))
                              }
                            />
                          </Table.Td>
                        </Table.Tr>
                      );
                    })}
                </Table.Tbody>
              </Table>
            </Stack>
          )}
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
