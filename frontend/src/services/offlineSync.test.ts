import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSessionStore } from '../store/sessionStore';
import { enqueueOfflineItem, listNeedsReviewItems, listPendingItems } from './offlineQueue';
import {
  PersistCountItemError,
  resolveNeedsReviewItem,
  submitManualFallbackItem,
  syncOfflineQueue,
  type SyncContext,
} from './offlineSync';

const ctx: SyncContext = {
  apiBaseUrl: 'http://api.test/api/v1',
  authToken: 'token-123',
  warehouseId: 'wh-1',
  shift: 'morning',
};

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

let counter = 0;
function uniqueSessionId(): string {
  counter += 1;
  return `sync-session-${counter}`;
}

beforeEach(() => {
  useSessionStore.getState().reset();
});

describe('syncOfflineQueue', () => {
  it('auto-accepts a high-score match and persists it through the Orchestrator', async () => {
    const sessionId = uniqueSessionId();
    await enqueueOfflineItem({ sessionId, article: 'Harina', quantity: 20, unit: 'kg', expiryDate: null });

    mockFetchByPath({
      '/agents/homologate': () => ({
        oracle_code: 'HAR-001',
        name: 'Harina de Trigo Especial 50kg',
        unit: 'kg',
        score: 0.94,
        is_perishable: false,
        match_method: 'vector_search',
        alternatives: [],
        requires_operator_selection: false,
        sin_homologar: false,
      }),
      '/count-items': () => ({
        item_id: 'persisted-1',
        sequence_in_session: 4,
        is_flagged: true,
        flag_type: 'threshold',
        flag_reason: 'Caída del 84.4%.',
        traffic_light: null,
      }),
    });

    await syncOfflineQueue(sessionId, ctx);

    expect(await listPendingItems(sessionId)).toHaveLength(0);
    const items = useSessionStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      id: 'persisted-1',
      oracleCode: 'HAR-001',
      articleName: 'Harina de Trigo Especial 50kg',
      isFlagged: true,
      flagType: 'threshold',
      flagReason: 'Caída del 84.4%.',
      isOffline: true,
      sinHomologar: false,
      sequenceInSession: 4,
    });
  });

  it('parks ambiguous matches as needs_review without persisting anything', async () => {
    const sessionId = uniqueSessionId();
    await enqueueOfflineItem({ sessionId, article: 'Harina', quantity: 20, unit: 'kg', expiryDate: null });

    const persistSpy = vi.fn();
    mockFetchByPath({
      '/agents/homologate': () => ({
        oracle_code: null,
        name: null,
        unit: null,
        score: 0.7,
        is_perishable: null,
        match_method: 'vector_search',
        alternatives: [{ oracle_code: 'HAR-001', name: 'Harina A', score: 0.7 }],
        requires_operator_selection: true,
        sin_homologar: false,
      }),
      '/count-items': () => {
        persistSpy();
        return { item_id: 'x', sequence_in_session: 1, is_flagged: false, flag_type: null, flag_reason: null, traffic_light: null };
      },
    });

    await syncOfflineQueue(sessionId, ctx);

    expect(persistSpy).not.toHaveBeenCalled();
    expect(useSessionStore.getState().items).toHaveLength(0);
    expect(await listPendingItems(sessionId)).toHaveLength(0);
    expect(await listNeedsReviewItems(sessionId)).toHaveLength(1);
  });

  it('parks a perishable item missing expiry date as needs_review', async () => {
    const sessionId = uniqueSessionId();
    await enqueueOfflineItem({ sessionId, article: 'Leche', quantity: 2, unit: 'L', expiryDate: null });

    mockFetchByPath({
      '/agents/homologate': () => ({
        oracle_code: 'LAC-001',
        name: 'Leche Entera 1L',
        unit: 'L',
        score: 0.9,
        is_perishable: true,
        match_method: 'vector_search',
        alternatives: [],
        requires_operator_selection: false,
        sin_homologar: false,
      }),
    });

    await syncOfflineQueue(sessionId, ctx);

    expect(useSessionStore.getState().items).toHaveLength(0);
    expect(await listNeedsReviewItems(sessionId)).toHaveLength(1);
  });

  it('persists a sin_homologar item directly with no oracle_code', async () => {
    const sessionId = uniqueSessionId();
    await enqueueOfflineItem({ sessionId, article: 'xyz', quantity: 1, unit: 'unit', expiryDate: null });

    let capturedBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString();
        if (url.endsWith('/agents/homologate')) {
          return {
            ok: true,
            json: async () => ({
              oracle_code: null,
              name: null,
              unit: null,
              score: 0,
              is_perishable: null,
              match_method: 'none',
              alternatives: [],
              requires_operator_selection: false,
              sin_homologar: true,
            }),
          };
        }
        if (url.endsWith('/count-items')) {
          capturedBody = JSON.parse(init!.body as string);
          return {
            ok: true,
            json: async () => ({
              item_id: 'persisted-2',
              sequence_in_session: 1,
              is_flagged: false,
              flag_type: null,
              flag_reason: null,
              traffic_light: null,
            }),
          };
        }
        throw new Error(`Unhandled fetch: ${url}`);
      }),
    );

    await syncOfflineQueue(sessionId, ctx);

    expect(capturedBody).toMatchObject({ oracle_code: null, sin_homologar: true, article_name: 'xyz' });
    const items = useSessionStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].sinHomologar).toBe(true);
    expect(items[0].articleName).toBe('xyz');
  });
});

