import { createBrowserRouter } from 'react-router-dom';
import { ScanListPage } from './pages/ScanListPage';
import { NewScanPage } from './pages/NewScanPage';
import { OptsPage } from './pages/OptsPage';

export const router = createBrowserRouter([
  { path: '/', element: <ScanListPage /> },
  { path: '/newscan', element: <NewScanPage /> },
  { path: '/opts', element: <OptsPage /> },
]);
