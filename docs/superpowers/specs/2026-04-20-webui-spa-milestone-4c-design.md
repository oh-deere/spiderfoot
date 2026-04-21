# Web UI SPA — Milestone 4c (`/scaninfo` Graph + retire scaninfo-legacy) Design

**Date:** 2026-04-20
**Builds on:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2,3,4a,4b}-design.md`
**Scope:** Third and final `/scaninfo` sub-milestone. Replaces the Graph tab placeholder with a React renderer backed by `@visx/network` + `d3-force`. Retires `scaninfo_legacy` handler, `scaninfo.tmpl`, and `viz.js`. Shared chrome (`HEADER.tmpl` / `FOOTER.tmpl` / `error.tmpl`) survives until the final-sweep milestone because `self.error()` still renders Mako.

---

## Goal

Graph tab that renders the scan's node/edge graph in the SPA with the same functional surface as the Mako Sigma.js implementation (random / force-directed layout, pan + zoom, PNG export, GEXF download), plus a clean fallback for large scans where SVG rendering would be unusable.

---

## Architecture

### Backend — `sfwebui.py`

**No new endpoints.** Both graph data endpoints already ship:

- `GET /scanviz?id=X&gexf=0` → JSON `{nodes, edges}`:
  - `nodes: [{id: string, label: string, x: int, y: int, size: string, color: string}, ...]` — backend seeds random x/y; we ignore those.
  - `edges: [{id: string, source: string, target: string}, ...]`.
- `GET /scanviz?id=X&gexf=1` → GEXF file download.

**Retirements in `sfwebui.py`:**

1. Delete the `scaninfo_legacy()` handler (renamed from the original `scaninfo()` in M4a). No code path left reaches it after M4c.
2. The `error()` helper (`self.error()` Mako renderer) stays — still used by `savesettings()` non-JSON error paths. Retires in the final sweep.

### Frontend — `webui/`

**New dependencies:**
```bash
npm install @visx/network @visx/responsive @visx/zoom d3-force
npm install -D @types/d3-force
```

Bundle-size impact: `@visx/*` packages are small tree-shakable React wrappers (~30KB total for network + responsive + zoom). `d3-force` is ~30KB gzipped. Net add ≈ 60KB to the already-500KB Vite bundle.

**New files:**
- `webui/src/api/scaninfo.ts` — extend with `fetchScanGraph(id)` returning a typed `GraphPayload`.
- `webui/src/pages/scaninfo/GraphTab.tsx` — top-level Graph tab. Node-count guard + d3-force layout + visx render.
- `webui/src/pages/scaninfo/GraphRenderer.tsx` — the actual SVG + pan/zoom/render. Split from GraphTab for testability and to keep each file focused.
- `webui/src/pages/scaninfo/graph/useForceLayout.ts` — custom hook: takes nodes + edges + mode → returns `{ positions: Map<id, {x, y}>, running }`. Runs d3-force-simulation on mount + on mode change.

**Modified files:**
- `webui/src/types.ts` — add `GraphNode`, `GraphEdge`, `GraphPayload`, `GraphLayoutMode`.
- `webui/src/pages/ScanInfoPage.tsx` — swap the final `PlaceholderTab tabLabel="Graph"` for `<GraphTab id={id} />`.
- `webui/src/pages/ScanInfoPage.test.tsx` — remove the test that asserted the Graph placeholder (Task 5's retargeted test becomes unnecessary; either delete it or replace with a smoke test that asserts `<GraphTab>` rendered without needing backend data, e.g. by mocking `/scanviz` empty).

**Retirements (same commit as the GraphTab ships):**
- Delete `spiderfoot/templates/scaninfo.tmpl`.
- Delete `spiderfoot/static/js/viz.js`.
- Remove `<script src="${docroot}/static/js/viz.js">` from `spiderfoot/templates/HEADER.tmpl`.
- Delete `scaninfo_legacy` handler from `sfwebui.py`.
- Remove `test_scaninfo_legacy*` tests (unit + integration) from `test/unit/test_spiderfootwebui.py` and `test/integration/test_sfwebui.py`.
- Leave `sigma` node_modules and `spiderfoot.js` alive — they only matter for `error.tmpl`, which stays until the final sweep.

Actually, re-checking: `sigma` is loaded only by `scaninfo.tmpl` (lines 68-72). Once `scaninfo.tmpl` is deleted, nothing references sigma. But `spiderfoot/static/node_modules/` is a shared bundle directory; surgical deletion of sigma specifically is fine but defer to the final sweep to delete everything under `node_modules/` cleanly. M4c does **not** touch `spiderfoot/static/node_modules/`.

### Data flow

```
Browser GET /scaninfo?id=X
  → CherryPy scaninfo() → _serve_spa_shell()
  → React Router mounts ScanInfoPage
  → User clicks Graph tab
  → GraphTab mounts
  → fetchScanGraph(id) hits /scanviz?id=X&gexf=0 → { nodes, edges }
  → If nodes.length > 500: show fallback Alert with GEXF-download button.
  → Else: useForceLayout(nodes, edges, mode) runs d3-force-simulation
    to convergence (~300 iterations), returns positions Map.
  → GraphRenderer draws visx <Graph> inside <svg>, wrapped with @visx/zoom
    for pan + wheel-zoom. PNG export button serializes SVG → canvas → blob.
```

### Typed UI shapes

```typescript
export type GraphNode = {
  id: string;
  label: string;
  isRoot: boolean;     // derived from backend's color === '#f00'
};

export type GraphEdge = {
  id: string;
  source: string;      // GraphNode.id
  target: string;      // GraphNode.id
};

export type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type GraphLayoutMode = 'force' | 'random';
```

### Layout algorithm

`useForceLayout(nodes, edges, mode)` — internal custom hook:

```typescript
import { forceSimulation, forceLink, forceManyBody, forceCenter } from 'd3-force';

// On mount or mode change:
if (mode === 'random') {
  // Assign uniformly-random x,y in [0, 1000] for each node. No sim.
} else {
  // Force-directed:
  //   forceSimulation(nodesAsD3Input)
  //     .force('link', forceLink(edges).id(n => n.id).distance(80))
  //     .force('charge', forceManyBody().strength(-200))
  //     .force('center', forceCenter(500, 500))
  //     .stop();
  //   Run 300 ticks synchronously (.tick(300)).
  //   Snapshot node.x and node.y into the returned Map.
}
```

Synchronous iteration (not `setInterval`-driven animation) avoids per-tick React re-renders. One render after convergence.

### Rendering

`GraphRenderer` is a `<ParentSize>` wrapping `<Zoom>` wrapping `<svg>`:

```tsx
<ParentSize>
  {({ width, height }) => (
    <Zoom width={width} height={height} scaleMin={0.1} scaleMax={10}>
      {({ transformMatrix, handleWheel, dragStart, dragMove, dragEnd, isDragging }) => (
        <svg width={width} height={height} onWheel={handleWheel}
             onMouseDown={dragStart} onMouseMove={dragMove}
             onMouseUp={dragEnd} onMouseLeave={dragEnd}>
          <rect width={width} height={height} fill="transparent" />
          <Graph
            graph={{ nodes: positionedNodes, links: mappedLinks }}
            transform={toTransformString(transformMatrix)}
            linkComponent={SimpleLink}
            nodeComponent={SimpleNode}
          />
        </svg>
      )}
    </Zoom>
  )}
</ParentSize>
```

### UX details

- **Toolbar**: top of the tab, `Group` with:
  - `SegmentedControl` `[Force | Random]` — changing fires `setMode`, triggers hook re-run.
  - `Button` "Download PNG" — serializes current SVG + paints to canvas + `canvas.toBlob(blob => downloadBlob(blob, 'scan-graph.png'))`.
  - `Button component="a"` "Download GEXF" → `href="/scanviz?id=${id}&gexf=1"` with `download` attr.
- **Node color**: `isRoot` → red (`#f00`); others → Mantine `primaryColor` (the ohdeereBlue from milestone 1's theme, shade 6 → `#228be6`).
- **Node label**: small text below the circle, truncated at 24 chars with ellipsis.
- **Edge**: stroke `#ccc`, stroke-width 1.
- **Legend**: small Mantine `Group` under the toolbar: "● Target · ● Other data".
- **Large-scan fallback** (> 500 nodes):
  ```
  Mantine Alert (color="blue"):
    "This graph has {n} nodes — the SPA caps interactive rendering at 500
    for performance. Download the GEXF file below and open it in a
    dedicated graph tool (Gephi, Cytoscape) for a usable view of larger
    scans."
    <Button component="a" href="/scanviz?id=X&gexf=1" download>
      Download GEXF ({n} nodes)
    </Button>
  ```
  Threshold `500` is a module-level constant; easy to revisit when it bites.

- **Empty-scan state**: `nodes.length === 0` → `<Alert color="gray">This scan produced no events yet.</Alert>`.

### PNG export

No animation during export. Synchronous path:

```typescript
function exportSvgAsPng(svgEl: SVGSVGElement, filename: string): Promise<void> {
  const serialized = new XMLSerializer().serializeToString(svgEl);
  const svgBlob = new Blob([serialized], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svgBlob);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = svgEl.clientWidth;
      canvas.height = svgEl.clientHeight;
      const ctx = canvas.getContext('2d')!;
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
```

Triggered on click via a `useRef<SVGSVGElement>` attached to the `<svg>`.

---

## Testing

### Vitest — ~4 new cases

`api/scaninfo.test.ts`:
1. `fetchScanGraph` unwraps `{nodes, edges}` into typed `GraphPayload`; derives `isRoot` from `color === '#f00'`.

`pages/scaninfo/GraphTab.test.tsx`:
2. Renders the large-scan fallback Alert when the backend returns > 500 nodes.
3. Renders the empty-state Alert when the backend returns zero nodes.
4. Renders a `<svg>` + both layout-toggle radios when 1-500 nodes are present. (Smoke-level — doesn't assert node coordinates.)

No Vitest for the `useForceLayout` hook directly — it's tested transitively through GraphTab, and d3-force under jsdom would need timer stubs to be deterministic. The spec-compliance reviewer can verify it works by reading the hook.

### Playwright — 1 new case in `07-scaninfo-graph.spec.ts`

1. Navigate to `/scaninfo?id=<finished-scan-guid>`, click Graph tab, assert the toolbar's `Force` / `Random` segmented control is visible AND at least one of: an `<svg>` element (happy path) OR the empty-state Alert (seeded scan may have zero nodes in its graph).

Hard to assert the force-sim converged to meaningful positions against a live fixture; stick to the render-level smoke test.

### Python retirement cleanup

- Delete `test_scaninfo_legacy_invalid_scan_returns_200` integration test (it targets the retired route).
- Delete `test_scaninfo_legacy` unit test (it calls the retired handler).
- pytest baseline drops by 2: **1466 → 1464**. Report the delta explicitly in the commit message.

---

## Rollout

Single milestone, single push to master. `/scaninfo-legacy` returns 404 after M4c — the SPA's placeholder previously pointed there; with M4c all six tabs are SPA-native so the placeholder is deleted too.

Users hitting `/scaninfo?id=X&tab=graph` via a bookmark never worked (the Mako page wasn't URL-deep-linkable anyway). The SPA still uses local state for tab selection; no regression.

---

## Risks

- **Huge SVG bundle.** 500 nodes + thousands of edges = several MB of SVG DOM. Modern browsers handle this fine but startup latency is noticeable (~500ms for 500/2000). Large-scan fallback (Alert at threshold) mitigates. For even smaller scans, keep one eye on PNG export — canvas paint time scales with SVG size.
- **d3-force synchronous block.** Running 300 iterations of force-simulation synchronously blocks the main thread for 100-400ms on typical scans. Acceptable for a one-time layout; a loading spinner covers the gap. If this becomes a pain, wrap in `useTransition` or move to an OffscreenCanvas worker as a post-retirement polish.
- **Pan/zoom transform + d3-force coordinate frame.** visx's `<Zoom>` applies an SVG transform on the whole group; nodes need coordinates in the "natural" (pre-transform) coordinate space. `useForceLayout` produces those directly, so no conversion needed.
- **Node dragging missing.** Mako had drag-to-reposition via sigma's `plugins.dragNodes`. We're not shipping it. If users complain, it's a ~30-line pointer-handler addition.
- **GEXF download reliance.** Large-scan fallback depends on `/scanviz?id=X&gexf=1`. That endpoint exists and is fine; just flagging the dependency.
- **HEADER.tmpl surgery.** Removing the viz.js reference is a one-line diff; no functional change to error.tmpl rendering since viz.js was a scaninfo-only helper.

---

## Non-goals

- Node dragging.
- Click-to-drill-into-event.
- Filter-by-event-type toggle on the graph.
- Animated force simulation (one-shot converge only).
- Canvas renderer / WebGL fallback for > 500 nodes.
- Virtualized graph rendering.
- Legend customization / color-by-module.
- Search within the graph.
- Minimap.
- Saving layout to re-open in the same arrangement.
- URL-deep-linkable tab / layout state.
- Migration of `viz.js`'s old bubble / dendrogram / bar-chart helpers (already cut in M4b scope).

---

## Open items — none

Brainstorming settled:
1. Scope = layout toggle + pan/zoom + PNG + GEXF, no drag/click-drill.
2. Convergence model: synchronous to convergence, not animated.
3. Large-scan fallback: Mantine Alert + GEXF link at > 500 nodes.
4. Library choice: `@visx/network` + `d3-force` + `@visx/zoom` + `@visx/responsive`.
