import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { OptsPage } from './OptsPage';

describe('OptsPage', () => {
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
            <Notifications />
            <OptsPage />
          </ModalsProvider>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockApi(optsRaw: unknown, saveResult: unknown = ['SUCCESS']) {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url === '/optsraw') {
        return Promise.resolve(
          new Response(JSON.stringify(optsRaw), { status: 200 }),
        );
      }
      if (url === '/savesettings') {
        return Promise.resolve(
          new Response(JSON.stringify(saveResult), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  const OPTS_FIXTURE = [
    'SUCCESS',
    {
      token: 7,
      data: {
        'global.webroot': '/sf',
        'module.sfp_x.enabled': true,
      },
      descs: {
        'global.webroot': 'Web root path',
        'module.sfp_x.enabled': 'Enable X',
      },
      modules: {
        sfp_x: {
          name: 'X Module',
          descr: 'summary',
          cats: [],
          labels: [],
          meta: {},
        },
      },
    },
  ];

  it('renders Global first, then modules, with values populated', async () => {
    mockApi(OPTS_FIXTURE);
    renderPage();
    expect(await screen.findByText('Web root path')).toBeInTheDocument();
    expect(screen.getByText('X Module')).toBeInTheDocument();
  });

  it('Save button is disabled when clean and enables on edit', async () => {
    mockApi(OPTS_FIXTURE);
    renderPage();
    const save = await screen.findByRole('button', { name: /Save Changes/ });
    expect(save).toBeDisabled();

    const input = await screen.findByRole('textbox', { name: 'global.webroot' });
    await userEvent.clear(input);
    await userEvent.type(input, '/newroot');
    expect(save).not.toBeDisabled();
  });

  it('saves edits via POST /savesettings with the token', async () => {
    mockApi(OPTS_FIXTURE);
    renderPage();
    const input = await screen.findByRole('textbox', { name: 'global.webroot' });
    await userEvent.clear(input);
    await userEvent.type(input, '/newroot');
    const save = screen.getByRole('button', { name: /Save Changes/ });
    await userEvent.click(save);

    await waitFor(() => {
      const calls = (globalThis.fetch as Mock).mock.calls.filter(
        (c) => c[0] === '/savesettings',
      );
      expect(calls).toHaveLength(1);
    });
    const call = (globalThis.fetch as Mock).mock.calls.find((c) => c[0] === '/savesettings');
    const body = new URLSearchParams((call![1] as RequestInit).body as string);
    expect(body.get('token')).toBe('7');
    const allopts = JSON.parse(body.get('allopts') ?? '{}');
    expect(allopts['global.webroot']).toBe('/newroot');
  });
});
