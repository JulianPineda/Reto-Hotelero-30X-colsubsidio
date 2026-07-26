import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionSelect } from './index';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigateMock };
});

function mockFetchByPath(handlers: Record<string, (init?: RequestInit) => unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const handler = Object.entries(handlers).find(([path]) => url.endsWith(path))?.[1];
      if (!handler) throw new Error(`Unhandled fetch: ${url}`);
      return { ok: true, json: async () => handler(init) };
    }),
  );
}

beforeEach(() => {
  navigateMock.mockClear();
});

describe('SessionSelect', () => {
  it('logs in and lists sessions to review', async () => {
    mockFetchByPath({
      '/auth/login': () => ({ access_token: 'token-abc', token_type: 'bearer', expires_in: 28800 }),
      '/sessions': () => [
        {
          id: 'session-1',
          warehouse_code: 'PSL-ALMACEN-GENERAL',
          shift: 'morning',
          status: 'in_progress',
          started_at: '2026-07-25T08:00:00Z',
          flagged_items: 2,
        },
      ],
    });

    render(<SessionSelect apiBaseUrl="http://api.test/api/v1" />);

    fireEvent.change(screen.getByLabelText(/id de operario/i), { target: { value: 'SUP-1' } });
    fireEvent.change(screen.getByLabelText(/pin/i), { target: { value: '1234' } });
    fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));

    await waitFor(() => expect(screen.getByLabelText(/sesión a revisar/i)).toBeInTheDocument());
    expect(screen.getByText(/PSL-ALMACEN-GENERAL/)).toBeInTheDocument();
  });

  it('shows a message when there are no sessions yet', async () => {
    mockFetchByPath({
      '/auth/login': () => ({ access_token: 'token-abc', token_type: 'bearer', expires_in: 28800 }),
      '/sessions': () => [],
    });

    render(<SessionSelect apiBaseUrl="http://api.test/api/v1" />);

    fireEvent.change(screen.getByLabelText(/id de operario/i), { target: { value: 'SUP-1' } });
    fireEvent.change(screen.getByLabelText(/pin/i), { target: { value: '1234' } });
    fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));

    await waitFor(() => expect(screen.getByText(/no hay sesiones/i)).toBeInTheDocument());
  });

  it('navigates to /supervisor with the chosen session', async () => {
    mockFetchByPath({
      '/auth/login': () => ({ access_token: 'token-abc', token_type: 'bearer', expires_in: 28800 }),
      '/sessions': () => [
        {
          id: 'session-1',
          warehouse_code: 'PSL-ALMACEN-GENERAL',
          shift: 'morning',
          status: 'in_progress',
          started_at: '2026-07-25T08:00:00Z',
          flagged_items: 2,
        },
      ],
    });

    render(<SessionSelect apiBaseUrl="http://api.test/api/v1" />);

    fireEvent.change(screen.getByLabelText(/id de operario/i), { target: { value: 'SUP-1' } });
    fireEvent.change(screen.getByLabelText(/pin/i), { target: { value: '1234' } });
    fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));

    await waitFor(() => expect(screen.getByLabelText(/sesión a revisar/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /abrir dashboard/i }));

    expect(navigateMock).toHaveBeenCalledTimes(1);
    const [path, options] = navigateMock.mock.calls[0];
    expect(path).toBe('/supervisor');
    expect(options.state).toMatchObject({
      sessionId: 'session-1',
      warehouseCode: 'PSL-ALMACEN-GENERAL',
      shiftLabel: 'Mañana',
      apiBaseUrl: 'http://api.test/api/v1',
      authToken: 'token-abc',
    });
  });
});
