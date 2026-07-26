import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { SupervisorDashboardProps } from '../SupervisorDashboard';
import { BrandRibbon } from '../../components/BrandRibbon';
import { HomeIcon, BackIcon, LogoutIcon } from '../../components/icons';
import { OptionsRibbon, type RibbonAction } from '../../components/OptionsRibbon';
import { colors, radius, shadow, touchTargets, typography } from '../../theme';

export interface SessionSelectProps {
  apiBaseUrl: string;
  /** Already-authenticated — login happens once in `Login`, shared by both
   * the operator and supervisor flows (T-XXX "una sola URL"). */
  authToken: string;
  onLogout: () => void;
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
  padding: '10px 12px',
  border: `1px solid ${colors.ui.border}`,
  borderRadius: radius.small,
  width: '100%',
  boxSizing: 'border-box' as const,
};

const buttonStyle = (enabled: boolean) => ({
  minHeight: touchTargets.minimum,
  background: enabled ? colors.primary.yellow : colors.neutral.grafito40,
  color: enabled ? colors.ui.textPrimary : '#ffffff',
  border: 'none',
  borderRadius: radius.small,
  fontSize: typography.sizes.base,
  fontWeight: 700,
  cursor: enabled ? 'pointer' : 'not-allowed',
});

/**
 * Supervisor flow's picker step: list sessions to review
 * (`GET /api/v1/sessions`) -> hand off to SupervisorDashboard with a real
 * session_id + token via router state. Login itself happens once in
 * `Login` (T-XXX "una sola URL" merged operator+supervisor entry) and is
 * passed down as `authToken`.
 */
export function SessionSelect({ apiBaseUrl, authToken, onLogout }: SessionSelectProps) {
  const navigate = useNavigate();

  const [sessionOptions, setSessionOptions] = useState<SessionOption[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/sessions`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        if (!response.ok) throw new Error('sessions_failed');
        const options: SessionOption[] = await response.json();
        if (cancelled) return;
        setSessionOptions(options);
        if (options.length > 0) setSelectedSessionId(options[0].id);
      } catch {
        if (!cancelled) setLoadError('No se pudieron cargar las sesiones. Intenta de nuevo.');
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, authToken]);

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

  const actions: RibbonAction[] = [
    { key: 'inicio', label: 'Inicio', icon: <HomeIcon />, onClick: () => navigate('/') },
    { key: 'retroceder', label: 'Retroceder', icon: <BackIcon />, onClick: onLogout },
    { key: 'logout', label: 'Cerrar sesión', icon: <LogoutIcon />, onClick: onLogout },
  ];

  return (
    <div style={{ minHeight: '100vh', fontFamily: typography.fontFamily }}>
      <BrandRibbon />
      <OptionsRibbon title="Selección de sesión a revisar" actions={actions} />

      <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 16px' }}>
        <div
          style={{
            width: '100%',
            maxWidth: 480,
            background: colors.ui.background,
            borderRadius: radius.large,
            padding: 28,
            boxShadow: shadow.medium,
            boxSizing: 'border-box',
          }}
        >
          {loadError && <p style={{ color: colors.ui.error }}>{loadError}</p>}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {sessionOptions.length === 0 ? (
              <p style={{ color: colors.ui.textSecondary }}>No hay sesiones de conteo todavía.</p>
            ) : (
              <div>
                <label htmlFor="session-select" style={{ display: 'block', marginBottom: 4, fontWeight: 600, color: colors.ui.textPrimary }}>
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
              disabled={!selectedSessionId}
              style={buttonStyle(!!selectedSessionId)}
            >
              Abrir dashboard
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
