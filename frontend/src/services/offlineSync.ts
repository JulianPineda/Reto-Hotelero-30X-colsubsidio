import { useSessionStore, type CountItem, type FlagType, type TrafficLight } from '../store/sessionStore';
import { deleteOfflineItem, listPendingItems, markItemStatus, type OfflineCountItem } from './offlineQueue';

export interface SyncContext {
  apiBaseUrl: string;
  authToken: string;
  warehouseId: string;
  shift: 'morning' | 'afternoon' | 'night';
}

export interface HomologateAlternative {
  oracle_code: string;
  name: string;
  score: number;
}

export interface HomologateResponse {
  oracle_code: string | null;
  name: string | null;
  unit: string | null;
  score: number;
  is_perishable: boolean | null;
  match_method: string;
  alternatives: HomologateAlternative[];
  requires_operator_selection: boolean;
  sin_homologar: boolean;
}

interface PersistCountItemResponse {
  item_id: string;
  sequence_in_session: number;
  is_flagged: boolean;
  flag_type: string | null;
  flag_reason: string | null;
  traffic_light: string | null;
}

function authHeaders(ctx: SyncContext): Record<string, string> {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${ctx.authToken}` };
}

export async function callHomologate(
  ctx: SyncContext,
  article: string,
  unitHint: string,
): Promise<HomologateResponse> {
  const response = await fetch(`${ctx.apiBaseUrl}/agents/homologate`, {
    method: 'POST',
    headers: authHeaders(ctx),
    body: JSON.stringify({ article, warehouse_id: ctx.warehouseId, unit_hint: unitHint }),
  });
  return response.json();
}

/** `POST /api/v1/count-items` — the Orchestrator (`services/orchestrator.py
 * ::persist_count_item`). Runs the Auditor Agent server-side (when
 * `oracleCode` is set) and actually writes the CountItem row + ItemCreated
 * event, instead of this module calling `/agents/audit` and fabricating a
 * client-only id the way an earlier version of this file did. */
async function callPersistCountItem(
  ctx: SyncContext,
  params: {
    sessionId: string;
    oracleCode: string | null;
    articleName: string;
    quantity: number;
    unit: string;
    homologationScore: number | null;
    sinHomologar: boolean;
    expiryDate: string | null;
  },
): Promise<PersistCountItemResponse> {
  const response = await fetch(`${ctx.apiBaseUrl}/count-items`, {
    method: 'POST',
    headers: authHeaders(ctx),
    body: JSON.stringify({
      session_id: params.sessionId,
      oracle_code: params.oracleCode,
      article_name: params.articleName,
      quantity: params.quantity,
      unit: params.unit,
      homologation_score: params.homologationScore,
      sin_homologar: params.sinHomologar,
      expiry_date: params.expiryDate,
      is_offline: true,
    }),
  });
  return response.json();
}

async function finalizeItem(
  entry: OfflineCountItem,
  homologation: HomologateResponse,
  ctx: SyncContext,
): Promise<void> {
  const persisted = await callPersistCountItem(ctx, {
    sessionId: entry.sessionId,
    oracleCode: homologation.oracle_code,
    articleName: homologation.name ?? entry.article,
    quantity: entry.quantity,
    unit: entry.unit,
    homologationScore: homologation.score,
    sinHomologar: homologation.sin_homologar,
    expiryDate: entry.expiryDate,
  });

  const item: CountItem = {
    id: persisted.item_id,
    oracleCode: homologation.oracle_code,
    articleName: homologation.name ?? entry.article,
    quantity: entry.quantity,
    unit: entry.unit,
    isFlagged: persisted.is_flagged,
    flagType: (persisted.flag_type as FlagType) ?? null,
    flagReason: persisted.flag_reason,
    isApproved: null,
    isOffline: true,
    sinHomologar: homologation.sin_homologar,
    expiryDate: entry.expiryDate,
    trafficLight: (persisted.traffic_light as TrafficLight) ?? null,
    sequenceInSession: persisted.sequence_in_session,
  };

  useSessionStore.getState().addItem(item);
  await deleteOfflineItem(entry.id!);
}

/**
 * CLAUDE.md §3.8: "Al reconectar: todos los ítems offline pasan por
 * Catalog Agent + Auditor Agent." Items that homologate cleanly (score
 * ≥0.80 or <0.50) resolve automatically; items in the 0.50-0.79
 * "alternatives" band need an explicit operator pick (CLAUDE.md §3.2) and
 * are parked as `needs_review` instead of guessed, same for perishables
 * missing an expiry date (CLAUDE.md §3.6 — rejecting silently would lose
 * the count entirely, so it's held for review instead).
 */
export async function syncOfflineQueue(sessionId: string, ctx: SyncContext): Promise<void> {
  const pending = await listPendingItems(sessionId);

  for (const entry of pending) {
    const homologation = await callHomologate(ctx, entry.article, entry.unit);

    if (homologation.requires_operator_selection) {
      await markItemStatus(entry.id!, 'needs_review');
      continue;
    }

    if (homologation.is_perishable && !entry.expiryDate) {
      await markItemStatus(entry.id!, 'needs_review');
      continue;
    }

    await finalizeItem(entry, homologation, ctx);
  }
}

export interface ReviewChoice {
  oracleCode: string | null;
  name: string | null;
  isPerishable: boolean | null;
}

/**
 * Resolves one `needs_review` item once the operator has picked an
 * alternative (or "guardar sin homologar") in `OfflineReviewList`.
 * `expiryDateOverride` covers the other reason an item can land in review:
 * homologation already succeeded, but the perishable item was missing its
 * expiry date — in that case `choice` still carries the already-known
 * oracle_code/name from the earlier homologate() call.
 */
export async function resolveNeedsReviewItem(
  entry: OfflineCountItem,
  choice: ReviewChoice,
  ctx: SyncContext,
  expiryDateOverride?: string,
): Promise<void> {
  const effectiveEntry = expiryDateOverride ? { ...entry, expiryDate: expiryDateOverride } : entry;

  await finalizeItem(
    effectiveEntry,
    {
      oracle_code: choice.oracleCode,
      name: choice.name,
      unit: entry.unit,
      score: 1,
      is_perishable: choice.isPerishable,
      match_method: 'operator_selection',
      alternatives: [],
      requires_operator_selection: false,
      sin_homologar: choice.oracleCode === null,
    },
    ctx,
  );
}
