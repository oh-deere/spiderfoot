import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import {
  fetchScanStatus,
  fetchScanSummary,
  fetchScanLog,
  fetchScanOpts,
  stopScan,
} from './scaninfo';
import { ApiError } from './client';

describe('fetchScanStatus', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('unwraps the 7-tuple response into a typed payload', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          'my-scan',
          'example.com',
          '2026-04-20 10:00:00',
          '2026-04-20 10:00:01',
          '2026-04-20 10:10:00',
          'FINISHED',
          { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 2 },
        ]),
        { status: 200 },
      ),
    );
    const result = await fetchScanStatus('abc');
    expect(result).toEqual({
      name: 'my-scan',
      target: 'example.com',
      created: '2026-04-20 10:00:00',
      started: '2026-04-20 10:00:01',
      ended: '2026-04-20 10:10:00',
      status: 'FINISHED',
      riskMatrix: { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 2 },
    });
  });

  it('throws a 404 ApiError when the response is empty', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await expect(fetchScanStatus('missing')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('fetchScanSummary', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps rows to typed ScanSummaryRow[]', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['INTERNET_NAME', 'Internet Name', '2026-04-20 14:23:01', 42, 8, 'FINISHED'],
          ['IP_ADDRESS', 'IP Address', '2026-04-20 14:23:05', 10, 10, 'FINISHED'],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchScanSummary('abc');
    expect(rows).toEqual([
      {
        typeId: 'INTERNET_NAME',
        typeLabel: 'Internet Name',
        lastSeen: '2026-04-20 14:23:01',
        count: 42,
        uniqueCount: 8,
      },
      {
        typeId: 'IP_ADDRESS',
        typeLabel: 'IP Address',
        lastSeen: '2026-04-20 14:23:05',
        count: 10,
        uniqueCount: 10,
      },
    ]);
  });
});

describe('fetchScanLog', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps rows to typed ScanLogEntry[] and sends the default limit', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [1_700_000_000_000, 'sfp_countryname', 'INFO', 'Module started', 'h1'],
          [1_700_000_100_000, 'sfp_countryname', 'DEBUG', 'Hit', 'h2'],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchScanLog('abc');
    expect(rows).toEqual([
      {
        generatedMs: 1_700_000_000_000,
        component: 'sfp_countryname',
        level: 'INFO',
        message: 'Module started',
      },
      {
        generatedMs: 1_700_000_100_000,
        component: 'sfp_countryname',
        level: 'DEBUG',
        message: 'Hit',
      },
    ]);
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/scanlog?id=abc&limit=500');
  });
});

describe('fetchScanOpts', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns the raw payload shape', async () => {
    const payload = {
      meta: ['n', 't', 'c', 's', 'e', 'FINISHED'],
      config: { 'global.webroot': '/sf' },
      configdesc: { 'global.webroot': 'Web root' },
    };
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    const result = await fetchScanOpts('abc');
    expect(result).toEqual(payload);
  });
});

describe('stopScan', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('resolves on empty-string success response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('""', { status: 200 }),
    );
    await expect(stopScan('abc')).resolves.toBeUndefined();
  });

  it('throws on error response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify({ error: { http_status: '400', message: 'Already finished' } }),
        { status: 200 },
      ),
    );
    await expect(stopScan('abc')).rejects.toThrow('Already finished');
  });
});
