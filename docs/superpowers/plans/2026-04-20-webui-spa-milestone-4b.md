# Web UI SPA — Milestone 4b (Browse + Correlations) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Browse and Correlations PlaceholderTab bodies with working React implementations backed by existing JSON endpoints. Graph stays on the placeholder until M4c.

**Architecture:** 6 tasks. API wrappers land first (with all tests), then the shared `EventList` drill-in component, then the two tab components, then the ScanInfoPage wire-up + Playwright, then docs. **Zero backend changes.**

**Tech Stack:** React 19, Mantine 9, TanStack Query 5, React Router 7, Vitest 2, Playwright 1.

**Spec:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-4b-design.md`.

---

## File Structure

### Frontend (React)

- **Modify** `webui/src/types.ts` — add `EventRisk`, `CorrelationRisk`, `CorrelationRow`, `EventViewMode`.
- **Modify** `webui/src/api/scaninfo.ts` — add `ScanEventRow` type, `fetchScanEvents`, `fetchScanEventsUnique`, `searchScanEvents`, `fetchCorrelations`, `toggleFalsePositive`.
- **Modify** `webui/src/api/scaninfo.test.ts` — add ~7 new Vitest cases.
- **Create** `webui/src/pages/scaninfo/EventList.tsx` — shared drill-in table. Used by both Browse and Correlations.
- **Create** `webui/src/pages/scaninfo/EventTypeList.tsx` — Browse landing view.
- **Create** `webui/src/pages/scaninfo/BrowseTab.tsx` — Browse state machine.
- **Create** `webui/src/pages/scaninfo/BrowseTab.test.tsx` — 3 Vitest cases.
- **Create** `webui/src/pages/scaninfo/CorrelationRiskBadge.tsx`.
- **Create** `webui/src/pages/scaninfo/CorrelationsList.tsx` — Correlations landing view.
- **Create** `webui/src/pages/scaninfo/CorrelationsTab.tsx` — Correlations state machine.
- **Create** `webui/src/pages/scaninfo/CorrelationsTab.test.tsx` — 2 Vitest cases.
- **Modify** `webui/src/pages/ScanInfoPage.tsx` — swap the Browse + Correlations PlaceholderTab usages for the new components.

### E2E

- **Create** `webui/tests/e2e/06-scaninfo-browse.spec.ts` — 2 Playwright cases.

### Docs

- **Modify** `CLAUDE.md` — update Web UI paragraph.
- **Modify** `docs/superpowers/BACKLOG.md` — mark M4b shipped.

---

## Context for the implementer

- **Branch:** master, direct commits. HEAD is 3363e646 (M4b spec commit).
- **Baseline:** 53 Vitest + 12 Playwright + flake8 clean + 1466 pytest + 34 skipped.
- **No backend changes** — every endpoint M4b touches is already live and already JSON. The SPA just wraps them.
- **Existing scaninfo module structure:**
  ```
  webui/src/pages/scaninfo/
    PlaceholderTab.tsx      (from M4a)
    StatusTab.tsx           (from M4a)
    InfoTab.tsx             (from M4a)
    LogTab.tsx              (from M4a)
  ```
  This task adds:
  ```
    EventList.tsx
    EventTypeList.tsx
    BrowseTab.tsx + BrowseTab.test.tsx
    CorrelationRiskBadge.tsx
    CorrelationsList.tsx
    CorrelationsTab.tsx + CorrelationsTab.test.tsx
  ```
- **`/scaneventresults` row shape (11 fields, positional):**
  ```
  [lastseen, data, source_data, source_module, source_event_hash, hash, _lastseen_raw, source_module_hash, fp, risk, event_type]
  ```
  The SPA hides these indices inside `fetchScanEvents`. `fp` is `0`/`1` (int) from the backend; map to `boolean`.
- **`/scancorrelations` row shape (8 fields):** `[id, headline, collection, rule_id, rule_name, rule_descr, rule_risk, events_count]`.
- **`/resultsetfp` response shape:** `["SUCCESS", …]` / `["WARNING", msg]` / `["ERROR", msg]` — wrapper throws on non-SUCCESS with the server message.
- **Mantine v9 primitives used in this milestone:** `Tabs` (already in page), `Table`, `Badge`, `Anchor`, `Alert`, `Breadcrumbs`, `Button`, `Menu`, `SegmentedControl`, `Switch`, `TextInput`, `Group`, `Stack`, `Title`, `Text`, `Loader`, `ActionIcon`. `@tabler/icons-react` used already (IconDotsVertical, IconDownload).
- **`useDebouncedValue`** is in `@mantine/hooks`, already installed.
- **`@typescript-eslint/no-explicit-any`** is active — use `Mock` from vitest.
- **`erasableSyntaxOnly: true`** in tsconfig — type-only imports use `import type`.
- **Integration tests:** pytest counts unchanged by this milestone. Don't touch any `test/unit/` or `test/integration/` file.

---

## Task 1: Types + API wrappers + Vitest

**Files:**
- Modify: `webui/src/types.ts` — add 4 new types.
- Modify: `webui/src/api/scaninfo.ts` — add the event/correlation wrappers.
- Modify: `webui/src/api/scaninfo.test.ts` — 7 new Vitest cases.

### Step 1: Extend `webui/src/types.ts`

`ScanStatus` etc. are already in this file; just append. No new import needed:

```typescript
export type EventRisk = 'NONE' | 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH';

