import '@testing-library/jest-dom';
// jsdom has no IndexedDB — offlineQueue.ts (Dexie) needs this polyfill
// loaded before any test module constructs the Dexie database.
import 'fake-indexeddb/auto';
