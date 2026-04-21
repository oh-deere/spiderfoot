# Web UI SPA — Milestone 4c (Graph tab + scaninfo retirement) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Graph tab PlaceholderTab with an SVG renderer backed by `@visx/network` + `d3-force`. Retire `scaninfo_legacy` handler, `scaninfo.tmpl`, `viz.js`. Close the /scaninfo migration — after M4c, `/scaninfo-legacy` returns 404 and the SPA owns all six tabs.

**Architecture:** 6 tasks. Dependencies + typed API land first, then the force-layout hook, then the renderer component, then the composing GraphTab that wires into ScanInfoPage, then the Python/template retirement + Playwright, docs close out.

**Tech Stack:** React 19, Mantine 9, TanStack Query 5, @visx/network 3, @visx/zoom 3, @visx/responsive 3, d3-force 3, React Router 7, Vitest 2, Playwright 1.

**Spec:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-4c-design.md`.

---

## File Structure

### Frontend (React)
- **Modify** `webui/package.json` — add `@visx/network`, `@visx/zoom`, `@visx/responsive`, `d3-force`, `@types/d3-force`.
- **Modify** `webui/src/types.ts` — add `GraphNode`, `GraphEdge`, `GraphPayload`, `GraphLayoutMode`.
- **Modify** `webui/src/api/scaninfo.ts` — add `fetchScanGraph(id)`.
- **Modify** `webui/src/api/scaninfo.test.ts` — add 1 Vitest case for `fetchScanGraph`.
- **Create** `webui/src/pages/scaninfo/graph/useForceLayout.ts` — custom hook running d3-force.
- **Create** `webui/src/pages/scaninfo/GraphRenderer.tsx` — SVG + pan/zoom + PNG export.
- **Create** `webui/src/pages/scaninfo/GraphTab.tsx` — top-level tab body (fallback + empty + renderer).
- **Create** `webui/src/pages/scaninfo/GraphTab.test.tsx` — 3 Vitest cases.
- **Modify** `webui/src/pages/ScanInfoPage.tsx` — swap `PlaceholderTab tabLabel="Graph"` for `<GraphTab id={id} />`.
- **Modify** `webui/src/pages/ScanInfoPage.test.tsx` — remove the "Graph placeholder" test (now meaningless).

### Backend + retirements (Python / templates)
- **Modify** `sfwebui.py` — delete `scaninfo_legacy()` handler.
- **Delete** `spiderfoot/templates/scaninfo.tmpl` (905 lines).
- **Delete** `spiderfoot/static/js/viz.js` (387 lines).
- **Modify** `spiderfoot/templates/HEADER.tmpl` — remove the `<script src="${docroot}/static/js/viz.js">` line.
- **Modify** `test/unit/test_spiderfootwebui.py` — delete `test_scaninfo_legacy`.
- **Modify** `test/integration/test_sfwebui.py` — delete `test_scaninfo_legacy_invalid_scan_returns_200`.

### E2E
- **Create** `webui/tests/e2e/07-scaninfo-graph.spec.ts` — 1 Playwright case.

### Docs
- **Modify** `CLAUDE.md` — Web UI paragraph updated for M4c completion.
- **Modify** `docs/superpowers/BACKLOG.md` — mark M4c shipped.

---

## Context for the implementer

- **Branch:** master, direct commits. HEAD is b508afad (M4c spec commit).
- **Baseline:** 66 Vitest + 14 Playwright + flake8 clean + 1466 pytest + 34 skipped.
- **No new Python endpoints** — `/scanviz?id=X&gexf=0` and `/scanviz?id=X&gexf=1` are unchanged.
- **`/scanviz?id=X&gexf=0` response shape** (see `spiderfoot/helpers.py:484` `buildGraphJson`):
  ```json
  {
    "nodes": [{"id": "1", "label": "example.com", "x": 123, "y": 456, "size": "1", "color": "#f00"}, ...],
    "edges": [{"id": "1", "source": "1", "target": "2"}, ...]
  }
  ```
  Root node has `color: "#f00"`. Others: `"#000"`. We derive `isRoot` from the color and ignore the backend's `x/y` (random on the server; we run d3-force ourselves).
- **ScanInfoPage's existing structure** (after M4b):
  ```
  webui/src/pages/scaninfo/
    BrowseTab.tsx + BrowseTab.test.tsx
    CorrelationRiskBadge.tsx
    CorrelationsList.tsx
    CorrelationsTab.tsx + CorrelationsTab.test.tsx
    EventList.tsx
    EventTypeList.tsx
    InfoTab.tsx
    LogTab.tsx
    PlaceholderTab.tsx       (unused after M4c — can be deleted, but leaving it to keep diffs tight; deletes in final sweep)
    StatusTab.tsx
  ```
  M4c adds: `GraphTab.tsx` + `GraphTab.test.tsx` + `GraphRenderer.tsx` + `graph/useForceLayout.ts`.
- **Mantine v9 + @visx/zoom compatibility:** both are React-18+ and React-19-compatible. No peer-dep warnings expected.
- **d3-force 3.x API:** `forceSimulation`, `forceLink`, `forceManyBody`, `forceCenter`. Synchronous iteration via `simulation.tick(N)` + `simulation.stop()`.
- **Bundle size budget:** current bundle is ~630KB JS. Adding `@visx/*` (~30KB) + `d3-force` (~30KB) pushes to ~690KB. Chunk-size warning threshold is 500KB; we've been above it since M2. No action required; the warning is pre-existing.
- **`@typescript-eslint/no-explicit-any`** is active — use `Mock` from vitest.
- **`erasableSyntaxOnly: true`** in tsconfig — use `import type` for type-only imports.

---

## Task 1: Dependencies + types + API + 1 Vitest case

**Files:**
- Modify: `webui/package.json` + `webui/package-lock.json` (via `npm install`).
- Modify: `webui/src/types.ts` — add 4 types.
- Modify: `webui/src/api/scaninfo.ts` — add `fetchScanGraph`.
- Modify: `webui/src/api/scaninfo.test.ts` — add 1 Vitest case.

### Step 1: Install dependencies

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui
npm install @visx/network @visx/zoom @visx/responsive d3-force
npm install -D @types/d3-force
```

Confirm `package.json` gains four runtime deps + one devDep.

### Step 2: Extend `webui/src/types.ts`

Append (same-file references for existing types):

```typescript
export type GraphNode = {
  id: string;
  label: string;
  isRoot: boolean;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
};

export type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type GraphLayoutMode = 'force' | 'random';
```

### Step 3: Extend `webui/src/api/scaninfo.ts`

Update the top-of-file `import type` to include the new types:

```typescript
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
  GraphPayload,
} from '../types';
```

Append `fetchScanGraph` at the bottom of the file:

```typescript
type ScanGraphRaw = {
  nodes: Array<{
    id: string;
    label: string;
    x: number;
    y: number;
    size: string;
    color: string;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
  }>;
};

export async function fetchScanGraph(id: string): Promise<GraphPayload> {
  const raw = await fetchJson<ScanGraphRaw>(
    `/scanviz?id=${encodeURIComponent(id)}&gexf=0`,
  );
  return {
    nodes: raw.nodes.map((n) => ({
      id: n.id,
      label: n.label,
      isRoot: n.color === '#f00',
    })),
    edges: raw.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
    })),
  };
}
```

### Step 4: Extend `webui/src/api/scaninfo.test.ts`

Add `fetchScanGraph` to the top-of-file import. At the end of the file, append:

```typescript
describe('fetchScanGraph', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps {nodes, edges} with color-based isRoot derivation', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify({
          nodes: [
            { id: '1', label: 'example.com', x: 10, y: 20, size: '1', color: '#f00' },
            { id: '2', label: 'subdomain', x: 30, y: 40, size: '1', color: '#000' },
          ],
          edges: [
            { id: '1', source: '1', target: '2' },
          ],
        }),
        { status: 200 },
      ),
    );
    const result = await fetchScanGraph('abc');
    expect(result.nodes).toEqual([
      { id: '1', label: 'example.com', isRoot: true },
      { id: '2', label: 'subdomain', isRoot: false },
    ]);
    expect(result.edges).toEqual([
      { id: '1', source: '1', target: '2' },
    ]);
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/scanviz?id=abc&gexf=0');
  });
});
```

### Step 5: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **66 existing + 1 new = 67 passing**.

### Step 6: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

Expected: success. Chunk-size warning is pre-existing.

### Step 7: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/package.json webui/package-lock.json webui/src/types.ts webui/src/api/scaninfo.ts webui/src/api/scaninfo.test.ts
git commit -m "$(cat <<'EOF'
webui: graph API + types + deps for GraphTab

Adds runtime deps for the M4c Graph tab:
- @visx/network, @visx/zoom, @visx/responsive (declarative React
  wrappers around D3 for SVG graph + pan/zoom)
- d3-force (force-directed layout simulation)
- @types/d3-force (devDep)

Types: GraphNode / GraphEdge / GraphPayload / GraphLayoutMode.

fetchScanGraph(id) wraps /scanviz?id=X&gexf=0, deriving isRoot
from the backend's color flag and dropping the random x/y (we
run our own d3-force layout client-side).

1 Vitest case covers the shape mapping + URL encoding.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4c-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: useForceLayout hook

**Files:**
- Create: `webui/src/pages/scaninfo/graph/useForceLayout.ts`.

### Step 1: Create the hook

```typescript
import { useMemo } from 'react';
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
} from 'd3-force';
import type { GraphNode, GraphEdge, GraphLayoutMode } from '../../../types';

type Position = { x: number; y: number };

export type LayoutResult = {
  positions: Map<string, Position>;  // node.id -> {x, y}
  bounds: { width: number; height: number };
};

const RANDOM_SEED_WIDTH = 1000;
const RANDOM_SEED_HEIGHT = 1000;
const FORCE_ITERATIONS = 300;
const FORCE_LINK_DISTANCE = 80;
const FORCE_CHARGE_STRENGTH = -200;
const FORCE_CENTER_X = 500;
const FORCE_CENTER_Y = 500;

export function useForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  mode: GraphLayoutMode,
): LayoutResult {
  return useMemo(() => {
    if (nodes.length === 0) {
      return {
        positions: new Map(),
        bounds: { width: RANDOM_SEED_WIDTH, height: RANDOM_SEED_HEIGHT },
      };
    }

    if (mode === 'random') {
      const positions = new Map<string, Position>();
      for (const node of nodes) {
        positions.set(node.id, {
          x: Math.random() * RANDOM_SEED_WIDTH,
          y: Math.random() * RANDOM_SEED_HEIGHT,
        });
      }
      return {
        positions,
        bounds: { width: RANDOM_SEED_WIDTH, height: RANDOM_SEED_HEIGHT },
      };
    }

    // mode === 'force'
    type SimNode = GraphNode & { x?: number; y?: number; index?: number };
    type SimLink = { source: string | SimNode; target: string | SimNode };

    const simNodes: SimNode[] = nodes.map((n) => ({ ...n }));
    const simLinks: SimLink[] = edges.map((e) => ({
      source: e.source,
      target: e.target,
    }));

    const sim = forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(FORCE_LINK_DISTANCE),
      )
      .force('charge', forceManyBody().strength(FORCE_CHARGE_STRENGTH))
      .force('center', forceCenter(FORCE_CENTER_X, FORCE_CENTER_Y))
      .stop();

    sim.tick(FORCE_ITERATIONS);

    const positions = new Map<string, Position>();
    for (const node of simNodes) {
      positions.set(node.id, {
        x: node.x ?? FORCE_CENTER_X,
        y: node.y ?? FORCE_CENTER_Y,
      });
    }

    // Derive bounds from node positions so the renderer can set viewBox.
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const p of positions.values()) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    return {
      positions,
      bounds: {
        width: Math.max(1, maxX - minX),
        height: Math.max(1, maxY - minY),
      },
    };
  }, [nodes, edges, mode]);
}
```

### Step 2: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

Expected: success.

### Step 3: Vitest — baseline stays green (no new tests for the hook)

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -4
```

Expected: 67 passing.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/scaninfo/graph/useForceLayout.ts
git commit -m "$(cat <<'EOF'
webui: useForceLayout hook — d3-force simulation to convergence

Synchronous layout for /scanviz graph data. On mode='force',
runs d3's forceSimulation with link + charge + center forces,
ticks 300 iterations, and returns a Map<node.id, {x, y}>.
On mode='random', scatters nodes uniformly in [0, 1000].

No animated ticking — one-shot converge to keep React renders
minimal. A 100-400ms main-thread block on typical scans is
acceptable for a one-time layout; the Loader state covers it.

Tests: transitively through GraphTab.test.tsx in Task 4.
Testing d3-force under jsdom would need timer stubs for
deterministic output and isn't worth the complexity.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4c-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: GraphRenderer component

**Files:**
- Create: `webui/src/pages/scaninfo/GraphRenderer.tsx`.

### Step 1: Create the component

```tsx
import { useRef } from 'react';
import { Button, Group } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { ParentSize } from '@visx/responsive';
import { Zoom } from '@visx/zoom';
import { Graph, DefaultLink, DefaultNode } from '@visx/network';
import type { GraphNode, GraphEdge } from '../../types';
import type { LayoutResult } from './graph/useForceLayout';

const ROOT_COLOR = '#f00';
const NODE_COLOR = '#228be6';
const EDGE_COLOR = '#ccc';

type NetworkNode = GraphNode & { x: number; y: number };
type NetworkLink = { source: NetworkNode; target: NetworkNode };

function exportSvgAsPng(svgEl: SVGSVGElement, filename: string): Promise<void> {
  const serialized = new XMLSerializer().serializeToString(svgEl);
  const svgBlob = new Blob([serialized], {
    type: 'image/svg+xml;charset=utf-8',
  });
  const url = URL.createObjectURL(svgBlob);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = svgEl.clientWidth || 1000;
      canvas.height = svgEl.clientHeight || 600;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        URL.revokeObjectURL(url);
        reject(new Error('Canvas 2d context unavailable'));
        return;
      }
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => {
        if (!blob) return reject(new Error('PNG export failed'));
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
        resolve();
      }, 'image/png');
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('SVG -> image load failed'));
    };
    img.src = url;
  });
}

export function GraphRenderer({
  nodes,
  edges,
  layout,
  scanId,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layout: LayoutResult;
  scanId: string;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Build fully-typed network shape for visx.
  const networkNodes: NetworkNode[] = nodes.map((n) => {
    const pos = layout.positions.get(n.id) ?? { x: 0, y: 0 };
    return { ...n, x: pos.x, y: pos.y };
  });
  const nodeById = new Map<string, NetworkNode>();
  for (const n of networkNodes) nodeById.set(n.id, n);
  const networkLinks: NetworkLink[] = edges
    .map((e) => {
      const source = nodeById.get(e.source);
      const target = nodeById.get(e.target);
      if (!source || !target) return null;
      return { source, target };
    })
    .filter((x): x is NetworkLink => x !== null);

  return (
    <>
      <Group justify="flex-end" mb="sm">
        <Button
          variant="light"
          leftSection={<IconDownload size={14} />}
          onClick={() => {
            if (!svgRef.current) return;
            void exportSvgAsPng(svgRef.current, `scan-graph-${scanId}.png`);
          }}
        >
          Download PNG
        </Button>
        <Button
          component="a"
          href={`/scanviz?id=${encodeURIComponent(scanId)}&gexf=1`}
          variant="light"
          leftSection={<IconDownload size={14} />}
        >
          Download GEXF
        </Button>
      </Group>
      <div style={{ width: '100%', height: 600, border: '1px solid #e9ecef', borderRadius: 4 }}>
        <ParentSize>
          {({ width, height }) => (
            <Zoom<SVGSVGElement>
              width={width}
              height={height}
              scaleXMin={0.1}
              scaleXMax={10}
              scaleYMin={0.1}
              scaleYMax={10}
            >
              {(zoom) => (
                <svg
                  ref={svgRef}
                  width={width}
                  height={height}
                  style={{ cursor: zoom.isDragging ? 'grabbing' : 'grab' }}
                  onWheel={zoom.handleWheel}
                  onMouseDown={zoom.dragStart}
                  onMouseMove={zoom.dragMove}
                  onMouseUp={zoom.dragEnd}
                  onMouseLeave={() => {
                    if (zoom.isDragging) zoom.dragEnd();
                  }}
                >
                  <rect width={width} height={height} fill="#fff" />
                  <g transform={zoom.toString()}>
                    <Graph<NetworkLink, NetworkNode>
                      graph={{ nodes: networkNodes, links: networkLinks }}
                      linkComponent={({ link }) => (
                        <DefaultLink
                          link={link}
                          stroke={EDGE_COLOR}
                          strokeWidth={1}
                        />
                      )}
                      nodeComponent={({ node }) => (
                        <g>
                          <DefaultNode
                            cx={0}
                            cy={0}
                            r={6}
                            fill={node.isRoot ? ROOT_COLOR : NODE_COLOR}
                          />
                          <text
                            x={10}
                            y={4}
                            fontSize={10}
                            fill="#333"
                          >
                            {node.label.length > 24
                              ? `${node.label.slice(0, 24)}…`
                              : node.label}
                          </text>
                        </g>
                      )}
                    />
                  </g>
                </svg>
              )}
            </Zoom>
          )}
        </ParentSize>
      </div>
    </>
  );
}
```

### Step 2: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

Expected: success. The build may surface type errors from @visx — if so, adjust the generic parameters passed to `<Graph>` or `<Zoom>`. The shape above matches @visx 3.x docs.

### Step 3: Vitest — baseline stays green

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -4
```

Expected: 67 passing.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/scaninfo/GraphRenderer.tsx
git commit -m "$(cat <<'EOF'
webui: GraphRenderer — SVG + pan/zoom + PNG/GEXF export

Takes layout positions from useForceLayout and renders the scan
graph inside an SVG wrapped in @visx/zoom for wheel-zoom + drag-
to-pan. Nodes color-coded: red for the scan target (isRoot),
brand-blue for everything else. Edge stroke #ccc.

Toolbar:
- Download PNG: serializes the SVG, paints onto a canvas, and
  triggers a blob download. Synchronous; SVG-to-raster always
  captures the current pan/zoom transform.
- Download GEXF: plain <a download> hitting the existing
  /scanviz?id=X&gexf=1 endpoint.

Node labels truncated at 24 chars. Defer node dragging /
click-drill / filter to a follow-up.

Tests: transitively through GraphTab.test.tsx in Task 4.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4c-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: GraphTab + wire into ScanInfoPage + Vitest

**Files:**
- Create: `webui/src/pages/scaninfo/GraphTab.tsx`.
- Create: `webui/src/pages/scaninfo/GraphTab.test.tsx`.
- Modify: `webui/src/pages/ScanInfoPage.tsx` — swap the last `PlaceholderTab`.
- Modify: `webui/src/pages/ScanInfoPage.test.tsx` — remove or retarget the Graph-placeholder test.

### Step 1: Create `webui/src/pages/scaninfo/GraphTab.tsx`

```tsx
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
            <Text size="xs" c="dimmed">●</Text>
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
```

### Step 2: Create `webui/src/pages/scaninfo/GraphTab.test.tsx`

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { GraphTab } from './GraphTab';

describe('GraphTab', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    cleanup();
  });

  function renderTab() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <GraphTab id="abc" />
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockGraph(nodeCount: number) {
    const nodes = Array.from({ length: nodeCount }, (_, i) => ({
      id: String(i + 1),
      label: `node${i + 1}`,
      x: 0,
      y: 0,
      size: '1',
      color: i === 0 ? '#f00' : '#000',
    }));
    const edges =
      nodeCount > 1
        ? [{ id: '1', source: '1', target: '2' }]
        : [];
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url.startsWith('/scanviz')) {
        return Promise.resolve(
          new Response(JSON.stringify({ nodes, edges }), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  it('renders the empty-state Alert when the backend returns zero nodes', async () => {
    mockGraph(0);
    renderTab();
    expect(
      await screen.findByText(/This scan produced no events yet/),
    ).toBeInTheDocument();
  });

  it('renders the large-scan fallback Alert when the backend returns >500 nodes', async () => {
    mockGraph(600);
    renderTab();
    expect(
      await screen.findByText(/Graph too large for interactive render/),
    ).toBeInTheDocument();
    const gexfLink = await screen.findByRole('link', {
      name: /Download GEXF \(600 nodes\)/,
    });
    expect(gexfLink).toHaveAttribute(
      'href',
      '/scanviz?id=abc&gexf=1',
    );
  });

  it('renders the SVG + layout-toggle controls for a small-scan graph', async () => {
    mockGraph(3);
    renderTab();
    // The node count label fires after the query resolves.
    expect(await screen.findByText(/3 nodes, 1 edges/)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Force' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Random' })).toBeInTheDocument();
  });
});
```

### Step 3: Modify `webui/src/pages/ScanInfoPage.tsx`

Add import:

```tsx
import { GraphTab } from './scaninfo/GraphTab';
```

Replace the last remaining PlaceholderTab. Find:

```tsx
<Tabs.Panel value="graph" pt="md">
  <PlaceholderTab tabLabel="Graph" scanId={id} />
</Tabs.Panel>
```

Replace with:

```tsx
<Tabs.Panel value="graph" pt="md">
  <GraphTab id={id} />
</Tabs.Panel>
```

The `PlaceholderTab` import can stay — it's still referenced at import level but unused. If the linter flags an unused import, delete the import line (and the `PlaceholderTab.tsx` file itself).

Actually — since `PlaceholderTab` is no longer used anywhere, delete both the import line and the file:

```bash
git rm webui/src/pages/scaninfo/PlaceholderTab.tsx
```

Remove the `import { PlaceholderTab } from './scaninfo/PlaceholderTab';` line from `ScanInfoPage.tsx`.

### Step 4: Modify `webui/src/pages/ScanInfoPage.test.tsx`

The third test currently asserts the Graph PlaceholderTab renders with a legacy-link href. That test is now stale. Options:
- **A**: Delete it entirely (test file drops from 3 cases to 2).
- **B**: Retarget to assert GraphTab renders — but that requires mocking `/scanviz` in the shell test mocks, which adds noise.

Pick **A**. Remove the third `it(...)` block. The first two tests (initial render + Abort visibility on running) stay.

Also extend the existing `mockStatus` helper to respond to `/scanviz` with an empty response body — the GraphTab loads lazily only when its panel is active, and the remaining two tests don't click the Graph tab. So this may not be strictly necessary. Try the tests without the extension first; add it only if a test hangs.

### Step 5: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **67 existing + 3 new − 1 removed (shell test) = 69 passing**.

### Step 6: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 7: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/scaninfo/GraphTab.tsx webui/src/pages/scaninfo/GraphTab.test.tsx webui/src/pages/ScanInfoPage.tsx webui/src/pages/ScanInfoPage.test.tsx
git rm webui/src/pages/scaninfo/PlaceholderTab.tsx
git commit -m "$(cat <<'EOF'
webui: GraphTab — @visx/network-driven scan-graph view

Wires the new Graph tab into ScanInfoPage. Three states:
1. nodes=0 -> "This scan produced no events yet" Alert.
2. nodes>500 -> large-scan fallback Alert with a Download GEXF
   button; skips interactive rendering entirely.
3. 1..500 nodes -> useForceLayout runs d3-force to convergence,
   GraphRenderer draws an SVG with pan/zoom, PNG/GEXF toolbar,
   and a Force/Random layout SegmentedControl.

Delete PlaceholderTab.tsx — no longer referenced. The M4a
ScanInfoPage test that asserted the Graph placeholder is
removed; the two remaining shell tests (initial render +
Abort visibility) still pass.

3 Vitest cases cover: empty-state, large-scan fallback with
correct GEXF href, small-scan renders the SegmentedControl +
node/edge counts.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4c-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Retire scaninfo_legacy + scaninfo.tmpl + viz.js + HEADER.tmpl + Playwright

**Files:**
- Delete: `spiderfoot/templates/scaninfo.tmpl`.
- Delete: `spiderfoot/static/js/viz.js`.
- Modify: `spiderfoot/templates/HEADER.tmpl` — remove viz.js script tag.
- Modify: `sfwebui.py` — delete `scaninfo_legacy()` handler.
- Modify: `test/unit/test_spiderfootwebui.py` — delete `test_scaninfo_legacy`.
- Modify: `test/integration/test_sfwebui.py` — delete `test_scaninfo_legacy_invalid_scan_returns_200`.
- Create: `webui/tests/e2e/07-scaninfo-graph.spec.ts`.

### Step 1: Delete the Mako template + viz.js

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git rm spiderfoot/templates/scaninfo.tmpl spiderfoot/static/js/viz.js
```

### Step 2: Sanity-check no references remain

```bash
grep -rnE "scaninfo\.tmpl|viz\.js|sf_viz_" --include="*.py" --include="*.tmpl" --include="*.robot" --include="*.html" /Users/olahjort/Projects/OhDeere/spiderfoot
```

Expected matches (all docs / template / sfwebui.py):
- `HEADER.tmpl` still references viz.js (fix in Step 3).
- Maybe `sfwebui.py` mentions `scaninfo.tmpl` in a comment — remove if present.
- Docs files (specs, plans) mention them — leave as history.

### Step 3: Remove viz.js script tag from `HEADER.tmpl`

Edit `/Users/olahjort/Projects/OhDeere/spiderfoot/spiderfoot/templates/HEADER.tmpl`. Find:

```html
<script type='text/javascript' src='${docroot}/static/js/viz.js'></script>
```

Delete that line entirely.

Re-run the grep from Step 2. Expected: only docs files remain.

### Step 4: Delete `scaninfo_legacy()` handler in `sfwebui.py`

```bash
grep -n "def scaninfo_legacy\|scaninfo_legacy" /Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py
```

Find the method (decorated with `@cherrypy.expose`). Delete the decorator, def line, docstring, and body.

Confirm no other references:

```bash
grep -n "scaninfo_legacy" /Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py
```

Expected: zero.

### Step 5: Delete `test_scaninfo_legacy` from unit tests

Edit `test/unit/test_spiderfootwebui.py`. Find:

```python
def test_scaninfo_legacy(self):
    """Test scaninfo_legacy(self, id) — renders Mako template."""
    ...
```

Delete the entire method.

### Step 6: Delete `test_scaninfo_legacy_invalid_scan_returns_200` from integration tests

Edit `test/integration/test_sfwebui.py`. Find:

```python
def test_scaninfo_legacy_invalid_scan_returns_200(self):
    self.getPage("/scaninfo-legacy?id=doesnotexist")
    self.assertStatus('200 OK')
    self.assertInBody("Scan ID not found.")
```

Delete the entire method.

### Step 7: Run pytest — expect 1464 passing

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1464 passed, 34 skipped** (down from 1466 — two `scaninfo_legacy` tests retired).

### Step 8: Create `webui/tests/e2e/07-scaninfo-graph.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

async function openFinishedScanInfo(
  page: import('@playwright/test').Page,
): Promise<void> {
  await page.goto('/');
  const anchor = page.getByRole('link', { name: 'monthly-recon' });
  await expect(anchor).toBeVisible();
  await anchor.click();
  await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 10_000 });
}

test.describe('Scan info page (M4c: Graph tab)', () => {
  test('Graph tab renders either the empty-state alert or the layout controls', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Graph' }).click();

    // Seeded "monthly-recon" scan has no events -> expect the empty-state
    // Alert. If a future fixture seed adds events, the Force radio should
    // appear instead. Accept both.
    const emptyAlert = page.getByText(/This scan produced no events yet/);
    const forceRadio = page.getByRole('radio', { name: 'Force' });
    await expect(emptyAlert.or(forceRadio)).toBeVisible();
  });
});
```

### Step 9: Run Playwright

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run test:e2e 2>&1 | tail -20
```

Expected: **14 existing + 1 new = 15 passing**.

### Step 10: Full `./test/run` sanity

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 69 Vitest + 15 Playwright + flake8 clean + 1464 pytest / 34 skipped.

### Step 11: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add sfwebui.py spiderfoot/templates/HEADER.tmpl test/unit/test_spiderfootwebui.py test/integration/test_sfwebui.py webui/tests/e2e/07-scaninfo-graph.spec.ts
git rm spiderfoot/templates/scaninfo.tmpl spiderfoot/static/js/viz.js
git commit -m "$(cat <<'EOF'
webui: retire scaninfo_legacy — all six tabs now SPA-native

Deletes the last Mako-era scan-detail path:
- spiderfoot/templates/scaninfo.tmpl (905 lines)
- spiderfoot/static/js/viz.js (387 lines)
- scaninfo_legacy() handler in sfwebui.py
- viz.js <script> reference in HEADER.tmpl

Python test cleanup: test_scaninfo_legacy (unit) and
test_scaninfo_legacy_invalid_scan_returns_200 (integration) are
removed. pytest drops from 1466 to 1464.

Adds 1 Playwright E2E asserting the Graph tab renders either
the empty-state Alert or the Force/Random layout controls
(depends on whether the fixture scan produced events).

After this commit, /scaninfo-legacy returns 404. All six SPA
tabs work natively. Shared chrome (HEADER.tmpl / FOOTER.tmpl /
error.tmpl / spiderfoot.js / sigma + jquery + bootstrap3 etc.)
still lives for self.error() until the final sweep.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4c-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Docs refresh + final verify

**Files:**
- Modify: `CLAUDE.md` — Web UI paragraph updated.
- Modify: `docs/superpowers/BACKLOG.md` — mark M4c shipped.

### Step 1: Update `CLAUDE.md`

Find the Web UI top paragraph:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1–4b (2026-04-20) migrated `/` (scan list), `/newscan` (scan creation), `/opts` (settings), and `/scaninfo` with 5 of 6 tabs (Status, Info, Log, Browse, Correlations). The Graph tab still renders a placeholder that links to the still-Mako `/scaninfo-legacy`; milestone 4c replaces it with @visx/network + d3-force and retires the legacy route. The final sweep retires shared chrome (`HEADER.tmpl`/`FOOTER.tmpl`/`error.tmpl`) alongside.
```

Replace with:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1–4c (2026-04-20) migrated `/` (scan list), `/newscan` (scan creation), `/opts` (settings), and `/scaninfo` with all six tabs (Status, Info, Log, Browse, Correlations, Graph via @visx/network + d3-force). Shared chrome (`HEADER.tmpl` / `FOOTER.tmpl` / `error.tmpl`, plus `spiderfoot.js` and the legacy `spiderfoot/static/node_modules/` bundle) survives until the final-sweep milestone because `self.error()` still renders Mako HTML for legacy form-post error paths.
```

### Step 2: Update `docs/superpowers/BACKLOG.md`

Under `### UI modernization — page-by-page migration` → `**Shipped:**`, append:

```
- Milestone 4c (2026-04-20) — `/scaninfo` Graph tab. React renderer on `@visx/network` + `d3-force` with pan/zoom, PNG+GEXF export, and a >500-node fallback that points at the GEXF download for external graph tools. Retires `scaninfo_legacy` handler, `scaninfo.tmpl` (905 lines), `viz.js` (387 lines), and HEADER.tmpl's viz.js reference. `/scaninfo-legacy` now returns 404.
```

Update the specs glob (e.g. `{1,2,3,4a,4b,4c}`).

Update the **Remaining Mako pages** block — now only the final sweep remains:

```
**Remaining Mako pages to migrate** (each its own spec + plan):
- Final sweep: retires `HEADER.tmpl`, `FOOTER.tmpl`, `error.tmpl`, `spiderfoot.js`, legacy CSS (`spiderfoot.css` / `dark.css`), `spiderfoot/static/node_modules/` (jquery, bootstrap3, d3, sigma, tablesorter, alertifyjs), the Mako TemplateLookup + imports in sfwebui.py, the `self.error()` helper (convert to SPA route or static HTML), and the legacy `/static` CherryPy mount. Also folds in the Clone-scan UX (scan list menu + new JSON endpoint).
```

### Step 3: Final `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 69 Vitest + 15 Playwright + flake8 clean + 1464 pytest / 34 skipped.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — milestone 4c Web UI

Updates the Web UI section to reflect M4c shipped: the Graph tab
now renders via @visx/network + d3-force. All six /scaninfo tabs
are SPA-native. scaninfo_legacy route retired.

BACKLOG.md removes Graph from the remaining list; only the
final-sweep milestone remains (shared chrome, legacy JS/CSS/
node_modules, Mako TemplateLookup, self.error() conversion,
Clone-scan UX).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4c-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 5: Milestone summary

Report:
- Number of commits across M4c.
- SPA scaninfo now has all 6 tabs native.
- /scaninfo-legacy retired.
- Test totals.
- Up next: final-sweep milestone retiring shared chrome + Clone-scan UX.