export type CorrelationRisk = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH';

export type CorrelationRow = {
  id: string;
  headline: string;
  collection: string;
  ruleId: string;
  ruleName: string;
  ruleDescr: string;
  ruleRisk: CorrelationRisk;
  eventsCount: number;
};

export type EventViewMode = 'full' | 'unique';
```

### Step 2: Extend `webui/src/api/scaninfo.ts`

Add `ScanEventRow` type + 5 new exports. Import `EventRisk`, `CorrelationRow`, `CorrelationRisk` alongside the existing `import type`.

```typescript
// Added near the top, alongside existing imports:
import type {
  ScanStatusPayload,
  ScanSummaryRow,
  ScanOptsPayload,
  ScanLogEntry,
  ScanStatus,
  RiskMatrix,
  EventRisk,
  CorrelationRow,
  CorrelationRisk,
} from '../types';

// Added near the top alongside existing exports:
export type ScanEventRow = {
  hash: string;
  lastSeen: string;
  data: string;
  sourceData: string;
  sourceModule: string;
  sourceEventHash: string;
  sourceModuleHash: string;
  fp: boolean;
  risk: EventRisk;
  eventType: string;
};

// /scaneventresults returns an 11-tuple per row; field ordering:
// 0 lastseen, 1 data, 2 source_data, 3 source_module,
// 4 source_event_hash, 5 hash, 6 _lastseen_raw, 7 source_module_hash,
// 8 fp, 9 risk, 10 event_type
type ScanEventTuple = [
  string,
  string,
  string,
  string,
  string,
  string,
  number,
  string,
  number,
  EventRisk,
  string,
];

function mapEventRow(row: ScanEventTuple): ScanEventRow {
  return {
    lastSeen: row[0],
    data: row[1],
    sourceData: row[2],
    sourceModule: row[3],
    sourceEventHash: row[4],
    hash: row[5],
    sourceModuleHash: row[7],
    fp: Boolean(row[8]),
    risk: row[9],
    eventType: row[10],
  };
}

export async function fetchScanEvents(args: {
  id: string;
  eventType?: string;
  correlationId?: string;
  filterFp?: boolean;
}): Promise<ScanEventRow[]> {
  const params = new URLSearchParams({ id: args.id });
  if (args.eventType) params.set('eventType', args.eventType);
  if (args.correlationId) params.set('correlationId', args.correlationId);
  if (args.filterFp !== undefined) {
    params.set('filterfp', args.filterFp ? 'true' : 'false');
  }
  const rows = await fetchJson<ScanEventTuple[]>(
    `/scaneventresults?${params.toString()}`,
  );
  return rows.map(mapEventRow);
}

export async function fetchScanEventsUnique(args: {
  id: string;
  eventType: string;
  filterFp?: boolean;
}): Promise<ScanEventRow[]> {
  const params = new URLSearchParams({
    id: args.id,
    eventType: args.eventType,
  });
  if (args.filterFp !== undefined) {
    params.set('filterfp', args.filterFp ? 'true' : 'false');
  }
  const rows = await fetchJson<ScanEventTuple[]>(
    `/scaneventresultsunique?${params.toString()}`,
  );
  return rows.map(mapEventRow);
}

export async function searchScanEvents(args: {
  id: string;
  eventType: string;
  value: string;
}): Promise<ScanEventRow[]> {
  const params = new URLSearchParams({
    id: args.id,
    eventType: args.eventType,
    value: args.value,
  });
  const rows = await fetchJson<ScanEventTuple[]>(
    `/search?${params.toString()}`,
  );
  return rows.map(mapEventRow);
}

type CorrelationTuple = [
  string,
  string,
  string,
  string,
  string,
  string,
  CorrelationRisk,
  number,
];

export async function fetchCorrelations(id: string): Promise<CorrelationRow[]> {
  const rows = await fetchJson<CorrelationTuple[]>(
    `/scancorrelations?id=${encodeURIComponent(id)}`,
  );
  return rows.map(
    ([id, headline, collection, ruleId, ruleName, ruleDescr, ruleRisk, eventsCount]) => ({
      id,
      headline,
      collection,
      ruleId,
      ruleName,
      ruleDescr,
      ruleRisk,
      eventsCount,
    }),
  );
}

