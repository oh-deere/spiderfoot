import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ScanInfoPage } from './ScanInfoPage';

describe('ScanInfoPage', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function renderAt(url: string) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <ModalsProvider>
            <MemoryRouter initialEntries={[url]}>
              <Routes>
                <Route path="/scaninfo" element={<ScanInfoPage />} />
              </Routes>
            </MemoryRouter>
          </ModalsProvider>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockStatus(status: string) {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url.startsWith('/scanstatus')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              'my-scan',
              'example.com',
              '2026-04-20 10:00:00',
              '2026-04-20 10:00:01',
              status === 'FINISHED' ? '2026-04-20 10:10:00' : 'Not yet',
              status,
              { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 },
            ]),
            { status: 200 },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  it('renders scan name + status badge + six tab labels', async () => {
    mockStatus('FINISHED');
    renderAt('/scaninfo?id=abc');
    expect(
      await screen.findByRole('heading', { level: 2, name: 'my-scan' }),
    ).toBeInTheDocument();
    expect(screen.getByText('FINISHED')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Status' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Correlations' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Browse' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Graph' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Info' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Log' })).toBeInTheDocument();
  });

  it('hides Abort button on terminal status', async () => {
    mockStatus('FINISHED');
    renderAt('/scaninfo?id=abc');
    await screen.findByRole('heading', { level: 2, name: 'my-scan' });
    expect(screen.queryByRole('button', { name: 'Abort' })).not.toBeInTheDocument();
  });

  it('shows Abort button while running and switching to Correlations tab shows the placeholder with legacy link', async () => {
    mockStatus('RUNNING');
    renderAt('/scaninfo?id=abc');
    await screen.findByRole('heading', { level: 2, name: 'my-scan' });
    expect(screen.getByRole('button', { name: 'Abort' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Correlations' }));
    const legacyLink = await screen.findByRole('link', {
      name: /Open legacy Correlations view/,
    });
    expect(legacyLink).toHaveAttribute('href', '/scaninfo-legacy?id=abc');
  });
});
