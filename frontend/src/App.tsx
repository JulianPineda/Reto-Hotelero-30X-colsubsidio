import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { CountSession, type CountSessionProps } from './pages/CountSession';
import { Login } from './pages/Login';
import { SupervisorDashboard, type SupervisorDashboardProps } from './pages/SupervisorDashboard';

// App shell: one entry point (`/`) — login once, then auto-routed by the
// backend-verified `role` claim straight into the operator or supervisor
// module (see pages/Login); role is a real security boundary
// (`require_role` on every endpoint), not a menu choice. Previously two
// separate URLs (/select, /supervisor-login) each with their own login
// form, despite hitting the exact same POST /auth/login underneath and no
// role concept existing on the backend at all. /count and /supervisor have
// no meaning on their own, so visiting either directly (refresh, bookmark)
// bounces back to "/" instead of falling back to stale demo props.
// ExportPreview (referenced in the project layout) has no component yet —
// UI Expert scope beyond what's been implemented here.
function CountSessionRoute() {
  const location = useLocation();
  const state = location.state as CountSessionProps | null;

  if (state === null) {
    return <Navigate to="/" replace />;
  }
  return <CountSession {...state} />;
}

function SupervisorDashboardRoute() {
  const location = useLocation();
  const state = location.state as SupervisorDashboardProps | null;

  if (state === null) {
    return <Navigate to="/" replace />;
  }
  return <SupervisorDashboard {...state} />;
}

export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost/api/v1';
  const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost/ws';

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login apiBaseUrl={apiBaseUrl} wsBaseUrl={wsBaseUrl} />} />
        <Route path="/count" element={<CountSessionRoute />} />
        <Route path="/supervisor" element={<SupervisorDashboardRoute />} />
        {/* Old bookmarks/links from before the single-URL merge. */}
        <Route path="/select" element={<Navigate to="/" replace />} />
        <Route path="/supervisor-login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
