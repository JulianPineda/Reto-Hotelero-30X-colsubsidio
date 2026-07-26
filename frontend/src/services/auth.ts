export type Role = 'operator' | 'supervisor';

export interface LoginResult {
  token: string;
  role: Role;
}

/** `POST /api/v1/auth/login` now checks real credentials against the
 * `operators` table (backend migration 003) — the previous "any
 * operator_id + non-empty pin works" stopgap is gone. `role` comes back
 * from the backend, not a frontend choice: it's the actual security
 * boundary (`app/api/deps.py::require_role` on every module-specific
 * endpoint), so an operator-role account never even sees the supervisor
 * screens, and vice versa, regardless of what URL someone tries. */
export async function login(apiBaseUrl: string, operatorId: string, pin: string): Promise<LoginResult> {
  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operator_id: operatorId, pin }),
  });
  if (!response.ok) throw new Error('login_failed');
  const data: { access_token: string; role: Role } = await response.json();
  return { token: data.access_token, role: data.role };
}

const TOKEN_KEY = 'piscilago_auth_token';
const ROLE_KEY = 'piscilago_auth_role';

/** sessionStorage, not localStorage — a shared tablet shouldn't stay
 * logged in as the same operator across an actual browser restart, but
 * "back to menu" (BackToMenuButton) shouldn't force a re-login either. */
export function storeSession(token: string, role: Role): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(ROLE_KEY, role);
}

export function getStoredSession(): LoginResult | null {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const role = sessionStorage.getItem(ROLE_KEY) as Role | null;
  if (!token || !role) return null;
  return { token, role };
}

export function clearStoredSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ROLE_KEY);
}
