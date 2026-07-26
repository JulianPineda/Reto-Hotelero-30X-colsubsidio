import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { SupervisorDashboardProps } from '../SupervisorDashboard';
import { login } from '../../services/auth';
import { colors, touchTargets, typography } from '../../theme';

export interface SessionSelectProps {
  apiBaseUrl: string;
}

interface SessionOption {
  id: string;
  warehouse_code: string;
  shift: string;
  status: string;
  started_at: string;
  flagged_items: number;
}

const SHIFT_LABELS: Record<string, string> = {
  morning: 'Mañana',
  afternoon: 'Tarde',
  night: 'Noche',
};

const inputStyle = {
  minHeight: touchTargets.minimum,
  fontSize: typography.sizes.base,
  fontFamily: typography.fontFamily,
  padding: '8px 12px',
  border: `1px solid ${colors.ui.border}`,
  borderRadius: 8,
  width: '100%',
  boxSizing: 'border-box' as const,
};

const buttonStyle = (enabled: boolean) => ({
  minHeight: touchTargets.minimum,
  background: enabled ? colors.primary.blue : colors.neutral.grafito40,
  color: '#ffffff',
  border: 'none',
  borderRadius: 8,
  fontSize: typography.sizes.base,
  fontWeight: 600,
  cursor: enabled ? 'pointer' : 'not-allowed',
});

/**
 * Entry screen for the Supervisor Dashboard flow: login (same STOPGAP as
 * WarehouseSelect — see app/api/auth.py) -> pick which session to review
 * (`GET /api/v1/sessions`) -> hand off to SupervisorDashboard with a real
 * session_id + token via router state, replacing the "demo-session" +
 * empty-string token App.tsx used to hardcode — which broke outright once
 * the JWT retrofit added auth to every supervisor endpoint.
 */
export function SessionSelect({ apiBaseUrl }: SessionSelectProps) {
  const navigate = useNavigate();

  const [operatorId, setOperatorId] = useState('');
  const [pin, setPin] = useState('');
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [sessionOptions, setSessionOptions] = useState<SessionOption[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [busy, setBusy] = useState(false);

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoginError(null);
    setBusy(true);
    try {
      const token = await login(apiBaseUrl, operatorId, pin);

      const sessionsResponse = await fetch(`${apiBaseUrl}/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!sessionsResponse.ok) throw new Error('sessions_failed');
      const options: SessionOption[] = await sessionsResponse.json();

      setAuthToken(token);
      setSessionOptions(options);
      if (options.length > 0) setSelectedSessionId(options[0].id);
    } catch {
      setLoginError('No se pudo iniciar sesión. Verifica tu ID de operario y PIN.');
    } finally {
      setBusy(false);
    }
  };

  const handleOpenDashboard = () => {
    if (!authToken || !selectedSessionId) return;
    const chosen = sessionOptions.find((option) => option.id === selectedSessionId);

    const dashboardProps: SupervisorDashboardProps = {
      sessionId: selectedSessionId,
      warehouseCode: chosen?.warehouse_code ?? '',
      shiftLabel: chosen ? (SHIFT_LABELS[chosen.shift] ?? chosen.shift) : '',
      apiBaseUrl,
      authToken,
    };
    navigate('/supervisor', { state: dashboardProps });
  };

  return (
    <div style={{ padding: 24, maxWidth: 480, fontFamily: typography.fontFamily }}>
      <h1 style={{ color: colors.primary.blue }}>Piscilago — Supervisor</h1>

      {authToken === null ? (
        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label htmlFor="supervisor-operator-id" style={{ display: 'block', marginBottom: 4 }}>
              ID de operario
            </label>
            <input
              id="supervisor-operator-id"
              type="text"
              value={operatorId}
              onChange={(event) => setOperatorId(event.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <label htmlFor="supervisor-pin" style={{ display: 'block', marginBottom: 4 }}>
              PIN
            </label>
            <input
              id="supervisor-pin"
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              style={inputStyle}
            />
          </div>
          {loginError && <p style={{ color: colors.ui.error }}>{loginError}</p>}
          <button
            type="submit"
            disabled={busy || !operatorId || !pin}
            style={buttonStyle(!busy && !!operatorId && !!pin)}
          >
            Ingresar
          </button>
        </form>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {sessionOptions.length === 0 ? (
            <p style={{ color: colors.ui.textSecondary }}>No hay sesiones de conteo todavía.</p>
          ) : (
            <div>
              <label htmlFor="session-select" style={{ display: 'block', marginBottom: 4 }}>
                Sesión a revisar
              </label>
              <select
                id="session-select"
                value={selectedSessionId}
                onChange={(event) => setSelectedSessionId(event.target.value)}
                style={inputStyle}
              >
                {sessionOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.warehouse_code} · {SHIFT_LABELS[option.shift] ?? option.shift} ·{' '}
                    {option.flagged_items} flaggeado(s)
                  </option>
                ))}
              </select>
            </div>
          )}

          <button
            type="button"
            onClick={handleOpenDashboard}
            disabled={busy || !selectedSessionId}
            style={buttonStyle(!busy && !!selectedSessionId)}
          >
            Abrir dashboard
          </button>
        </div>
      )}
    </div>
  );
}
