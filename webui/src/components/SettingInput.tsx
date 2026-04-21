import { NumberInput, Switch, TextInput } from '@mantine/core';
import type { SettingValue } from '../types';

export function SettingInput({
  settingKey,
  value,
  onChange,
}: {
  settingKey: string;
  value: SettingValue;
  onChange: (next: SettingValue) => void;
}) {
  if (typeof value === 'boolean') {
    return (
      <Switch
        checked={value}
        onChange={(e) => onChange(e.currentTarget.checked)}
        aria-label={settingKey}
      />
    );
  }
  if (typeof value === 'number') {
    return (
      <NumberInput
        value={value}
        onChange={(v) => onChange(typeof v === 'number' ? v : Number(v) || 0)}
        aria-label={settingKey}
      />
    );
  }
  if (Array.isArray(value)) {
    const display = value.join(',');
    const isNumberList = value.length > 0 && typeof value[0] === 'number';
    return (
      <TextInput
        value={display}
        onChange={(e) => {
          const raw = e.currentTarget.value;
          const parts = raw.split(',').map((p) => p.trim()).filter((p) => p.length > 0);
          if (isNumberList) {
            onChange(parts.map(Number).filter((n) => Number.isFinite(n)));
          } else {
            onChange(parts);
          }
        }}
        description="Comma-separated"
        aria-label={settingKey}
      />
    );
  }
  // string
  return (
    <TextInput
      value={value}
      onChange={(e) => onChange(e.currentTarget.value)}
      aria-label={settingKey}
    />
  );
}
