import { useState } from 'react';
import { SessionSelect } from '../SessionSelect';
import { WarehouseSelect } from '../WarehouseSelect';
import { clearStoredSession, getStoredSession, login, storeSession, type Role } from '../../services/auth';
import { colors, gradients, logos, radius, shadow, touchTargets, typography } from '../../theme';

export interface LoginProps {
  apiBaseUrl: string;
  wsBaseUrl: string;
}

const inputStyle = {
  minHeight: touchTargets.minimum,
  fontSize: typography.sizes.base,
  fontFamily: typography.fontFamily,
  padding: '12px 14px',
  border: `1px solid ${colors.ui.border}`,
  borderRadius: 10,
  width: '100%',
  boxSizing: 'border-box' as const,
  transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
};

// CLAUDE.md §2 reserves yellow for "Botón principal" — the primary CTA on
// every screen (this one, WarehouseSelect, SessionSelect) uses it rather
// than blue, which is reserved for headers/links/text-on-light per the
// same color table.
const buttonStyle = (enabled: boolean) => ({
  minHeight: touchTargets.minimum,
  background: enabled ? colors.primary.yellow : colors.neutral.grafito40,
  color: enabled ? colors.ui.textPrimary : '#ffffff',
  border: 'none',
  borderRadius: 10,
  fontSize: typography.sizes.base,
  fontWeight: 700,
  cursor: enabled ? 'pointer' : 'not-allowed',
  boxShadow: enabled ? '0 2px 8px rgba(255, 208, 0, 0.35)' : 'none',
  transition: 'transform 0.1s ease, box-shadow 0.15s ease',
});

/** Colsubsidio lockup on the brand-blue header — CLAUDE.md §2: the white
 * lockup is only ever used on a colored/dark background, never white. */
function BrandHeader() {
  return (
    <div
      style={{
        background: gradients.brandBlue,
        padding: '28px 24px',
        display: 'flex',
        justifyContent: 'center',
      }}
    >
      <img src={logos.fullWhite} alt="Colsubsidio" style={{ height: 40 }} />
    </div>
  );
}

/**
 * Single entry point for both the operator and supervisor flows (previously
 * two separate URLs — `/select` and `/supervisor-login` — with their own
 * duplicated login forms). Login happens once here; `role` comes back from
 * the backend (real credential check against the `operators` table, not a
 * frontend choice) and routes straight to the matching module — an
 * operator-role account never sees the supervisor screens and vice versa,
 * mirroring the server-side `require_role` gate on every endpoint.
 */
export function Login({ apiBaseUrl, wsBaseUrl }: LoginProps) {
  const stored = getStoredSession();
  const [authToken, setAuthToken] = useState<string | null>(stored?.token ?? null);
  const [role, setRole] = useState<Role | null>(stored?.role ?? null);
  const [operatorId, setOperatorId] = useState('');
  const [pin, setPin] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoginError(null);
    setBusy(true);
    try {
      const result = await login(apiBaseUrl, operatorId, pin);
      storeSession(result.token, result.role);
      setAuthToken(result.token);
      setRole(result.role);
    } catch {
      setLoginError('No se pudo iniciar sesión. Verifica tu ID de operario y PIN.');
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = () => {
    clearStoredSession();
    setAuthToken(null);
    setRole(null);
    setOperatorId('');
    setPin('');
  };

  if (authToken && role === 'operator') {
    return <WarehouseSelect apiBaseUrl={apiBaseUrl} wsBaseUrl={wsBaseUrl} authToken={authToken} onLogout={handleLogout} />;
  }
  if (authToken && role === 'supervisor') {
    return <SessionSelect apiBaseUrl={apiBaseUrl} authToken={authToken} onLogout={handleLogout} />;
  }

  return (
    <div style={{ minHeight: '100vh', background: colors.ui.surface, fontFamily: typography.fontFamily }}>
      <BrandHeader />
      <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 16px' }}>
        <div
          style={{
            width: '100%',
            maxWidth: 400,
            background: colors.ui.background,
            borderRadius: radius.large,
            padding: 32,
            boxShadow: shadow.medium,
            boxSizing: 'border-box',
          }}
        >
          <h1 style={{ color: colors.primary.blue, marginTop: 0, fontSize: '1.5rem' }}>
            Piscilago — Conteo de Inventario
          </h1>
          <p style={{ color: colors.ui.textSecondary, marginTop: -8 }}>Ingresa tus credenciales para continuar.</p>

          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 24 }}>
            <div>
              <label htmlFor="operator-id" style={{ display: 'block', marginBottom: 6, fontWeight: 600, color: colors.ui.textPrimary }}>
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
              <label htmlFor="operator-pin" style={{ display: 'block', marginBottom: 6, fontWeight: 600, color: colors.ui.textPrimary }}>
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
            {loginError && <p style={{ color: colors.ui.error, margin: 0 }}>{loginError}</p>}
            <button
              type="submit"
              disabled={busy || !operatorId || !pin}
              style={buttonStyle(!busy && !!operatorId && !!pin)}
            >
              {busy ? 'Ingresando…' : 'Ingresar'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
