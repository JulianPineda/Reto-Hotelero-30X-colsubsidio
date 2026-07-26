/**
 * Central place to react to an expired/invalid JWT. `JWT_EXPIRE_MINUTES`
 * is 480 (8h) — a tablet left logged in across a shift change, or a
 * CountSession that just runs long, will eventually get a 401 on some
 * authenticated call with no other signal that anything's wrong. Before
 * this, that 401 body would just get parsed as if it were real data.
 *
 * A hard `window.location` redirect (not React Router's `navigate`) is
 * deliberate — this needs to work from plain `services/*.ts` modules with
 * no access to router context, not just from inside components.
 */
export type LoginPath = '/select' | '/supervisor-login';

export function redirectToLogin(loginPath: LoginPath): void {
  window.location.href = loginPath;
}

/** Returns true (and redirects) when `response` is a 401 — callers should
 * stop immediately rather than trying to parse the response as data. */
export function handleUnauthorized(response: Response, loginPath: LoginPath): boolean {
  if (response.status === 401) {
    redirectToLogin(loginPath);
    return true;
  }
  return false;
}