export async function toggleFalsePositive(args: {
  id: string;
  resultIds: string[];
  fp: boolean;
}): Promise<void> {
  const params = new URLSearchParams({
    id: args.id,
    fp: args.fp ? '1' : '0',
    resultids: JSON.stringify(args.resultIds),
  });
  const result = await fetchJson<[string, string?]>(
    `/resultsetfp?${params.toString()}`,
  );
  if (!Array.isArray(result) || result[0] !== 'SUCCESS') {
    throw new Error(result?.[1] ?? 'Failed to toggle false positive flag');
  }
}
```

### Step 3: Extend `webui/src/api/scaninfo.test.ts`

At the end of the file, add 7 new cases. Import the new exports at the top.

```typescript
import {
  fetchScanStatus,
  fetchScanSummary,
  fetchScanLog,
  fetchScanOpts,
  stopScan,
  fetchScanEvents,
  fetchScanEventsUnique,
  searchScanEvents,
  fetchCorrelations,
  toggleFalsePositive,
} from './scaninfo';
```

```typescript
describe('fetchScanEvents', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps the 11-tuple rows to typed ScanEventRow[]', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            '2026-04-20 14:23:01',
            'example.com',
            'root',
            'sfp_dnsresolve',
            'hashA',
            'hashB',
            1_700_000_000,
            'modHashC',
            0,
            'NONE',
            'INTERNET_NAME',
          ],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchScanEvents({ id: 'abc', eventType: 'INTERNET_NAME' });
    expect(rows).toEqual([
      {
        lastSeen: '2026-04-20 14:23:01',
        data: 'example.com',
        sourceData: 'root',
        sourceModule: 'sfp_dnsresolve',
        sourceEventHash: 'hashA',
        hash: 'hashB',
        sourceModuleHash: 'modHashC',
        fp: false,
        risk: 'NONE',
        eventType: 'INTERNET_NAME',
      },
    ]);
  });

  it('passes filterfp=true and eventType on the URL', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await fetchScanEvents({
      id: 'abc',
      eventType: 'IP_ADDRESS',
      filterFp: true,
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe(
      '/scaneventresults?id=abc&eventType=IP_ADDRESS&filterfp=true',
    );
  });

  it('passes correlationId when given', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await fetchScanEvents({ id: 'abc', correlationId: 'corr1' });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/scaneventresults?id=abc&correlationId=corr1');
  });
});

describe('fetchScanEventsUnique', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('uses the /scaneventresultsunique path', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await fetchScanEventsUnique({ id: 'abc', eventType: 'INTERNET_NAME' });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/scaneventresultsunique?id=abc&eventType=INTERNET_NAME');
  });
});

describe('searchScanEvents', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('uses the /search path with url-encoded value', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await searchScanEvents({
      id: 'abc',
      eventType: 'INTERNET_NAME',
      value: 'exa mple.com',
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe(
      '/search?id=abc&eventType=INTERNET_NAME&value=exa+mple.com',
    );
  });
});

describe('fetchCorrelations', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps the 8-tuple rows to typed CorrelationRow[]', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            'corr1',
            'Suspicious co-hosted domains',
            'collect',
            'rule.suspicious.cohost',
            'Suspicious co-host',
            'Triggers when ...',
            'HIGH',
            12,
          ],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchCorrelations('abc');
    expect(rows).toEqual([
      {
        id: 'corr1',
        headline: 'Suspicious co-hosted domains',
        collection: 'collect',
        ruleId: 'rule.suspicious.cohost',
        ruleName: 'Suspicious co-host',
        ruleDescr: 'Triggers when ...',
        ruleRisk: 'HIGH',
        eventsCount: 12,
      },
    ]);
  });
});

describe('toggleFalsePositive', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('sends fp=1 and JSON-encoded resultIds on SUCCESS', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
    );
    await toggleFalsePositive({
      id: 'abc',
      resultIds: ['h1', 'h2'],
      fp: true,
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    const parsed = new URL(url as string, 'http://host');
    expect(parsed.pathname).toBe('/resultsetfp');
    expect(parsed.searchParams.get('id')).toBe('abc');
    expect(parsed.searchParams.get('fp')).toBe('1');
    expect(parsed.searchParams.get('resultids')).toBe('["h1","h2"]');
  });

  it('throws the server message on ERROR', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['ERROR', 'Not allowed']), { status: 200 }),
    );
    await expect(
      toggleFalsePositive({ id: 'abc', resultIds: ['h1'], fp: true }),
    ).rejects.toThrow('Not allowed');
  });
});
```

### Step 4: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **53 existing + 7 new = 60 passing**.

### Step 5: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

Expected: success.

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/types.ts webui/src/api/scaninfo.ts webui/src/api/scaninfo.test.ts
git commit -m "$(cat <<'EOF'
webui: typed API for /scaneventresults, /scancorrelations, /search, /resultsetfp

Adds ScanEventRow / CorrelationRow / EventRisk / CorrelationRisk /
EventViewMode types and five new exports on scaninfo.ts:

- fetchScanEvents({id, eventType?, correlationId?, filterFp?})
  → typed 11-field rows mapped to named fields.
- fetchScanEventsUnique({id, eventType, filterFp?}).
- searchScanEvents({id, eventType, value}).
- fetchCorrelations(id) → typed 8-field rows.
- toggleFalsePositive({id, resultIds, fp}) → throws server message
  on non-SUCCESS.

7 Vitest cases cover tuple -> object mapping on events + correlations,
URL param construction (filterfp, correlationId, search encoding),
and toggleFalsePositive's SUCCESS/ERROR branches.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4b-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: EventList shared drill-in component

**Files:**
- Create: `webui/src/pages/scaninfo/EventList.tsx`.

### Step 1: Create the file

```tsx
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
import type { EventRisk, EventViewMode, ScanEventRow } from '../../types';

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
```

### Step 2: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 3: Run Vitest — should stay green (no new tests, component tested transitively)

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -4
```

