import '@testing-library/jest-dom';

// Mantine v9 touches a couple of browser APIs during provider init (color
// scheme detection, FloatingIndicator resize tracking) that jsdom doesn't
// implement. Stub them so MantineProvider can render under vitest.
// See https://mantine.dev/guides/vitest/.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver =
  ResizeObserverStub;
