import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { listScans, deleteScan, startScan, fetchScanClone } from './scans';
import { ApiError } from './client';

describe('listScans', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps 9-field positional-tuple response to typed Scan objects', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            'abc',
            'test-scan',
            'example.com',
            '2026-04-20 10:00:00',
            '2026-04-20 10:00:01',
            '2026-04-20 10:10:00',
            'FINISHED',
            42,
            { HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 },
          ],
        ]),
        { status: 200 },
      ),
    );
    const scans = await listScans();
    expect(scans).toEqual([
      {
        guid: 'abc',
        name: 'test-scan',
        target: 'example.com',
        created: '2026-04-20 10:00:00',
        started: '2026-04-20 10:00:01',
        finished: '2026-04-20 10:10:00',
        status: 'FINISHED',
        eventCount: 42,
        riskMatrix: { HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 },
      },
    ]);
  });

  it('handles the "Pending"/"Running" sentinels in started/finished for un-started or running scans', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            'abc',
            'queued',
            'example.com',
            '2026-04-20 10:00:00',
            'Pending',
            'Running',
            'CREATED',
            0,
            { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 },
          ],
        ]),
        { status: 200 },
      ),
    );
    const scans = await listScans();
    expect(scans[0].started).toBe('Pending');
    expect(scans[0].finished).toBe('Running');
  });

  it('returns empty array for empty response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    const scans = await listScans();
    expect(scans).toEqual([]);
  });

  it('throws ApiError on non-2xx', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('nope', { status: 500 }),
    );
    await expect(listScans()).rejects.toBeInstanceOf(ApiError);
  });

  it('throws ApiError on malformed row (too few fields)', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify([['too', 'short']]), { status: 200 }),
    );
    await expect(listScans()).rejects.toBeInstanceOf(ApiError);
  });

  it('propagates network errors', async () => {
    (globalThis.fetch as Mock).mockRejectedValue(new TypeError('Network'));
    await expect(listScans()).rejects.toThrow('Network');
  });
});

describe('deleteScan', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('hits /scandelete with the encoded guid', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('null', { status: 200 }),
    );
    await deleteScan('abc/123');
    const url = (globalThis.fetch as Mock).mock.calls[0][0];
    expect(url).toBe('/scandelete?id=abc%2F123');
  });

  it('throws ApiError when /scandelete returns 400', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('{"error":"scan is running"}', { status: 400 }),
    );
    await expect(deleteScan('abc')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('startScan', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns the scanId on SUCCESS response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS', 'abc-guid']), { status: 200 }),
    );
    const scanId = await startScan({
      scanName: 'test',
      scanTarget: 'example.com',
      mode: 'usecase',
      usecase: 'all',
      moduleList: [],
      typeList: [],
    });
    expect(scanId).toBe('abc-guid');
  });

  it('throws the server message on ERROR response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['ERROR', 'Unrecognised target type.']), { status: 200 }),
    );
    await expect(
      startScan({
        scanName: 'test',
        scanTarget: 'not-a-real-target',
        mode: 'usecase',
        usecase: 'all',
        moduleList: [],
        typeList: [],
      }),
    ).rejects.toThrow('Unrecognised target type.');
  });

  it('sends module mode with modulelist populated and other lists empty', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS', 'abc']), { status: 200 }),
    );
    await startScan({
      scanName: 't',
      scanTarget: 'x',
      mode: 'module',
      usecase: 'all',
      moduleList: ['sfp_alpha', 'sfp_beta'],
      typeList: [],
    });
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('modulelist')).toBe('sfp_alpha,sfp_beta');
    expect(body.get('typelist')).toBe('');
    expect(body.get('usecase')).toBe('');
  });

  it('sends type mode with typelist prefixed "type_" and other lists empty', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS', 'abc']), { status: 200 }),
    );
    await startScan({
      scanName: 't',
      scanTarget: 'x',
      mode: 'type',
      usecase: 'all',
      moduleList: [],
      typeList: ['DOMAIN_NAME', 'IP_ADDRESS'],
    });
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('typelist')).toBe('type_DOMAIN_NAME,type_IP_ADDRESS');
    expect(body.get('modulelist')).toBe('');
  });

  it('sends usecase mode with usecase populated and other lists empty', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS', 'abc']), { status: 200 }),
    );
    await startScan({
      scanName: 't',
      scanTarget: 'x',
      mode: 'usecase',
      usecase: 'Footprint',
      moduleList: [],
      typeList: [],
    });
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('usecase')).toBe('Footprint');
    expect(body.get('modulelist')).toBe('');
    expect(body.get('typelist')).toBe('');
  });

  it('throws on malformed /startscan response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
    );
    await expect(
      startScan({
        scanName: 't',
        scanTarget: 'x',
        mode: 'usecase',
        usecase: 'all',
        moduleList: [],
        typeList: [],
      }),
    ).rejects.toThrow(/Malformed/);
  });
});

describe('fetchScanClone', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('normalizes snake_case modulelist/typelist into camelCase + sane defaults', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify({
          scanName: 'original',
          scanTarget: 'example.com',
          modulelist: ['sfp_countryname', 'sfp_dnsresolve'],
          typelist: [],
          usecase: '',
        }),
        { status: 200 },
      ),
    );
    const result = await fetchScanClone('abc');
    expect(result).toEqual({
      scanName: 'original',
      scanTarget: 'example.com',
      moduleList: ['sfp_countryname', 'sfp_dnsresolve'],
      typeList: [],
      usecase: 'all',
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/clonescan?id=abc');
  });
});