Expected: **60 passing** (same as Task 1).

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/scaninfo/EventList.tsx
git commit -m "$(cat <<'EOF'
webui: EventList — shared drill-in table for Browse + Correlations

Single component used by both BrowseTab (per-event-type events)
and CorrelationsTab (events-for-correlation). Props:

- id + onBack + backLabel + headerTitle (required)
- eventType (Browse path — enables Full/Unique toggle + search +
  export scope)
- correlationId (Correlation path — used in the events fetch)
- hideViewModeToggle (Correlations uses this; unique variant
  isn't available for correlation-filtered events)

Features: Full/Unique SegmentedControl, Hide-FP Switch (default
on), debounced value search (300ms) that flips the query to
/search when non-empty, CSV+Excel export via <a download>,
per-row FP toggle via Menu + notification.

Controlled state lives entirely inside this component — the two
tab containers only supply their id + eventType/correlationId
scope.

Tests: transitively through BrowseTab.test.tsx and
CorrelationsTab.test.tsx in later tasks.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4b-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: BrowseTab + EventTypeList + Vitest

**Files:**
- Create: `webui/src/pages/scaninfo/EventTypeList.tsx`.
- Create: `webui/src/pages/scaninfo/BrowseTab.tsx`.
- Create: `webui/src/pages/scaninfo/BrowseTab.test.tsx`.

### Step 1: Create `webui/src/pages/scaninfo/EventTypeList.tsx`

```tsx
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Anchor,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { fetchScanSummary } from '../../api/scaninfo';
import type { ScanSummaryRow } from '../../types';

export function EventTypeList({
  id,
  onSelect,
}: {
  id: string;
  onSelect: (type: ScanSummaryRow) => void;
}) {
  const query = useQuery({
    queryKey: ['scansummary', id],
    queryFn: () => fetchScanSummary(id),
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
      <Alert color="red" title="Failed to load event types">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = (query.data ?? []).slice().sort((a, b) => b.count - a.count);

  if (rows.length === 0) {
    return <Alert color="gray">No events produced yet.</Alert>;
  }

  return (
    <Stack>
      <Title order={3}>Browse by event type</Title>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Event type</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>Count</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>Unique</Table.Th>
            <Table.Th>Last seen</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.typeId}>
              <Table.Td>
                <Anchor
                  component="button"
                  type="button"
                  onClick={() => onSelect(r)}
                >
                  <Stack gap={0} align="flex-start">
                    <Text size="sm" fw={500}>{r.typeLabel}</Text>
                    <Text size="xs" c="dimmed">{r.typeId}</Text>
                  </Stack>
                </Anchor>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>{r.count}</Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>{r.uniqueCount}</Table.Td>
              <Table.Td>{r.lastSeen}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
```

### Step 2: Create `webui/src/pages/scaninfo/BrowseTab.tsx`

```tsx
import { useState } from 'react';
import { EventList } from './EventList';
import { EventTypeList } from './EventTypeList';
import type { ScanSummaryRow } from '../../types';

export function BrowseTab({ id }: { id: string }) {
  const [selected, setSelected] = useState<ScanSummaryRow | null>(null);

  if (!selected) {
    return <EventTypeList id={id} onSelect={setSelected} />;
  }

  return (
    <EventList
      id={id}
      eventType={selected.typeId}
      onBack={() => setSelected(null)}
      backLabel="All event types"
      headerTitle={selected.typeLabel}
    />
  );
}
```

### Step 3: Create `webui/src/pages/scaninfo/BrowseTab.test.tsx`

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { BrowseTab } from './BrowseTab';

describe('BrowseTab', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function renderTab() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <Notifications />
          <BrowseTab id="abc" />
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockApi(overrides: Record<string, unknown> = {}) {
    const defaults = {
      summary: [
        [
          'INTERNET_NAME',
          'Internet Name',
          '2026-04-20 14:23:01',
          3,
          2,
          'FINISHED',
        ],
      ],
      events: [
        [
          '2026-04-20 14:23:01',
          'example.com',
          'root',
          'sfp_dnsresolve',
          'srcHash',
          'rowHash',
          1_700_000_000,
          'modHash',
          0,
          'NONE',
          'INTERNET_NAME',
        ],
      ],
      ...overrides,
    };
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url.startsWith('/scansummary')) {
        return Promise.resolve(
          new Response(JSON.stringify(defaults.summary), { status: 200 }),
        );
      }
      if (url.startsWith('/scaneventresults') || url.startsWith('/scaneventresultsunique') || url.startsWith('/search')) {
        return Promise.resolve(
          new Response(JSON.stringify(defaults.events), { status: 200 }),
        );
      }
      if (url.startsWith('/resultsetfp')) {
        return Promise.resolve(
          new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  it('renders the event-type list and drills into the per-type events on click', async () => {
    mockApi();
    renderTab();

    // Type list renders first
    expect(await screen.findByText('Internet Name')).toBeInTheDocument();

    // Click the event type
    await userEvent.click(screen.getByRole('button', { name: /Internet Name/ }));

    // Drill-in: event row shows the data value
    expect(await screen.findByText('example.com')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Export' }) || screen.getByRole('button', { name: 'Export' })).toBeTruthy();
  });

  it('triggers /resultsetfp when clicking Mark false positive', async () => {
    mockApi();
    renderTab();
    await userEvent.click(await screen.findByRole('button', { name: /Internet Name/ }));
    await screen.findByText('example.com');

    // Open the row action menu
    await userEvent.click(
      screen.getByRole('button', { name: /Actions for example.com/ }),
    );
    await userEvent.click(
      await screen.findByRole('menuitem', { name: 'Mark false positive' }),
    );

    await waitFor(() => {
      const fpCalls = (globalThis.fetch as Mock).mock.calls.filter(
        ([url]) => typeof url === 'string' && url.startsWith('/resultsetfp'),
      );
      expect(fpCalls).toHaveLength(1);
      const [url] = fpCalls[0];
      const parsed = new URL(url as string, 'http://host');
      expect(parsed.searchParams.get('fp')).toBe('1');
      expect(parsed.searchParams.get('resultids')).toBe('["rowHash"]');
    });
  });

  it('switches to /scaneventresultsunique when Unique is selected', async () => {
    mockApi();
    renderTab();
    await userEvent.click(await screen.findByRole('button', { name: /Internet Name/ }));
    await screen.findByText('example.com');

    // Click the Unique segment
    await userEvent.click(screen.getByRole('radio', { name: 'Unique' }));

    await waitFor(() => {
      const uniqueCalls = (globalThis.fetch as Mock).mock.calls.filter(
        ([url]) => typeof url === 'string' && url.startsWith('/scaneventresultsunique'),
      );
      expect(uniqueCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});
```

### Step 4: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **60 + 3 = 63 passing**.

### Step 5: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/scaninfo/BrowseTab.tsx webui/src/pages/scaninfo/BrowseTab.test.tsx webui/src/pages/scaninfo/EventTypeList.tsx
git commit -m "$(cat <<'EOF'
webui: BrowseTab — event-type list + EventList drill-in

BrowseTab is a two-view state machine:
- view=type-list renders EventTypeList, a clickable Table of
  event types (reuses the /scansummary query that StatusTab
  already uses so no extra fetch).
- view=events renders EventList scoped to the selected type.

EventTypeList renders typeLabel + typeId as the clickable cell,
sorted by count desc.

3 Vitest cases cover: type-list drill-in transition, mark-FP
posting to /resultsetfp with the row hash, Full/Unique toggle
flipping the query to /scaneventresultsunique.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4b-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: CorrelationsTab + CorrelationsList + CorrelationRiskBadge + Vitest

**Files:**
- Create: `webui/src/pages/scaninfo/CorrelationRiskBadge.tsx`.
- Create: `webui/src/pages/scaninfo/CorrelationsList.tsx`.
- Create: `webui/src/pages/scaninfo/CorrelationsTab.tsx`.
- Create: `webui/src/pages/scaninfo/CorrelationsTab.test.tsx`.

### Step 1: Create `webui/src/pages/scaninfo/CorrelationRiskBadge.tsx`

```tsx
import { Badge } from '@mantine/core';
import type { CorrelationRisk } from '../../types';

const RISK_COLORS: Record<CorrelationRisk, string> = {
  INFO: 'blue',
  LOW: 'yellow',
  MEDIUM: 'orange',
  HIGH: 'red',
};

export function CorrelationRiskBadge({ risk }: { risk: CorrelationRisk }) {
  return (
    <Badge color={RISK_COLORS[risk] ?? 'gray'} variant="light">
      {risk}
    </Badge>
  );
}
```

### Step 2: Create `webui/src/pages/scaninfo/CorrelationsList.tsx`

```tsx
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Anchor,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { fetchCorrelations } from '../../api/scaninfo';
import { CorrelationRiskBadge } from './CorrelationRiskBadge';
import type { CorrelationRow } from '../../types';

export function CorrelationsList({
  id,
  onSelect,
}: {
  id: string;
  onSelect: (row: CorrelationRow) => void;
}) {
  const query = useQuery({
    queryKey: ['scancorrelations', id],
    queryFn: () => fetchCorrelations(id),
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
      <Alert color="red" title="Failed to load correlations">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = query.data ?? [];

  if (rows.length === 0) {
    return (
      <Stack>
        <Title order={3}>Triggered correlations</Title>
        <Alert color="gray">No correlations triggered for this scan.</Alert>
      </Stack>
    );
  }

  return (
    <Stack>
      <Title order={3}>Triggered correlations</Title>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th style={{ width: 90 }}>Risk</Table.Th>
            <Table.Th>Headline</Table.Th>
            <Table.Th>Rule</Table.Th>
            <Table.Th style={{ width: 90, textAlign: 'right' }}>Events</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>
                <CorrelationRiskBadge risk={r.ruleRisk} />
              </Table.Td>
              <Table.Td>
                <Anchor
                  component="button"
                  type="button"
                  onClick={() => onSelect(r)}
                >
                  <Text size="sm" fw={500}>{r.headline}</Text>
                </Anchor>
              </Table.Td>
              <Table.Td>
                <Stack gap={0}>
                  <Text size="xs">{r.ruleName}</Text>
                  <Text size="xs" c="dimmed">{r.ruleId}</Text>
                </Stack>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>{r.eventsCount}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
```

### Step 3: Create `webui/src/pages/scaninfo/CorrelationsTab.tsx`

```tsx
import { useState } from 'react';
import { Group, Stack, Text } from '@mantine/core';
import { CorrelationsList } from './CorrelationsList';
import { CorrelationRiskBadge } from './CorrelationRiskBadge';
import { EventList } from './EventList';
import type { CorrelationRow } from '../../types';

export function CorrelationsTab({ id }: { id: string }) {
  const [selected, setSelected] = useState<CorrelationRow | null>(null);

  if (!selected) {
    return <CorrelationsList id={id} onSelect={setSelected} />;
  }

  const headerTitle = (
    <Stack gap={4}>
      <Group gap="xs" align="center">
        <Text fw={600}>{selected.headline}</Text>
        <CorrelationRiskBadge risk={selected.ruleRisk} />
      </Group>
      <Text size="xs" c="dimmed">
        {selected.ruleDescr}
      </Text>
    </Stack>
  );

  return (
    <EventList
      id={id}
      correlationId={selected.id}
      onBack={() => setSelected(null)}
      backLabel="All correlations"
      headerTitle={headerTitle}
      hideViewModeToggle
    />
  );
}
```

### Step 4: Create `webui/src/pages/scaninfo/CorrelationsTab.test.tsx`

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { CorrelationsTab } from './CorrelationsTab';

describe('CorrelationsTab', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function renderTab() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <Notifications />
          <CorrelationsTab id="abc" />
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  it('renders an empty-state Alert when there are no correlations', async () => {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url.startsWith('/scancorrelations')) {
        return Promise.resolve(new Response('[]', { status: 200 }));
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
    renderTab();
    expect(
      await screen.findByText('No correlations triggered for this scan.'),
    ).toBeInTheDocument();
  });

  it('lists correlations and drills into events for the selected one', async () => {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url.startsWith('/scancorrelations')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              [
                'corr1',
                'Suspicious co-hosted domains',
                'collect',
                'rule.suspicious.cohost',
                'Suspicious co-host',
                'Triggered when shared IP spans 5+ domains',
                'HIGH',
                4,
              ],
            ]),
            { status: 200 },
          ),
        );
      }
      if (url.startsWith('/scaneventresults')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              [
                '2026-04-20 14:23:01',
                'example.com',
                'root',
                'sfp_dnsresolve',
                'srcHash',
                'rowHash',
                1_700_000_000,
                'modHash',
                0,
                'NONE',
                'INTERNET_NAME',
              ],
            ]),
            { status: 200 },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
    renderTab();

    await userEvent.click(
      await screen.findByRole('button', { name: /Suspicious co-hosted domains/ }),
    );
    expect(await screen.findByText('example.com')).toBeInTheDocument();
  });
});
```

### Step 5: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **63 + 2 = 65 passing**.

### Step 6: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 7: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/scaninfo/CorrelationRiskBadge.tsx webui/src/pages/scaninfo/CorrelationsList.tsx webui/src/pages/scaninfo/CorrelationsTab.tsx webui/src/pages/scaninfo/CorrelationsTab.test.tsx
git commit -m "$(cat <<'EOF'
webui: CorrelationsTab — list + drill-in

Three small pieces:

- CorrelationRiskBadge: Mantine Badge with HIGH→red / MEDIUM→orange
  / LOW→yellow / INFO→blue color map.
- CorrelationsList: Table of triggered correlations (risk /
  headline / rule / events count), clickable rows. Empty-state
  Alert when the scan has no correlations.
- CorrelationsTab: two-view state machine. On drill-in, reuses
  EventList with correlationId scope and hideViewModeToggle
  (unique-variant isn't meaningful for correlation-filtered events).

2 Vitest cases: empty-state renders, drill-in transitions to
the events view with the correlation's headline.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4b-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire into ScanInfoPage + Playwright

**Files:**
- Modify: `webui/src/pages/ScanInfoPage.tsx` — swap Browse + Correlations PlaceholderTab for BrowseTab / CorrelationsTab. Graph stays on PlaceholderTab.
- Create: `webui/tests/e2e/06-scaninfo-browse.spec.ts`.

### Step 1: Modify `webui/src/pages/ScanInfoPage.tsx`

Add imports near the top:

```tsx
import { BrowseTab } from './scaninfo/BrowseTab';
import { CorrelationsTab } from './scaninfo/CorrelationsTab';
```

Find and replace the two placeholder bodies. Browse:

```tsx
<Tabs.Panel value="browse" pt="md">
  <PlaceholderTab tabLabel="Browse" scanId={id} />
</Tabs.Panel>
```

becomes:

```tsx
<Tabs.Panel value="browse" pt="md">
  <BrowseTab id={id} />
</Tabs.Panel>
```

Correlations:

```tsx
<Tabs.Panel value="correlations" pt="md">
  <PlaceholderTab tabLabel="Correlations" scanId={id} />
</Tabs.Panel>
```

becomes:

```tsx
<Tabs.Panel value="correlations" pt="md">
  <CorrelationsTab id={id} />
</Tabs.Panel>
```

Graph panel still uses `<PlaceholderTab tabLabel="Graph" scanId={id} />` — don't touch it.

### Step 2: Update the existing ShellPage test mocks

Open `webui/src/pages/ScanInfoPage.test.tsx`. The existing mock responded to `/scanstatus`, `/scansummary`, `/scanopts`, `/scanlog`. With Browse/Correlations now live, clicking the Correlations tab in test 3 (which currently asserts the PlaceholderTab) will try to hit `/scancorrelations`.

Update the shell test that switches to the Correlations tab — it currently asserts the PlaceholderTab renders. Since Correlations is now a real tab, that assertion no longer matches.

Rewrite test 3 to assert the **Browse** tab's placeholder — wait, Browse is also now live. The original purpose of the test was "switching to a placeholder tab renders the migrating alert". Since the only remaining PlaceholderTab is **Graph**, retarget test 3 to the Graph tab:

```tsx
it('shows Abort button while running and switching to the Graph tab shows the placeholder with legacy link', async () => {
  mockStatus('RUNNING');
  renderAt('/scaninfo?id=abc');
  await screen.findByRole('heading', { level: 2, name: 'my-scan' });
  expect(screen.getByRole('button', { name: 'Abort' })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('tab', { name: 'Graph' }));
  const legacyLink = await screen.findByRole('link', {
    name: /Open legacy Graph view/,
  });
  expect(legacyLink).toHaveAttribute('href', '/scaninfo-legacy?id=abc');
});
```

Also extend the mock to respond to `/scaneventresults` / `/scaneventresultsunique` / `/search` / `/scancorrelations` / `/resultsetfp` with empty arrays so test 1 (which renders all tabs but the default is Status — Browse + Correlations won't fire queries until their panel is active). Default-tab is Status, so this may not actually be necessary — but add the entries defensively for the test that clicks through to Correlations (test 3 post-rewrite clicks Graph which is the placeholder, no API call).

### Step 3: Create `webui/tests/e2e/06-scaninfo-browse.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

// Runs after 05-scaninfo.spec.ts. Navigates from the scan list to
// the seeded "monthly-recon" FINISHED scan, then exercises Browse
// and Correlations tabs.

async function openFinishedScanInfo(
  page: import('@playwright/test').Page,
): Promise<void> {
  await page.goto('/');
  const anchor = page.getByRole('link', { name: 'monthly-recon' });
  await expect(anchor).toBeVisible();
  await anchor.click();
  await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 10_000 });
}

test.describe('Scan info page (M4b: Browse + Correlations)', () => {
  test('Browse tab drills into events for the first event type', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Browse' }).click();

    // Event-type landing renders.
    await expect(
      page.getByRole('heading', { name: 'Browse by event type' }),
    ).toBeVisible();

    // The seeded scan has at least one event type — click the first clickable type cell.
    const firstTypeButton = page
      .getByRole('button', { name: /.*/ })
      .filter({ hasText: /.+/ })
      .first();
    // More specific: the type-list only has buttons wrapping type labels.
    // The "Back" button and export don't appear on the type list, so the
    // first role=button element is a type row.
    await firstTypeButton.click();

    // Drill-in shows the "← All event types" breadcrumb button.
    await expect(
      page.getByRole('button', { name: /All event types/ }),
    ).toBeVisible();
  });

  test('Correlations tab renders either the list or the empty-state alert', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Correlations' }).click();

    await expect(
      page.getByRole('heading', { name: 'Triggered correlations' }),
    ).toBeVisible();

    // Seeded scan has no correlations (no correlation rules run during the
    // fixture). Accept either the empty-state alert OR a populated table.
    const emptyAlert = page.getByText(/No correlations triggered/);
    const tableFirstRow = page.getByRole('row').nth(1);
    await expect(emptyAlert.or(tableFirstRow)).toBeVisible();
  });
});
```

### Step 4: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 5: Run Vitest — confirm the updated shell test still passes

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **65 passing** (no new Vitest tests in this task; the shell test was updated).

### Step 6: Run Playwright

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run test:e2e 2>&1 | tail -20
```

Expected: **12 existing + 2 new = 14 passing**.

If any Playwright test times out or flakes on selector ambiguity, adjust the selector rather than the component.

### Step 7: Full `./test/run` sanity check

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 65 Vitest + 14 Playwright + flake8 clean + 1466 pytest / 34 skipped.

### Step 8: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/ScanInfoPage.tsx webui/src/pages/ScanInfoPage.test.tsx webui/tests/e2e/06-scaninfo-browse.spec.ts
git commit -m "$(cat <<'EOF'
webui: wire BrowseTab + CorrelationsTab into ScanInfoPage

ScanInfoPage.tsx swaps the Browse and Correlations PlaceholderTab
usages for the real components from Tasks 3-4. Graph remains on
PlaceholderTab (→ M4c).

ScanInfoPage.test.tsx's placeholder-link test retargets from
Correlations to Graph — the only remaining placeholder tab.

06-scaninfo-browse.spec.ts adds 2 Playwright cases:
- Browse: click the tab, see the event-type landing, drill into
  the first type, see the "All event types" breadcrumb.
- Correlations: click the tab, see the header, verify either a
  populated table or the empty-state alert (seeded scan typically
  has no correlations).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4b-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Docs refresh + final verify

**Files:**
- Modify: `CLAUDE.md`.
- Modify: `docs/superpowers/BACKLOG.md`.

### Step 1: Update `CLAUDE.md` Web UI paragraph

Find:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1–4a (2026-04-20) migrated `/` (scan list), `/newscan` (scan creation), `/opts` (settings), and `/scaninfo` with the Status/Info/Log tabs; Browse/Correlations/Graph tabs render a placeholder that links to the still-Mako `/scaninfo-legacy` for functional fallback until milestones 4b+4c fill them in. The final sweep retires shared chrome (`HEADER.tmpl`/`FOOTER.tmpl`/`error.tmpl`) along with the legacy route.
```

Replace with:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1–4b (2026-04-20) migrated `/` (scan list), `/newscan` (scan creation), `/opts` (settings), and `/scaninfo` with 5 of 6 tabs (Status, Info, Log, Browse, Correlations). The Graph tab still renders a placeholder that links to the still-Mako `/scaninfo-legacy`; milestone 4c replaces it with @visx/network + d3-force and retires the legacy route. The final sweep retires shared chrome (`HEADER.tmpl`/`FOOTER.tmpl`/`error.tmpl`) alongside.
```

### Step 2: Update `docs/superpowers/BACKLOG.md`

Under `### UI modernization — page-by-page migration` → `**Shipped:**`, append:

```
- Milestone 4b (2026-04-20) — `/scaninfo` Browse + Correlations tabs. Two-view drill-in (event-type list → events, correlations list → events) sharing an `EventList` component that hosts Full/Unique toggle, hide-FP switch, debounced value search, CSV+Excel export, and per-row FP-flip. Zero new JSON endpoints — reuses `/scaneventresults`, `/scaneventresultsunique`, `/search`, `/scancorrelations`, `/scaneventresultexport`, `/resultsetfp`.
```

Update the specs reference (e.g. `{1,2,3,4a}` → `{1,2,3,4a,4b}`).

Update the **Remaining Mako pages** block:

```
**Remaining Mako pages to migrate** (each its own spec + plan):
- `/scaninfo` — Graph tab + `viz.js` replacement (milestone 4c). Uses @visx/network + d3-force, consistent with nightscout-java's @visx/* stack.
- Final sweep: retires `/scaninfo-legacy`, `scaninfo.tmpl`, `HEADER.tmpl`, `FOOTER.tmpl`, `error.tmpl`, `spiderfoot.js`, legacy CSS, and `spiderfoot/static/node_modules/`. Also folds in the Clone-scan UX (scan list menu + new JSON endpoint).
```

### Step 3: Final `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 65 Vitest + 14 Playwright + flake8 clean + 1466 pytest / 34 skipped.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — milestone 4b Web UI

Updates the Web UI section to reflect M4b shipped: Browse and
Correlations tabs now render React; Graph is the last placeholder
linking to /scaninfo-legacy until M4c swaps in @visx/network.

BACKLOG.md removes Browse+Correlations from the remaining list
and notes the @visx/network choice for M4c.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4b-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 5: Milestone summary

Report:
- 6 commits across M4b.
- SPA scaninfo now has 5 of 6 tabs (Status / Info / Log / Browse / Correlations).
- 65 Vitest + 14 Playwright + 1466 pytest all green.
- Graph tab + `viz.js` retirement land in M4c.
