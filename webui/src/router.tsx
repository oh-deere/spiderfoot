import { createBrowserRouter } from 'react-router-dom';
import { ScanListPage } from './pages/ScanListPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <ScanListPage />,
  },
]);
