import { Alert, Anchor, Stack, Text } from '@mantine/core';

export function PlaceholderTab({
  tabLabel,
  scanId,
}: {
  tabLabel: string;
  scanId: string;
}) {
  return (
    <Alert color="blue" title="This view is being migrated" mt="md">
      <Stack gap="xs">
        <Text size="sm">
          The updated <strong>{tabLabel}</strong> view arrives in a follow-up
          milestone. Use the legacy view for now.
        </Text>
        <Anchor href={`/scaninfo-legacy?id=${encodeURIComponent(scanId)}`}>
          Open legacy {tabLabel} view
        </Anchor>
      </Stack>
    </Alert>
  );
}
