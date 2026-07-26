import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { CountSessionProps } from '../CountSession';
import { login } from '../../services/auth';
import { colors, touchTargets, typography } from '../../theme';

export interface WarehouseSelectProps {
  apiBaseUrl: string;
  wsBaseUrl: string;
}

interface WarehouseOption {
  id: string;
  code: string;
  name: string;
}

type Shift = 'morning' | 'afternoon' | 'night';

const SHIFT_LABELS: Record<Shift, string> = {
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
 * First screen of the operator flow: login (STOPGAP — see
 * `app/api/auth.py`, there is no real credential store yet) -> pick
 * warehouse + shift -> create a real CountSession (`POST /api/v1/sessions`)
 * -> hand off to CountSession with a real session_id, instead of the
 * "demo-session" placeholder App.tsx used to hardcode.
 */
export function WarehouseSelect({ apiBaseUrl, wsBaseUrl }: WarehouseSelectProps) {
  const navigate = useNavigate();

  const [operatorId, setOperatorId] = useState('');
  const [pin, setPin] = useState('');
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [warehouses, setWarehouses] = useState<WarehouseOption[]>([]);
  const [selectedWarehouseId, setSelectedWarehouseId] = useState('');
  const [shift, setShift] = useState<Shift>('morning');
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoginError(null);
    setBusy(true);
    try {
      const token = await login(apiBaseUrl, operatorId, pin);

      const warehousesResponse = await fetch(`${apiBaseUrl}/warehouses`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!warehousesResponse.ok) throw new Error('warehouses_failed');
      const options: WarehouseOption[] = await warehousesResponse.json();

      setAuthToken(token);
      setWarehouses(options);
      if (options.length > 0) setSelectedWarehouseId(options[0].id);
    } catch {
      setLoginError('No se pudo iniciar sesión. Verifica tu ID de operario y PIN.');
    } finally {
      setBusy(false);
    }
  };

  const handleStartSession = async () => {
    if (!authToken || !selectedWarehouseId) return;
    setSessionError(null);
    setBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
        body: JSON.stringify({ warehouse_id: selectedWarehouseId, shift }),
      });
      if (!response.ok) throw new Error('session_failed');
      const session: { id: string } = await response.json();
      const warehouse = warehouses.find((w) => w.id === selectedWarehouseId);

      const countSessionProps: CountSessionProps = {
        wsUrl: `${wsBaseUrl}/voice/${session.id}?token=${authToken}`,
        apiBaseUrl,
        authToken,
        sessionId: session.id,
        warehouseId: selectedWarehouseId,
        warehouseCode: warehouse?.code ?? '',
        shift,
        shiftLabel: SHIFT_LABELS[shift],
      };
      navigate('/count', { state: countSessionProps });
    } catch {
      setSessionError('No se pudo iniciar la sesión de conteo. Intenta de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 420, fontFamily: typography.fontFamily }}>
      <h1 style={{ color: colors.primary.blue }}>Piscilago — Conteo de Inventario</h1>

      {authToken === null ? (
        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label htmlFor="operator-id" style={{ display: 'block', marginBottom: 4 }}>
              ID de operario
            </label>
            <input
              id="operator-id"
              type="text"
              value={operatorId}
              onChange={(event) => setOperatorId(event.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <label htmlFor="operator-pin" style={{ display: 'block', marginBottom: 4 }}>
              PIN
            </label>
            <input
              id="operator-pin"
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
          <div>
            <label htmlFor="warehouse-select" style={{ display: 'block', marginBottom: 4 }}>
              Bodega
            </label>
            <select
              id="warehouse-select"
              value={selectedWarehouseId}
              onChange={(event) => setSelectedWarehouseId(event.target.value)}
              style={inputStyle}
            >
              {warehouses.map((warehouse) => (
                <option key={warehouse.id} value={warehouse.id}>
                  {warehouse.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="shift-select" style={{ display: 'block', marginBottom: 4 }}>
              Turno
            </label>
            <select
              id="shift-select"
              value={shift}
              onChange={(event) => setShift(event.target.value as Shift)}
              style={inputStyle}
            >
              {(Object.entries(SHIFT_LABELS) as [Shift, string][]).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {sessionError && <p style={{ color: colors.ui.error }}>{sessionError}</p>}

          <button
            type="button"
            onClick={handleStartSession}
            disabled={busy || !selectedWarehouseId}
            style={buttonStyle(!busy && !!selectedWarehouseId)}
          >
            Iniciar conteo
          </button>
        </div>
      )}
    </div>
  );
}
