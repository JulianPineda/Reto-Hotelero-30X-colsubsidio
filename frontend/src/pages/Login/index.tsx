import { useState } from 'react';
import { SessionSelect } from '../SessionSelect';
import { WarehouseSelect } from '../WarehouseSelect';
import { login } from '../../services/auth';
import { colors, logos, touchTargets, typography } from '../../theme';

export interface LoginProps {
  apiBaseUrl: string;
  wsBaseUrl: string;
}

type Role = 'operator' | 'supervisor';
type Step = 'login' | 'role-select' | Role;

const TOKEN_STORAGE_KEY = 'piscilago_auth_token';

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

/** Colsubsidio lockup on the brand-blue header — CLAUDE.md §2: the white
 * lockup is only ever used on a colored/dark background, never white. */
function BrandHeader() {
  return (
    <div
      style={{
        background: colors.primary.blue,
        padding: '20px 24px',
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
 * duplicated login forms, even though both hit the exact same
 * `POST /auth/login` and there's no role concept on the backend at all).
 * Login happens once here; the operator then picks what they came to do.
 */
export function Login({ apiBaseUrl, wsBaseUrl }: LoginProps) {
  // Re-mounted every time something navigates back to "/" (BackToMenuButton,
  // the router-state guards in App.tsx) — without persisting the token
  // somewhere outside this component, "back to menu" silently demoted to
  // "log in again," which defeats the point of a quick way back. sessionStorage
  // (not localStorage) so a shared tablet doesn't keep a stale session
  // across actual browser restarts/different operators.
  const [authToken, setAuthToken] = useState<string | null>(() => sessionStorage.getItem(TOKEN_STORAGE_KEY));
  const [step, setStep] = useState<Step>(() => (sessionStorage.getItem(TOKEN_STORAGE_KEY) ? 'role-select' : 'login'));
  const [operatorId, setOperatorId] = useState('');
  const [pin, setPin] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoginError(null);
    setBusy(true);
    try {
      const token = await login(apiBaseUrl, operatorId, pin);
      sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
      setAuthToken(token);
      setStep('role-select');
    } catch {
      setLoginError('No se pudo iniciar sesión. Verifica tu ID de operario y PIN.');
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = () => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    setOperatorId('');
    setPin('');
    setStep('login');
  };

  if (step === 'operator' && authToken) {
    return <WarehouseSelect apiBaseUrl={apiBaseUrl} wsBaseUrl={wsBaseUrl} authToken={authToken} />;
  }
  if (step === 'supervisor' && authToken) {
    return <SessionSelect apiBaseUrl={apiBaseUrl} authToken={authToken} />;
  }

  return (
    <div style={{ fontFamily: typography.fontFamily }}>
      <BrandHeader />
      <div style={{ padding: 24, maxWidth: 420 }}>
        <h1 style={{ color: colors.primary.blue }}>Piscilago — Conteo de Inventario</h1>

        {step === 'login' && (
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
        )}

        {step === 'role-select' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <p style={{ color: colors.ui.textSecondary }}>¿Qué deseas hacer?</p>
            <button type="button" onClick={() => setStep('operator')} style={buttonStyle(true)}>
              Contar inventario
            </button>
            <button
              type="button"
              onClick={() => setStep('supervisor')}
              style={{ ...buttonStyle(true), background: colors.neutral.grafito }}
            >
              Panel de supervisor
            </button>
            <button
              type="button"
              onClick={handleLogout}
              style={{
                minHeight: touchTargets.minimum,
                background: 'none',
                border: 'none',
                color: colors.ui.textSecondary,
                textDecoration: 'underline',
                cursor: 'pointer',
              }}
            >
              Cerrar sesión
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
