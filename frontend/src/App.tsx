import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { CountSession, type CountSessionProps } from './pages/CountSession';
import { SupervisorDashboard } from './pages/SupervisorDashboard';
import { WarehouseSelect } from './pages/WarehouseSelect';

// App shell: WarehouseSelect (login + bodega/turno) hands its result to
// CountSession via router state, so /count has no meaning on its own —
// visiting it directly (refresh, bookmark) bounces back to /select rather
// than falling back to stale demo props. SupervisorDashboard (T-015) still
// uses fixed demo props — it has no equivalent "which session am I
// reviewing" picker yet. ExportPreview (referenced in the project layout)
// has no component yet — UI Expert scope beyond what's been implemented here.
function CountSessionRoute() {
  const location = useLocation();
  const state = location.state as CountSessionProps | null;

  if (state === null) {
    return <Navigate to="/select" replace />;
  }
  return <CountSession {...state} />;
}

export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost/api/v1';
  const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost/ws';

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/select" element={<WarehouseSelect apiBaseUrl={apiBaseUrl} wsBaseUrl={wsBaseUrl} />} />
        <Route path="/count" element={<CountSessionRoute />} />
        <Route
          path="/supervisor"
          element={
            <SupervisorDashboard
              sessionId="demo-session"
              warehouseCode="PSL-ALMACEN-GENERAL"
              shiftLabel="Mañana"
              apiBaseUrl={apiBaseUrl}
              authToken=""
            />
          }
        />
        <Route path="*" element={<Navigate to="/select" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
