import { create } from 'zustand';

export type FlagType = 'threshold' | 'trend' | 'both' | null;
export type TrafficLight = 'red' | 'yellow' | 'green' | null;

export interface CountItem {
  id: string;
  oracleCode: string | null;
  articleName: string;
  quantity: number;
  unit: string;
  isFlagged: boolean;
  flagType: FlagType;
  flagReason: string | null;
  isApproved: boolean | null;
  isOffline: boolean;
  sinHomologar: boolean;
  expiryDate: string | null;
  trafficLight: TrafficLight;
  sequenceInSession: number;
}

export type SessionStatus =
  | 'in_progress'
  | 'pending_review'
  | 'approved'
  | 'exported';

export interface SessionState {
  sessionId: string | null;
  warehouseId: string | null;
  warehouseCode: string | null;
  operatorId: string | null;
  shift: 'morning' | 'afternoon' | 'night' | null;
  status: SessionStatus;
  items: CountItem[];
  isListening: boolean;
  isProcessing: boolean;
  isOffline: boolean;

  // Actions
  setSession: (id: string, warehouseId: string, warehouseCode: string, operatorId: string, shift: 'morning' | 'afternoon' | 'night') => void;
  addItem: (item: CountItem) => void;
  updateItem: (id: string, updates: Partial<CountItem>) => void;
  removeItem: (id: string) => void;
  setListening: (val: boolean) => void;
  setProcessing: (val: boolean) => void;
  setOffline: (val: boolean) => void;
  reset: () => void;
}

const initialState = {
  sessionId: null,
  warehouseId: null,
  warehouseCode: null,
  operatorId: null,
  shift: null,
  status: 'in_progress' as SessionStatus,
  items: [],
  isListening: false,
  isProcessing: false,
  isOffline: false,
};

export const useSessionStore = create<SessionState>((set) => ({
  ...initialState,

  setSession: (id, warehouseId, warehouseCode, operatorId, shift) =>
    set({ sessionId: id, warehouseId, warehouseCode, operatorId, shift }),

  addItem: (item) =>
    set((state) => ({ items: [...state.items, item] })),

  updateItem: (id, updates) =>
    set((state) => ({
      items: state.items.map((item) =>
        item.id === id ? { ...item, ...updates } : item,
      ),
    })),

  removeItem: (id) =>
    set((state) => ({
      items: state.items.filter((item) => item.id !== id),
    })),

  setListening: (val) => set({ isListening: val }),
  setProcessing: (val) => set({ isProcessing: val }),
  setOffline: (val) => set({ isOffline: val }),
  reset: () => set(initialState),
}));