describe('resolveNeedsReviewItem', () => {
  it('finalizes a picked alternative and removes it from the review queue', async () => {
    const sessionId = uniqueSessionId();
    await enqueueOfflineItem({ sessionId, article: 'Harina', quantity: 20, unit: 'kg', expiryDate: null });

    mockFetchByPath({
      '/agents/homologate': () => ({
        oracle_code: null,
        name: null,
        unit: null,
        score: 0.7,
        is_perishable: null,
        match_method: 'vector_search',
        alternatives: [{ oracle_code: 'HAR-001', name: 'Harina A', score: 0.7 }],
        requires_operator_selection: true,
        sin_homologar: false,
      }),
      '/count-items': () => ({
        item_id: 'persisted-3',
        sequence_in_session: 2,
        is_flagged: false,
        flag_type: null,
        flag_reason: null,
        traffic_light: null,
      }),
    });

    await syncOfflineQueue(sessionId, ctx);
    const [entry] = await listNeedsReviewItems(sessionId);

    await resolveNeedsReviewItem(entry, { oracleCode: 'HAR-001', name: 'Harina A', isPerishable: false }, ctx);

    expect(await listNeedsReviewItems(sessionId)).toHaveLength(0);
    const items = useSessionStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      id: 'persisted-3',
      oracleCode: 'HAR-001',
      articleName: 'Harina A',
      isOffline: true,
    });
  });
});

describe('submitManualFallbackItem', () => {
  it('homologates and persists with is_offline=false', async () => {
    mockFetchByPath({
      '/agents/homologate': () => ({
        oracle_code: 'HAR-001',
        name: 'Harina de Trigo Especial 50kg',
        unit: 'kg',
        score: 0.94,
        is_perishable: false,
        match_method: 'vector_search',
        alternatives: [],
        requires_operator_selection: false,
        sin_homologar: false,
      }),
      '/count-items': () => ({
        item_id: 'manual-1',
        sequence_in_session: 2,
        is_flagged: false,
        flag_type: null,
        flag_reason: null,
        traffic_light: null,
      }),
    });

    const item = await submitManualFallbackItem(
      { sessionId: 'session-1', article: 'Harina', quantity: 20, unit: 'kg', expiryDate: null },
      ctx,
    );

    expect(item).toMatchObject({
      id: 'manual-1',
      oracleCode: 'HAR-001',
      articleName: 'Harina de Trigo Especial 50kg',
      isOffline: false,
      sinHomologar: false,
    });
    expect(useSessionStore.getState().items).toHaveLength(1);
  });

  it('falls back to sin_homologar for an ambiguous match instead of blocking', async () => {
    const persistSpy = vi.fn();
    mockFetchByPath({
      '/agents/homologate': () => ({
        oracle_code: null,
        name: null,
        unit: null,
        score: 0.7,
        is_perishable: null,
        match_method: 'vector_search',
        alternatives: [{ oracle_code: 'HAR-001', name: 'Harina A', score: 0.7 }],
        requires_operator_selection: true,
        sin_homologar: false,
      }),
      '/count-items': () => {
        persistSpy();
        return {
          item_id: 'manual-2',
          sequence_in_session: 1,
          is_flagged: false,
          flag_type: null,
          flag_reason: null,
          traffic_light: null,
        };
      },
    });

    const item = await submitManualFallbackItem(
      { sessionId: 'session-1', article: 'Harina ambigua', quantity: 5, unit: 'kg', expiryDate: null },
      ctx,
    );

    expect(persistSpy).toHaveBeenCalledTimes(1);
    expect(item.oracleCode).toBeNull();
    expect(item.sinHomologar).toBe(true);
    expect(item.articleName).toBe('Harina ambigua');
  });

  it('propagates PersistCountItemError when the backend rejects a missing expiry date', async () => {
    mockFetchByPath({
      '/agents/homologate': () => ({
        oracle_code: 'LAC-001',
        name: 'Leche Entera 1L',
        unit: 'L',
        score: 0.9,
        is_perishable: true,
        match_method: 'vector_search',
        alternatives: [],
        requires_operator_selection: false,
        sin_homologar: false,
      }),
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString();
        if (url.endsWith('/agents/homologate')) {
          return {
            ok: true,
            json: async () => ({
              oracle_code: 'LAC-001',
              name: 'Leche Entera 1L',
              unit: 'L',
              score: 0.9,
              is_perishable: true,
              match_method: 'vector_search',
              alternatives: [],
              requires_operator_selection: false,
              sin_homologar: false,
            }),
          };
        }
        if (url.endsWith('/count-items')) {
          return {
            ok: false,
            json: async () => ({ detail: { error: 'EXPIRY_DATE_REQUIRED', message: 'nope' } }),
          };
        }
        throw new Error(`Unhandled fetch: ${url}`);
      }),
    );

    await expect(
      submitManualFallbackItem(
        { sessionId: 'session-1', article: 'Leche', quantity: 2, unit: 'L', expiryDate: null },
        ctx,
      ),
    ).rejects.toThrow(PersistCountItemError);

    expect(useSessionStore.getState().items).toHaveLength(0);
  });
});
