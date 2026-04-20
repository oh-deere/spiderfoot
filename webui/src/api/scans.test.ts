import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { listScans, deleteScan } from './scans';
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

  it('handles the "Not yet" sentinel in started/finished for un-started scans', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [
            'abc',
            'queued',
            'example.com',
            '2026-04-20 10:00:00',
            'Not yet',
            'Not yet',
            'CREATED',
            0,
            { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 },
          ],
        ]),
        { status: 200 },
      ),
    );
    const scans = await listScans();
    expect(scans[0].started).toBe('Not yet');
    expect(scans[0].finished).toBe('Not yet');
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
