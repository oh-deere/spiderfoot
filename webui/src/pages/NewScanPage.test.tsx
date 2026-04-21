import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { NewScanPage } from './NewScanPage';

describe('NewScanPage', () => {
  const originalFetch = globalThis.fetch;
  const originalLocation = window.location;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, href: '' },
      writable: true,
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
      writable: true,
    });
  });

  function renderPage() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/newscan']}>
            <NewScanPage />
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockApi(modules: unknown, types: unknown) {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url === '/modules') {
        return Promise.resolve(
          new Response(JSON.stringify(modules), { status: 200 }),
        );
      }
      if (url === '/eventtypes') {
        return Promise.resolve(
          new Response(JSON.stringify(types), { status: 200 }),
        );
      }
      if (url === '/startscan') {
        return Promise.resolve(
          new Response(JSON.stringify(['SUCCESS', 'new-guid']), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  it('renders form, modules, and event types on load', async () => {
    mockApi(
      [
        { name: 'sfp_alpha', descr: 'alpha desc', api_key: false },
        { name: 'sfp_beta', descr: 'beta desc', api_key: true },
      ],
      [['Domain Name', 'DOMAIN_NAME']],
    );
    renderPage();

    expect(await screen.findByLabelText(/Scan Name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Scan Target/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /By Use Case/ })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: /By Module/ }));
    expect(await screen.findByText('sfp_alpha')).toBeInTheDocument();
    expect(screen.getByText('sfp_beta')).toBeInTheDocument();
  });

  it('disables Run Scan when scan name is empty', async () => {
    mockApi([], []);
    renderPage();
    const run = await screen.findByRole('button', { name: 'Run Scan Now' });
    expect(run).toBeDisabled();
  });

  it('submits with modulelist when in module mode', async () => {
    mockApi(
      [{ name: 'sfp_x', descr: 'x', api_key: false }],
      [['Domain Name', 'DOMAIN_NAME']],
    );
    renderPage();
    await screen.findByLabelText(/Scan Name/);

    await userEvent.type(screen.getByLabelText(/Scan Name/), 'myscan');
    await userEvent.type(screen.getByLabelText(/Scan Target/), 'example.com');
    await userEvent.click(screen.getByRole('tab', { name: /By Module/ }));
    await screen.findByText('sfp_x');

    const run = screen.getByRole('button', { name: 'Run Scan Now' });
    await userEvent.click(run);

    await waitFor(() => {
      expect(window.location.href).toBe('/scaninfo?id=new-guid');
    });
    const calls = (globalThis.fetch as Mock).mock.calls.filter(
      (c) => c[0] === '/startscan',
    );
    expect(calls).toHaveLength(1);
    const body = new URLSearchParams(calls[0][1].body);
    expect(body.get('modulelist')).toBe('sfp_x');
    expect(body.get('typelist')).toBe('');
    expect(body.get('usecase')).toBe('');
  });

  it('surfaces an Alert when /startscan returns ERROR', async () => {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url === '/modules') return Promise.resolve(new Response('[]', { status: 200 }));
      if (url === '/eventtypes') return Promise.resolve(new Response('[]', { status: 200 }));
      if (url === '/startscan') {
        return Promise.resolve(
          new Response(JSON.stringify(['ERROR', 'Unrecognised target type.']), {
            status: 200,
          }),
        );
      }
      return Promise.reject(new Error('unexpected'));
    });
    renderPage();
    await screen.findByLabelText(/Scan Name/);
    await userEvent.type(screen.getByLabelText(/Scan Name/), 't');
    await userEvent.type(screen.getByLabelText(/Scan Target/), 'bogus');
    await userEvent.click(screen.getByRole('button', { name: 'Run Scan Now' }));
    expect(
      await screen.findByText('Unrecognised target type.'),
    ).toBeInTheDocument();
  });

  it('prefills the form when navigated with ?clone=<guid>', async () => {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url === '/modules') {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { name: 'sfp_countryname', descr: 'Country name', api_key: false },
              { name: 'sfp_dnsresolve', descr: 'DNS resolver', api_key: false },
            ]),
            { status: 200 },
          ),
        );
      }
      if (url === '/eventtypes') {
        return Promise.resolve(
          new Response(JSON.stringify([['Domain Name', 'DOMAIN_NAME']]), {
            status: 200,
          }),
        );
      }
      if (url.startsWith('/clonescan')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              scanName: 'monthly-recon',
              scanTarget: 'spiderfoot.net',
              modulelist: ['sfp_countryname'],
              typelist: [],
              usecase: '',
            }),
            { status: 200 },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/newscan?clone=abc']}>
            <Routes>
              <Route path="/newscan" element={<NewScanPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );

    const nameInput = await screen.findByLabelText(/Scan Name/);
    expect((nameInput as HTMLInputElement).value).toBe('monthly-recon (clone)');
    const targetInput = screen.getByLabelText(/Scan Target/);
    expect((targetInput as HTMLInputElement).value).toBe('spiderfoot.net');
  });
});
