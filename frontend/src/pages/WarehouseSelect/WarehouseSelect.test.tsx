import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WarehouseSelect } from './index';

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

describe('WarehouseSelect', () => {
  it('loads warehouses on mount and shows the picker', async () => {
    mockFetchByPath({
      '/warehouses': () => [
        { id: 'wh-1', code: 'PSL-ALMACEN-GENERAL', name: 'Almacén General' },
        { id: 'wh-2', code: 'PSL-ZOO', name: 'Zoológico' },
      ],
    });

    render(
      <WarehouseSelect apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" authToken="token-abc" onLogout={vi.fn()} />,
    );

    await waitFor(() => expect(screen.getByLabelText(/bodega/i)).toBeInTheDocument());
    expect(screen.getByRole('option', { name: 'Almacén General' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Zoológico' })).toBeInTheDocument();
  });

  it('shows a load error when the warehouses request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({}) })));

    render(
      <WarehouseSelect apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" authToken="token-abc" onLogout={vi.fn()} />,
    );

    await waitFor(() => expect(screen.getByText(/no se pudieron cargar las bodegas/i)).toBeInTheDocument());
  });

  it('creates a session and navigates to /count with the right props', async () => {
    mockFetchByPath({
      '/warehouses': () => [{ id: 'wh-1', code: 'PSL-ALMACEN-GENERAL', name: 'Almacén General' }],
      '/sessions': () => ({ id: 'session-xyz', warehouse_id: 'wh-1', operator_id: 'OP-231', shift: 'morning', status: 'in_progress' }),
    });

    render(
      <WarehouseSelect apiBaseUrl="http://api.test/api/v1" wsBaseUrl="ws://api.test/ws" authToken="token-abc" onLogout={vi.fn()} />,
    );

    await waitFor(() => expect(screen.getByLabelText(/bodega/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /iniciar conteo/i }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalledTimes(1));
    const [path, options] = navigateMock.mock.calls[0];
    expect(path).toBe('/count');
    expect(options.state).toMatchObject({
      wsUrl: 'ws://api.test/ws/voice/session-xyz?token=token-abc',
      apiBaseUrl: 'http://api.test/api/v1',
      authToken: 'token-abc',
      sessionId: 'session-xyz',
      warehouseId: 'wh-1',
      warehouseCode: 'PSL-ALMACEN-GENERAL',
      shift: 'morning',
      shiftLabel: 'Mañana',
    });
  });
});
