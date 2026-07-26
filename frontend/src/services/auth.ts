/** Shared login call (`POST /api/v1/auth/login` — STOPGAP, see
 * `app/api/auth.py`: there is no real credential store yet, any
 * operator_id + non-empty pin gets a valid token). Used by both
 * WarehouseSelect (operator flow) and SessionSelect (supervisor flow) so
 * the request shape only lives in one place. */
export async function login(apiBaseUrl: string, operatorId: string, pin: string): Promise<string> {
  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operator_id: operatorId, pin }),
  });
  if (!response.ok) throw new Error('login_failed');
  const data: { access_token: string } = await response.json();
  return data.access_token;
}
