import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { ScanListPage } from './ScanListPage';

describe('ScanListPage', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function renderPage() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <ModalsProvider>
            <ScanListPage />
          </ModalsProvider>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  it('renders the scan list when query resolves', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            'abc',
            'test',
            'example.com',
            '2026-04-20 10:00:00',
            '2026-04-20 10:00:01',
            '2026-04-20 10:10:00',
            'FINISHED',
            42,
            { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 },
          ],
        ]),
        { status: 200 },
      ),
    );
    renderPage();
    expect(await screen.findByText('test')).toBeInTheDocument();
    expect(await screen.findByText('example.com')).toBeInTheDocument();
    expect(await screen.findByText('FINISHED')).toBeInTheDocument();
  });

  it('renders empty state when no scans', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    renderPage();
    expect(await screen.findByText(/No scans yet/)).toBeInTheDocument();
  });

  it('shows the Alert on fetch failure with a Retry button', async () => {
    (globalThis.fetch as Mock).mockRejectedValue(new TypeError('Network down'));
    renderPage();
    expect(await screen.findByText('Failed to load scans')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('filters to running scans when Running tab is active', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['a', 'done', 'd.example', '2026-04-20 10:00:00',
            '2026-04-20 10:00:01', '2026-04-20 10:10:00', 'FINISHED', 5,
            { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 }],
          ['b', 'alive', 'l.example', '2026-04-20 10:00:00',
            '2026-04-20 10:00:01', 'Not yet', 'RUNNING', 2,
            { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 }],
        ]),
        { status: 200 },
      ),
    );
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('done')).toBeInTheDocument();
    expect(screen.getByText('alive')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Running' }));

    expect(screen.getByText('alive')).toBeInTheDocument();
    expect(screen.queryByText('done')).not.toBeInTheDocument();
  });
});
