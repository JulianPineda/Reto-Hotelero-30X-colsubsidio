import { describe, expect, it } from 'vitest';
import {
  deleteOfflineItem,
  enqueueOfflineItem,
  listNeedsReviewItems,
  listPendingItems,
  markItemStatus,
} from './offlineQueue';

// Each test uses its own sessionId so tests don't see each other's rows in
// the shared fake-indexeddb-backed Dexie instance within this file.
let counter = 0;
function uniqueSessionId(): string {
  counter += 1;
  return `session-${counter}`;
}

describe('offlineQueue', () => {
  it('enqueues an item as pending', async () => {
    const sessionId = uniqueSessionId();
    await enqueueOfflineItem({ sessionId, article: 'Harina', quantity: 20, unit: 'kg', expiryDate: null });

    const pending = await listPendingItems(sessionId);
    expect(pending).toHaveLength(1);
    expect(pending[0]).toMatchObject({ sessionId, article: 'Harina', quantity: 20, unit: 'kg', status: 'pending' });
  });

  it('does not mix items from different sessions', async () => {
    const sessionA = uniqueSessionId();
    const sessionB = uniqueSessionId();
    await enqueueOfflineItem({ sessionId: sessionA, article: 'Harina', quantity: 20, unit: 'kg', expiryDate: null });
    await enqueueOfflineItem({ sessionId: sessionB, article: 'Sal', quantity: 5, unit: 'kg', expiryDate: null });

    expect(await listPendingItems(sessionA)).toHaveLength(1);
    expect(await listPendingItems(sessionB)).toHaveLength(1);
  });

  it('markItemStatus moves an item from pending to needs_review', async () => {
    const sessionId = uniqueSessionId();
    const id = await enqueueOfflineItem({ sessionId, article: 'Leche', quantity: 2, unit: 'L', expiryDate: null });

    await markItemStatus(id, 'needs_review');

    expect(await listPendingItems(sessionId)).toHaveLength(0);
    const review = await listNeedsReviewItems(sessionId);
    expect(review).toHaveLength(1);
    expect(review[0].article).toBe('Leche');
  });

  it('deleteOfflineItem removes it from the queue entirely', async () => {
    const sessionId = uniqueSessionId();
    const id = await enqueueOfflineItem({ sessionId, article: 'Azúcar', quantity: 10, unit: 'kg', expiryDate: null });

    await deleteOfflineItem(id);

    expect(await listPendingItems(sessionId)).toHaveLength(0);
    expect(await listNeedsReviewItems(sessionId)).toHaveLength(0);
  });

  it('preserves an optional expiryDate', async () => {
    const sessionId = uniqueSessionId();
    await enqueueOfflineItem({
      sessionId,
      article: 'Yogurt',
      quantity: 4,
      unit: 'unit',
      expiryDate: '2026-08-15',
    });

    const [item] = await listPendingItems(sessionId);
    expect(item.expiryDate).toBe('2026-08-15');
  });
});
