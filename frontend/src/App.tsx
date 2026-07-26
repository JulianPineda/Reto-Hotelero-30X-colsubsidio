import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { CountSession, type CountSessionProps } from './pages/CountSession';
import { SessionSelect } from './pages/SessionSelect';
import { SupervisorDashboard, type SupervisorDashboardProps } from './pages/SupervisorDashboard';
import { WarehouseSelect } from './pages/WarehouseSelect';

// App shell: both operator and supervisor flows start with a login +
// picker page (WarehouseSelect / SessionSelect) that hands its result to
// the actual work page via router state — /count and /supervisor have no
// meaning on their own, so visiting either directly (refresh, bookmark)
// bounces back to its picker instead of falling back to stale demo props.
// ExportPreview (referenced in the project layout) has no component yet —
// UI Expert scope beyond what's been implemented here.
function CountSessionRoute() {
  const location = useLocation();
  const state = location.state as CountSessionProps | null;

  if (state === null) {
    return <Navigate to="/select" replace />;
  }
  return <CountSession {...state} />;
}

function SupervisorDashboardRoute() {
  const location = useLocation();
  const state = location.state as SupervisorDashboardProps | null;

  if (state === null) {
    return <Navigate to="/supervisor-login" replace />;
  }
  return <SupervisorDashboard {...state} />;
}

export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost/api/v1';
  const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost/ws';

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/select" element={<WarehouseSelect apiBaseUrl={apiBaseUrl} wsBaseUrl={wsBaseUrl} />} />
        <Route path="/count" element={<CountSessionRoute />} />
        <Route path="/supervisor-login" element={<SessionSelect apiBaseUrl={apiBaseUrl} />} />
        <Route path="/supervisor" element={<SupervisorDashboardRoute />} />
        <Route path="*" element={<Navigate to="/select" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
