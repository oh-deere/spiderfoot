import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import {
  fetchSettings,
  saveSettings,
  resetSettings,
  parseConfigFile,
  coerceToOriginalType,
} from './settings';

describe('fetchSettings', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('unwraps /optsraw into typed SettingsPayload with Global-first groups', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          'SUCCESS',
          {
            token: 42,
            data: {
              'global.webroot': '/sf',
              'module.sfp_x.opt_a': true,
              'module.sfp_x.opt_b': 'hello',
            },
            descs: {
              'global.webroot': 'Web root',
              'module.sfp_x.opt_a': 'Enable A',
            },
            modules: {
              sfp_x: {
                name: 'X Module',
                descr: 'summary',
                cats: ['Footprint'],
                labels: ['tool'],
                meta: {
                  dataSource: {
                    website: 'https://x.example',
                    description: 'data',
                    apiKeyInstructions: ['step 1', 'step 2'],
                  },
                },
              },
            },
          },
        ]),
        { status: 200 },
      ),
    );
    const payload = await fetchSettings();
    expect(payload.token).toBe(42);
    expect(payload.groups).toHaveLength(2);
    expect(payload.groups[0]).toMatchObject({
      key: 'global',
      label: 'Global',
      settings: { 'global.webroot': '/sf' },
      descs: { 'global.webroot': 'Web root' },
    });
    expect(payload.groups[1]).toMatchObject({
      key: 'module.sfp_x',
      label: 'X Module',
      settings: { 'module.sfp_x.opt_a': true, 'module.sfp_x.opt_b': 'hello' },
      meta: {
        name: 'X Module',
        cats: ['Footprint'],
        dataSourceWebsite: 'https://x.example',
        apiKeyInstructions: ['step 1', 'step 2'],
      },
    });
    expect(payload.settings['global.webroot']).toBe('/sf');
  });
});

describe('saveSettings', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('posts allopts as URL-encoded JSON with stringified bool/list values', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
    );
    await saveSettings(99, {
      'global.a': true,
      'global.b': 'hello',
      'global.c': 5,
      'global.d': ['x', 'y'],
    });
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('token')).toBe('99');
    const allopts = JSON.parse(body.get('allopts') ?? '{}');
    expect(allopts).toEqual({
      'global.a': '1',
      'global.b': 'hello',
      'global.c': '5',
      'global.d': 'x,y',
    });
  });

  it('throws on ERROR response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['ERROR', 'Invalid token (nope)']), { status: 200 }),
    );
    await expect(saveSettings(1, {})).rejects.toThrow('Invalid token');
  });
});

describe('resetSettings', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('posts allopts=RESET with the token', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
    );
    await resetSettings(123);
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('allopts')).toBe('RESET');
    expect(body.get('token')).toBe('123');
  });
});

describe('parseConfigFile', () => {
  it('parses key=value lines into a flat dict', () => {
    const out = parseConfigFile(
      'global.a=1\nmodule.sfp_x.foo=hello world\n# comment\nempty_key=\n=nokey\n',
    );
    expect(out).toEqual({
      'global.a': '1',
      'module.sfp_x.foo': 'hello world',
      empty_key: '',
    });
  });
});

describe('coerceToOriginalType', () => {
  it('coerces to bool', () => {
    expect(coerceToOriginalType('1', false)).toBe(true);
    expect(coerceToOriginalType('true', false)).toBe(true);
    expect(coerceToOriginalType('0', true)).toBe(false);
  });
  it('coerces to number', () => {
    expect(coerceToOriginalType('42', 5)).toBe(42);
    expect(coerceToOriginalType('nope', 5)).toBe(5);  // fallback
  });
  it('coerces to string[]', () => {
    expect(coerceToOriginalType('a, b,c', ['x'])).toEqual(['a', 'b', 'c']);
    expect(coerceToOriginalType('', ['x'])).toEqual([]);
  });
  it('coerces to number[]', () => {
    expect(coerceToOriginalType('1,2,3', [0])).toEqual([1, 2, 3]);
  });
  it('passes strings through', () => {
    expect(coerceToOriginalType('hello', 'default')).toBe('hello');
  });
});
