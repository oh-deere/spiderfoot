import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { listModules, listEventTypes } from './modules';

describe('listModules', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns typed Module[] with api_key flag preserved', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          { name: 'sfp_alpha', descr: 'first', api_key: false },
          { name: 'sfp_beta', descr: 'second', api_key: true },
        ]),
        { status: 200 },
      ),
    );
    const modules = await listModules();
    expect(modules).toHaveLength(2);
    expect(modules[0]).toEqual({ name: 'sfp_alpha', descr: 'first', api_key: false });
    expect(modules[1].api_key).toBe(true);
  });

  it('sorts modules by name', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          { name: 'sfp_z', descr: 'z', api_key: false },
          { name: 'sfp_a', descr: 'a', api_key: false },
        ]),
        { status: 200 },
      ),
    );
    const modules = await listModules();
    expect(modules.map((m) => m.name)).toEqual(['sfp_a', 'sfp_z']);
  });
});

describe('listEventTypes', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps [label, id] tuples to typed EventType objects', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['Domain Name', 'DOMAIN_NAME'],
          ['IP Address', 'IP_ADDRESS'],
        ]),
        { status: 200 },
      ),
    );
    const types = await listEventTypes();
    expect(types).toEqual([
      { id: 'DOMAIN_NAME', label: 'Domain Name' },
      { id: 'IP_ADDRESS', label: 'IP Address' },
    ]);
  });
});
