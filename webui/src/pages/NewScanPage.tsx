import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Accordion,
  Alert,
  Button,
  Group,
  Loader,
  Stack,
  Tabs,
  TextInput,
  Title,
  Text,
} from '@mantine/core';
import { listModules, listEventTypes } from '../api/modules';
import { startScan } from '../api/scans';
import { UseCaseTab } from '../components/UseCaseTab';
import { ModuleTab } from '../components/ModuleTab';
import { TypeTab } from '../components/TypeTab';
import type { SelectionMode, UseCase } from '../types';

export function NewScanPage() {
  const [scanName, setScanName] = useState('');
  const [scanTarget, setScanTarget] = useState('');
  const [mode, setMode] = useState<SelectionMode>('usecase');
  const [usecase, setUsecase] = useState<UseCase>('all');
  const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set());
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());
  const [moduleFilter, setModuleFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  const modulesQuery = useQuery({
    queryKey: ['modules'],
    queryFn: listModules,
    staleTime: Infinity,
  });
  const typesQuery = useQuery({
    queryKey: ['eventtypes'],
    queryFn: listEventTypes,
    staleTime: Infinity,
  });

  // Default: all modules + all types checked once loaded.
  useEffect(() => {
    if (modulesQuery.data && selectedModules.size === 0) {
      setSelectedModules(new Set(modulesQuery.data.map((m) => m.name)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modulesQuery.data]);

  useEffect(() => {
    if (typesQuery.data && selectedTypes.size === 0) {
      setSelectedTypes(new Set(typesQuery.data.map((t) => t.id)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typesQuery.data]);

  const submitMutation = useMutation({
    mutationFn: startScan,
    onSuccess: (scanId) => {
      // Hard redirect: /scaninfo is still a legacy Mako page outside
      // the SPA shell. Replace with useNavigate() once /scaninfo is
      // migrated (tracked in BACKLOG.md).
      window.location.href = `/scaninfo?id=${scanId}`;
    },
  });

  const submitDisabled =
    !scanName.trim() ||
    !scanTarget.trim() ||
    (mode === 'module' && selectedModules.size === 0) ||
    (mode === 'type' && selectedTypes.size === 0) ||
    submitMutation.isPending;

  if (modulesQuery.isLoading || typesQuery.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }

  if (modulesQuery.isError || typesQuery.isError) {
    const err = (modulesQuery.error ?? typesQuery.error) as Error;
    return (
      <Alert color="red" title="Failed to load form data" mt="md">
        {err.message}
        <Group mt="sm">
          <Button
            size="xs"
            onClick={() => {
              void modulesQuery.refetch();
              void typesQuery.refetch();
            }}
          >
            Retry
          </Button>
        </Group>
      </Alert>
    );
  }

  const handleSubmit = () => {
    submitMutation.mutate({
      scanName,
      scanTarget,
      mode,
      usecase,
      moduleList: Array.from(selectedModules),
      typeList: Array.from(selectedTypes),
    });
  };

  return (
    <Stack>
      <Title order={2}>New Scan</Title>

      {submitMutation.isError && (
        <Alert color="red" title="Failed to start scan">
          {(submitMutation.error as Error).message}
        </Alert>
      )}

      <Group grow>
        <TextInput
          label="Scan Name"
          placeholder="The name of this scan."
          value={scanName}
          onChange={(e) => setScanName(e.currentTarget.value)}
          required
        />
        <TextInput
          label="Scan Target"
          placeholder="The target of your scan."
          value={scanTarget}
          onChange={(e) => setScanTarget(e.currentTarget.value)}
          required
        />
      </Group>

      <Accordion variant="separated">
        <Accordion.Item value="target-types">
          <Accordion.Control>
            Target types — what can I enter?
          </Accordion.Control>
          <Accordion.Panel>
            <Text size="sm">
              SpiderFoot auto-detects the target type based on format:
              <br />
              <strong>Domain Name</strong>: example.com &nbsp;|&nbsp;
              <strong>IPv4 Address</strong>: 1.2.3.4 &nbsp;|&nbsp;
              <strong>IPv6 Address</strong>: 2606:4700:4700::1111 &nbsp;|&nbsp;
              <strong>Hostname/Sub-domain</strong>: abc.example.com
              <br />
              <strong>Subnet</strong>: 1.2.3.0/24 &nbsp;|&nbsp;
              <strong>Bitcoin Address</strong> &nbsp;|&nbsp;
              <strong>E-mail</strong>: bob@example.com &nbsp;|&nbsp;
              <strong>Phone Number</strong>: +12345678901 (E.164)
              <br />
              <strong>Human Name</strong>: &quot;John Smith&quot; (quoted) &nbsp;|&nbsp;
              <strong>Username</strong>: &quot;jsmith2000&quot; (quoted) &nbsp;|&nbsp;
              <strong>Network ASN</strong>: 1234
            </Text>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      <Tabs value={mode} onChange={(v) => setMode((v ?? 'usecase') as SelectionMode)}>
        <Tabs.List>
          <Tabs.Tab value="usecase">By Use Case</Tabs.Tab>
          <Tabs.Tab value="type">By Required Data</Tabs.Tab>
          <Tabs.Tab value="module">By Module</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="usecase" pt="md">
          <UseCaseTab value={usecase} onChange={setUsecase} />
        </Tabs.Panel>
        <Tabs.Panel value="type" pt="md">
          <TypeTab
            types={typesQuery.data ?? []}
            selected={selectedTypes}
            onChange={setSelectedTypes}
            filter={typeFilter}
            onFilterChange={setTypeFilter}
          />
        </Tabs.Panel>
        <Tabs.Panel value="module" pt="md">
          <ModuleTab
            modules={modulesQuery.data ?? []}
            selected={selectedModules}
            onChange={setSelectedModules}
            filter={moduleFilter}
            onFilterChange={setModuleFilter}
          />
        </Tabs.Panel>
      </Tabs>

      <Group justify="flex-end">
        <Button
          color="red"
          disabled={submitDisabled}
          loading={submitMutation.isPending}
          onClick={handleSubmit}
        >
          Run Scan Now
        </Button>
      </Group>
    </Stack>
  );
}
