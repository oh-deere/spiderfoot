import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { cleanNotifications } from '@mantine/notifications';
import { Notifications } from '@mantine/notifications';
import { CorrelationsTab } from './CorrelationsTab';

describe('CorrelationsTab', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    cleanup();
    cleanNotifications();
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
