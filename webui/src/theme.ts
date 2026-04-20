import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Primary color sampled from auth.ohdeere.se brand. Adjust if the
// auth server's palette changes.
const ohdeereBlue: MantineColorsTuple = [
  '#e7f5ff',
  '#d0ebff',
  '#a5d8ff',
  '#74c0fc',
  '#4dabf7',
  '#339af0',
  '#228be6',
  '#1c7ed6',
  '#1971c2',
  '#1864ab',
];

export const theme = createTheme({
  primaryColor: 'ohdeere',
  colors: {
    ohdeere: ohdeereBlue,
  },
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  defaultRadius: 'md',
  cursorType: 'pointer',
});
