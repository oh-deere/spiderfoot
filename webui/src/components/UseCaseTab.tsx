import { Radio, Stack, Text } from '@mantine/core';
import type { UseCase } from '../types';

const USECASE_OPTIONS: { value: UseCase; label: string; description: string }[] = [
  {
    value: 'all',
    label: 'All',
    description:
      'Get anything and everything about the target. All SpiderFoot modules will be enabled (slow) but every possible piece of information about the target will be obtained and analysed.',
  },
  {
    value: 'Footprint',
    label: 'Footprint',
    description:
      "Understand what information this target exposes to the Internet. Gain an understanding about the target's network perimeter, associated identities and other information that is obtained through a lot of web crawling and search engine use.",
  },
  {
    value: 'Investigate',
    label: 'Investigate',
    description:
      "Best for when you suspect the target to be malicious but need more information. Some basic footprinting will be performed in addition to querying of blacklists and other sources that may have information about your target's maliciousness.",
  },
  {
    value: 'Passive',
    label: 'Passive',
    description:
      "When you don't want the target to even suspect they are being investigated. As much information will be gathered without touching the target or their affiliates, therefore only modules that do not touch the target will be enabled.",
  },
];

export function UseCaseTab({
  value,
  onChange,
}: {
  value: UseCase;
  onChange: (v: UseCase) => void;
}) {
  return (
    <Radio.Group value={value} onChange={(v) => onChange(v as UseCase)}>
      <Stack gap="md">
        {USECASE_OPTIONS.map((opt) => (
          <Radio
            key={opt.value}
            value={opt.value}
            label={
              <>
                <Text fw={600}>{opt.label}</Text>
                <Text size="sm" c="dimmed">
                  {opt.description}
                </Text>
              </>
            }
          />
        ))}
      </Stack>
    </Radio.Group>
  );
}
