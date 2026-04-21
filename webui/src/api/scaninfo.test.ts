import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import {
  fetchScanStatus,
  fetchScanSummary,
  fetchScanLog,
  fetchScanOpts,
  stopScan,
  fetchScanEvents,
  fetchScanEventsUnique,
  searchScanEvents,
  fetchCorrelations,
  toggleFalsePositive,
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

describe('fetchScanEvents', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps the 11-tuple rows to typed ScanEventRow[]', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            '2026-04-20 14:23:01',
            'example.com',
            'root',
            'sfp_dnsresolve',
            'hashA',
            'hashB',
            1_700_000_000,
            'modHashC',
            0,
            'NONE',
            'INTERNET_NAME',
          ],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchScanEvents({ id: 'abc', eventType: 'INTERNET_NAME' });
    expect(rows).toEqual([
      {
        lastSeen: '2026-04-20 14:23:01',
        data: 'example.com',
        sourceData: 'root',
        sourceModule: 'sfp_dnsresolve',
        sourceEventHash: 'hashA',
        hash: 'hashB',
        sourceModuleHash: 'modHashC',
        fp: false,
        risk: 'NONE',
        eventType: 'INTERNET_NAME',
      },
    ]);
  });

  it('passes filterfp=true and eventType on the URL', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await fetchScanEvents({
      id: 'abc',
      eventType: 'IP_ADDRESS',
      filterFp: true,
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe(
      '/scaneventresults?id=abc&eventType=IP_ADDRESS&filterfp=true',
    );
  });

  it('passes correlationId when given', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await fetchScanEvents({ id: 'abc', correlationId: 'corr1' });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/scaneventresults?id=abc&correlationId=corr1');
  });
});

describe('fetchScanEventsUnique', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('uses the /scaneventresultsunique path', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await fetchScanEventsUnique({ id: 'abc', eventType: 'INTERNET_NAME' });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/scaneventresultsunique?id=abc&eventType=INTERNET_NAME');
  });
});

describe('searchScanEvents', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('uses the /search path with url-encoded value', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await searchScanEvents({
      id: 'abc',
      eventType: 'INTERNET_NAME',
      value: 'exa mple.com',
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe(
      '/search?id=abc&eventType=INTERNET_NAME&value=exa+mple.com',
    );
  });
});

describe('fetchCorrelations', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps the 8-tuple rows to typed CorrelationRow[]', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            'corr1',
            'Suspicious co-hosted domains',
            'collect',
            'rule.suspicious.cohost',
            'Suspicious co-host',
            'Triggers when ...',
            'HIGH',
            12,
          ],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchCorrelations('abc');
    expect(rows).toEqual([
      {
        id: 'corr1',
        headline: 'Suspicious co-hosted domains',
        collection: 'collect',
        ruleId: 'rule.suspicious.cohost',
        ruleName: 'Suspicious co-host',
        ruleDescr: 'Triggers when ...',
        ruleRisk: 'HIGH',
        eventsCount: 12,
      },
    ]);
  });
});

describe('toggleFalsePositive', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('sends fp=1 and JSON-encoded resultIds on SUCCESS', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
    );
    await toggleFalsePositive({
      id: 'abc',
      resultIds: ['h1', 'h2'],
      fp: true,
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    const parsed = new URL(url as string, 'http://host');
    expect(parsed.pathname).toBe('/resultsetfp');
    expect(parsed.searchParams.get('id')).toBe('abc');
    expect(parsed.searchParams.get('fp')).toBe('1');
    expect(parsed.searchParams.get('resultids')).toBe('["h1","h2"]');
  });

  it('throws the server message on ERROR', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['ERROR', 'Not allowed']), { status: 200 }),
    );
    await expect(
      toggleFalsePositive({ id: 'abc', resultIds: ['h1'], fp: true }),
    ).rejects.toThrow('Not allowed');
  });
});
