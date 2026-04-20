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

  it('maps positional-tuple response to typed Scan objects', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['abc', 'test-scan', 'example.com', 1700000000, 1700000001,
            1700000100, 'FINISHED', 42],
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
        createdAt: 1700000000,
        startedAt: 1700000001,
        endedAt: 1700000100,
        status: 'FINISHED',
        eventCount: 42,
      },
    ]);
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
});
