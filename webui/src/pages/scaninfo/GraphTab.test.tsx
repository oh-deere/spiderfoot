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
