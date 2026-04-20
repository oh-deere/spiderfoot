import { AppShell, Title } from '@mantine/core';

export default function App() {
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header p="md">
        <Title order={3}>SpiderFoot</Title>
      </AppShell.Header>
      <AppShell.Main>
        <Title order={4}>Mantine boots</Title>
      </AppShell.Main>
    </AppShell>
  );
}
