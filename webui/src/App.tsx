import { AppShell, Title } from '@mantine/core';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';

export default function App() {
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header p="md">
        <Title order={3}>SpiderFoot</Title>
      </AppShell.Header>
      <AppShell.Main>
        <RouterProvider router={router} />
      </AppShell.Main>
    </AppShell>
  );
}
