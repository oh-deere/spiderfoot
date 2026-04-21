import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { Notifications, cleanNotifications } from '@mantine/notifications';
import { BrowseTab } from './BrowseTab';

describe('BrowseTab', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    cleanNotifications();
    cleanup();
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
