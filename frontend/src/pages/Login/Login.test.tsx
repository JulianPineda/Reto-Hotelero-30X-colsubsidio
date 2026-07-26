import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Login } from './index';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigateMock };
});

function mockFetchByPath(handlers: Record<string, () => unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      const handler = Object.entries(handlers).find(([path]) => url.endsWith(path))?.[1];
      if (!handler) throw new Error(`Unhandled fetch: ${url}`);
      return { ok: true, json: async () => handler() };
    }),
  );
}

async function login() {
  fireEvent.change(screen.getByLabelText(/id de operario/i), { target: { value: 'OP-231' } });
  fireEvent.change(screen.getByLabelText(/pin/i), { target: { value: '1234' } });
  fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));
  await waitFor(() => expect(screen.getByText(/qué deseas hacer/i)).toBeInTheDocument());
}

beforeEach(() => {
  navigateMock.mockClear();
  // Login persists the token in sessionStorage (so "back to menu" doesn't
  // force a re-login) — without clearing it, one test's login would leak
  // into the next test's initial render.
  sessionStorage.clear();
});

describe('Login', () => {
  it('shows a login error when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({}) })));

    render(<Login apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" />);

    fireEvent.change(screen.getByLabelText(/id de operario/i), { target: { value: 'OP-231' } });
    fireEvent.change(screen.getByLabelText(/pin/i), { target: { value: '1234' } });
    fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));

    await waitFor(() => expect(screen.getByText(/no se pudo iniciar sesión/i)).toBeInTheDocument());
  });

  it('logs in once, then choosing "Contar inventario" shows the warehouse picker', async () => {
    mockFetchByPath({
      '/auth/login': () => ({ access_token: 'token-abc', token_type: 'bearer', expires_in: 28800 }),
      '/warehouses': () => [{ id: 'wh-1', code: 'PSL-ALMACEN-GENERAL', name: 'Almacén General' }],
    });

    render(<Login apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" />);
    await login();

    fireEvent.click(screen.getByRole('button', { name: /contar inventario/i }));

    await waitFor(() => expect(screen.getByLabelText(/bodega/i)).toBeInTheDocument());
  });

  it('logs in once, then choosing "Panel de supervisor" shows the session picker', async () => {
    mockFetchByPath({
      '/auth/login': () => ({ access_token: 'token-abc', token_type: 'bearer', expires_in: 28800 }),
      '/sessions': () => [
        {
          id: 'session-1',
          warehouse_code: 'PSL-ALMACEN-GENERAL',
          shift: 'morning',
          status: 'in_progress',
          started_at: '2026-07-25T08:00:00Z',
          flagged_items: 1,
        },
      ],
    });

    render(<Login apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" />);
    await login();

    fireEvent.click(screen.getByRole('button', { name: /panel de supervisor/i }));

    await waitFor(() => expect(screen.getByLabelText(/sesión a revisar/i)).toBeInTheDocument());
  });

  it('skips straight to the role menu when a token is already in sessionStorage', () => {
    // Simulates BackToMenuButton navigating to "/" — Login remounts fresh,
    // but a still-valid session shouldn't force a re-login.
    sessionStorage.setItem('piscilago_auth_token', 'token-from-earlier');

    render(<Login apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" />);

    expect(screen.getByText(/qué deseas hacer/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/id de operario/i)).not.toBeInTheDocument();
  });

  it('"Cerrar sesión" clears the stored token and returns to the login form', async () => {
    mockFetchByPath({
      '/auth/login': () => ({ access_token: 'token-abc', token_type: 'bearer', expires_in: 28800 }),
    });

    render(<Login apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" />);
    await login();

    fireEvent.click(screen.getByRole('button', { name: /cerrar sesión/i }));

    expect(screen.getByLabelText(/id de operario/i)).toBeInTheDocument();
    expect(sessionStorage.getItem('piscilago_auth_token')).toBeNull();
  });
});
