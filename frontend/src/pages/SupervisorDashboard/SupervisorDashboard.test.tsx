import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SupervisorDashboard } from './index';

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
      return { ok: true, json: async () => handler(init), blob: async () => new Blob(['fake xlsx']) };
    }),
  );
}

beforeEach(() => {
  navigateMock.mockClear();
  // jsdom doesn't implement these — handleExport's blob-download path
  // (needed since the download requires the same Bearer auth as
  // everything else, so a plain <a href> can't be used) calls them.
  vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:fake'), revokeObjectURL: vi.fn() });
});

describe('SupervisorDashboard export', () => {
  it('fetches the download from the origin + the backend-provided absolute path, not a doubled /api/v1 prefix', async () => {
    const fetchedUrls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString();
        fetchedUrls.push(url);
        if (url.endsWith('/flagged-items')) return { ok: true, json: async () => [] };
        if (url.endsWith('/agents/export')) return { ok: true, json: async () => ({ job_id: 'job-1' }) };
        if (url.endsWith('/agents/export/jobs/job-1')) {
          return {
            ok: true,
            json: async () => ({
              status: 'completed',
              download_url: '/api/v1/exports/PSL-X_2026-07-26_morning_abc123.xlsx',
              error: null,
            }),
          };
        }
        if (url === 'http://api.test/api/v1/exports/PSL-X_2026-07-26_morning_abc123.xlsx') {
          return { ok: true, blob: async () => new Blob(['fake xlsx']), json: async () => ({}) };
        }
        throw new Error(`Unhandled fetch: ${url} (init=${JSON.stringify(init)})`);
      }),
    );

    render(
      <SupervisorDashboard
        sessionId="session-1"
        warehouseCode="PSL-X"
        shiftLabel="Mañana"
        apiBaseUrl="http://api.test/api/v1"
        authToken="token-abc"
      />,
    );

    await waitFor(() => expect(screen.getByText(/no hay ítems marcados/i)).toBeInTheDocument());
    screen.getByRole('button', { name: /exportar a excel/i }).click();

    await waitFor(() => expect(screen.getByText(/exportación completada/i)).toBeInTheDocument(), { timeout: 3000 });

    // The exact bug this regression-tests: the download fetch must never
    // hit ".../api/v1/api/v1/exports/..." (confirmed live as a 404).
    expect(fetchedUrls.some((url) => url.includes('/api/v1/api/v1/'))).toBe(false);
    expect(fetchedUrls).toContain('http://api.test/api/v1/exports/PSL-X_2026-07-26_morning_abc123.xlsx');
  });

  it('shows an error instead of a silent failure when the download itself 404s', async () => {
    mockFetchByPath({
      '/flagged-items': () => [],
      '/agents/export': () => ({ job_id: 'job-2' }),
      '/agents/export/jobs/job-2': () => ({
        status: 'completed',
        download_url: '/api/v1/exports/missing.xlsx',
        error: null,
      }),
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString();
        if (url.endsWith('/flagged-items')) return { ok: true, json: async () => [] };
        if (url.endsWith('/agents/export')) return { ok: true, json: async () => ({ job_id: 'job-2' }) };
        if (url.endsWith('/agents/export/jobs/job-2')) {
          return {
            ok: true,
            json: async () => ({ status: 'completed', download_url: '/api/v1/exports/missing.xlsx', error: null }),
          };
        }
        if (url.endsWith('/exports/missing.xlsx')) return { ok: false, status: 404, json: async () => ({}) };
        throw new Error(`Unhandled fetch: ${url}`);
      }),
    );

    render(
      <SupervisorDashboard
        sessionId="session-1"
        warehouseCode="PSL-X"
        shiftLabel="Mañana"
        apiBaseUrl="http://api.test/api/v1"
        authToken="token-abc"
      />,
    );

    await waitFor(() => expect(screen.getByText(/no hay ítems marcados/i)).toBeInTheDocument());
    screen.getByRole('button', { name: /exportar a excel/i }).click();

    await waitFor(() => expect(screen.getByText(/no se pudo completar la exportación/i)).toBeInTheDocument(), {
      timeout: 3000,
    });
  });
});
