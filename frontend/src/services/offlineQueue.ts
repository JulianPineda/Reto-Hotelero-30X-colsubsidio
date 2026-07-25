import Dexie, { type Table } from 'dexie';

export type OfflineItemStatus = 'pending' | 'needs_review';

export interface OfflineCountItem {
  id?: number;
  sessionId: string;
  article: string;
  quantity: number;
  unit: string;
  /** ISO date, only filled in when the operator already knows the item is
   * perishable — CLAUDE.md §3.6 requires it, but offline capture has no
   * catalog lookup to know `is_perishable` in advance. */
  expiryDate: string | null;
  createdAt: string;
  status: OfflineItemStatus;
}

/**
 * IndexedDB-backed queue for CLAUDE.md §3.8's offline mode: manual entries
 * captured while `navigator.onLine` is false, persisted locally until
 * reconnect drains them through Catalog Agent + Auditor Agent
 * (`offlineSync.ts`).
 */
class OfflineDB extends Dexie {
  items!: Table<OfflineCountItem, number>;

  constructor() {
    super('inventory-offline-db');
    this.version(1).stores({
      items: '++id, sessionId, status',
    });
  }
}

export const offlineDB = new OfflineDB();

export async function enqueueOfflineItem(
  entry: Omit<OfflineCountItem, 'id' | 'status' | 'createdAt'>,
): Promise<number> {
  return offlineDB.items.add({ ...entry, status: 'pending', createdAt: new Date().toISOString() });
}

export async function listPendingItems(sessionId: string): Promise<OfflineCountItem[]> {
  return offlineDB.items
    .where('sessionId')
    .equals(sessionId)
    .and((item) => item.status === 'pending')
    .toArray();
}

export async function listNeedsReviewItems(sessionId: string): Promise<OfflineCountItem[]> {
  return offlineDB.items
    .where('sessionId')
    .equals(sessionId)
    .and((item) => item.status === 'needs_review')
    .toArray();
}

export async function markItemStatus(id: number, status: OfflineItemStatus): Promise<void> {
  await offlineDB.items.update(id, { status });
}

export async function deleteOfflineItem(id: number): Promise<void> {
  await offlineDB.items.delete(id);
}
