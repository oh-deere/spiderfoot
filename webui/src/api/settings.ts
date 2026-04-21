import { fetchJson } from './client';
import type { SettingValue, SettingsGroup, SettingsPayload, ModuleMeta } from '../types';

type OptsRawResponse = [
  'SUCCESS',
  {
    token: number;
    data: Record<string, SettingValue>;
    descs: Record<string, string>;
    modules: Record<string, {
      name: string;
      descr: string;
      cats: string[];
      labels: string[];
      meta: {
        dataSource?: {
          website?: string;
          description?: string;
          apiKeyInstructions?: string[];
        };
      };
    }>;
  },
];

function extractMeta(raw: OptsRawResponse[1]['modules'][string]): ModuleMeta {
  const ds = raw.meta?.dataSource ?? {};
  return {
    name: raw.name,
    descr: raw.descr,
    cats: raw.cats ?? [],
    labels: raw.labels ?? [],
    dataSourceWebsite: ds.website,
    dataSourceDescription: ds.description,
    apiKeyInstructions: ds.apiKeyInstructions,
  };
}

export async function fetchSettings(): Promise<SettingsPayload> {
  const raw = await fetchJson<OptsRawResponse>('/optsraw');
  if (!Array.isArray(raw) || raw[0] !== 'SUCCESS') {
    throw new Error('Unexpected /optsraw response');
  }
  const { token, data, descs, modules } = raw[1];

  // Partition flat data into per-group buckets.
  const globalSettings: Record<string, SettingValue> = {};
  const globalDescs: Record<string, string> = {};
  const modSettings = new Map<string, Record<string, SettingValue>>();
  const modDescs = new Map<string, Record<string, string>>();

  for (const [k, v] of Object.entries(data)) {
    if (k.startsWith('global.')) {
      globalSettings[k] = v;
    } else if (k.startsWith('module.')) {
      const [, mod] = k.split('.');
      if (!modSettings.has(mod)) modSettings.set(mod, {});
      modSettings.get(mod)![k] = v;
    }
  }
  for (const [k, d] of Object.entries(descs)) {
    if (k.startsWith('global.')) {
      globalDescs[k] = d;
    } else if (k.startsWith('module.')) {
      const [, mod] = k.split('.');
      if (!modDescs.has(mod)) modDescs.set(mod, {});
      modDescs.get(mod)![k] = d;
    }
  }

  const groups: SettingsGroup[] = [];
  groups.push({
    key: 'global',
    label: 'Global',
    settings: globalSettings,
    descs: globalDescs,
  });
  for (const mod of Object.keys(modules).sort()) {
    groups.push({
      key: `module.${mod}`,
      label: modules[mod].name,
      settings: modSettings.get(mod) ?? {},
      descs: modDescs.get(mod) ?? {},
      meta: extractMeta(modules[mod]),
    });
  }

  return { token, groups, settings: { ...data } };
}

function serializeValue(v: SettingValue): string {
  if (typeof v === 'boolean') return v ? '1' : '0';
  if (Array.isArray(v)) return v.join(',');
  return String(v);
}

export async function saveSettings(token: number, allopts: Record<string, SettingValue>): Promise<void> {
  // Server expects allopts as a JSON string inside a form-urlencoded body,
  // with each value already stringified in the legacy Mako convention.
  const stringified: Record<string, string> = {};
  for (const [k, v] of Object.entries(allopts)) {
    stringified[k] = serializeValue(v);
  }
  const body = new URLSearchParams();
  body.set('allopts', JSON.stringify(stringified));
  body.set('token', String(token));

  const result = await fetchJson<[string, string?]>('/savesettings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!Array.isArray(result) || result[0] !== 'SUCCESS') {
    throw new Error(result?.[1] ?? 'Unknown error saving settings');
  }
}

export async function resetSettings(token: number): Promise<void> {
  const body = new URLSearchParams();
  body.set('allopts', 'RESET');
  body.set('token', String(token));

  const result = await fetchJson<[string, string?]>('/savesettings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!Array.isArray(result) || result[0] !== 'SUCCESS') {
    throw new Error(result?.[1] ?? 'Unknown error resetting settings');
  }
}

export function parseConfigFile(contents: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of contents.split('\n')) {
    const line = rawLine.trim();
    if (!line || !line.includes('=')) continue;
    const eq = line.indexOf('=');
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1);  // don't trim value; preserve spaces
    if (key) out[key] = value;
  }
  return out;
}

export function coerceToOriginalType(raw: string, original: SettingValue): SettingValue {
  if (typeof original === 'boolean') {
    return raw === '1' || raw.toLowerCase() === 'true';
  }
  if (typeof original === 'number') {
    const n = Number(raw);
    return Number.isFinite(n) ? n : original;
  }
  if (Array.isArray(original)) {
    const parts = raw.split(',').map((p) => p.trim()).filter((p) => p.length > 0);
    if (original.length > 0 && typeof original[0] === 'number') {
      return parts.map(Number).filter((n) => Number.isFinite(n));
    }
    return parts;
  }
  return raw;
}
