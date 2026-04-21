import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { fetchJson, ApiError } from './client';

describe('fetchJson', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function initFromLastCall(): RequestInit {
    const call = (globalThis.fetch as Mock).mock.calls[0];
    return (call?.[1] ?? {}) as RequestInit;
  }

  it('sends Accept: application/json by default', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('{}', { status: 200 }),
    );
    await fetchJson('/x');
    const headers = initFromLastCall().headers as Record<string, string>;
    expect(headers.Accept).toBe('application/json');
  });

  it('preserves Accept when caller provides Content-Type — regression for legacy-Mako fallback bug', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('{}', { status: 200 }),
    );
    await fetchJson('/x', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'a=1',
    });
    const init = initFromLastCall();
    const headers = init.headers as Record<string, string>;
    expect(headers.Accept).toBe('application/json');
    expect(headers['Content-Type']).toBe('application/x-www-form-urlencoded');
    expect(init.method).toBe('POST');
  });

  it('caller Accept overrides the default', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('<html/>', { status: 200, headers: { 'Content-Type': 'text/html' } }),
    );
    // We expect the call to fail because the body is HTML; we just want the
    // pre-request header check. Use a 200 response so fetchJson tries to parse
    // JSON; the test will catch that and not rethrow.
    await expect(
      fetchJson('/x', { headers: { Accept: 'text/html' } }),
    ).rejects.toBeDefined();
    const headers = initFromLastCall().headers as Record<string, string>;
    expect(headers.Accept).toBe('text/html');
  });

  it('caller credentials overrides the same-origin default', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('{}', { status: 200 }),
    );
    await fetchJson('/x', { credentials: 'omit' });
    expect(initFromLastCall().credentials).toBe('omit');
  });

  it('wraps non-2xx responses in ApiError', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('boom', { status: 500 }),
    );
    await expect(fetchJson('/x')).rejects.toBeInstanceOf(ApiError);
  });
});
