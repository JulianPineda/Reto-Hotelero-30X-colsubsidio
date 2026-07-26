import { useCallback, useEffect, useState } from 'react';
import { colors } from '../../theme';
import type { FlagType } from '../../components/FlagBadge';
import type { TrafficLightColor } from '../../components/TrafficLight';
import { handleUnauthorized } from '../../services/apiClient';
import { BulkActionBar } from './BulkActionBar';
import { FlaggedItemRow, type FlaggedItem } from './FlaggedItemRow';

export interface SupervisorDashboardProps {
  sessionId: string;
  warehouseCode: string;
  shiftLabel: string;
  apiBaseUrl: string;
  authToken: string;
}

interface RawFlaggedItem {
  item_id: string;
  article_name: string;
  quantity: number;
  unit: string | null;
  flag_type: FlagType | null;
  flag_reason: string | null;
  homologation_score: number | null;
  traffic_light: TrafficLightColor | null;
  is_perishable: boolean;
}

function mapRawItem(raw: RawFlaggedItem): FlaggedItem {
  return {
    itemId: raw.item_id,
    articleName: raw.article_name,
    quantity: raw.quantity,
    unit: raw.unit,
    flagType: raw.flag_type,
    flagReason: raw.flag_reason,
    homologationScore: raw.homologation_score,
    trafficLight: raw.traffic_light,
    isPerishable: raw.is_perishable,
  };
}

/**
 * CLAUDE.md §4 + EPIC-5-supervisor.md T-015. The ordering (RED perishables
 * first, then by flag_type) comes from the backend
 * (GET /supervisor/sessions/{id}/flagged-items) — this component renders
 * whatever order it receives, it does not re-sort.
 */
export function SupervisorDashboard({
  sessionId,
  warehouseCode,
  shiftLabel,
  apiBaseUrl,
  authToken,
}: SupervisorDashboardProps) {
  const [items, setItems] = useState<FlaggedItem[]>([]);
  const [loading, setLoading] = useState(true);

  const authHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${authToken}`,
  };

  const fetchItems = useCallback(async () => {
    setLoading(true);
    const response = await fetch(`${apiBaseUrl}/supervisor/sessions/${sessionId}/flagged-items`, {
      headers: authHeaders,
    });
    if (handleUnauthorized(response, '/supervisor-login')) return;
    const data: RawFlaggedItem[] = await response.json();
    setItems(data.map(mapRawItem));
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, sessionId, authToken]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const approveItem = async (itemId: string, correctedQuantity: number | null) => {
    const response = await fetch(`${apiBaseUrl}/supervisor/items/${itemId}/approve`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({ corrected_quantity: correctedQuantity }),
    });
    if (handleUnauthorized(response, '/supervisor-login')) return;
    await fetchItems();
  };

  const rejectItem = async (itemId: string, reason: string) => {
    const response = await fetch(`${apiBaseUrl}/supervisor/items/${itemId}/reject`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({ reason }),
    });
    if (handleUnauthorized(response, '/supervisor-login')) return;
    await fetchItems();
  };

  const approveAll = async () => {
    const response = await fetch(`${apiBaseUrl}/supervisor/sessions/${sessionId}/bulk-approve`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({ item_ids: items.map((item) => item.itemId) }),
    });
    if (handleUnauthorized(response, '/supervisor-login')) return;
    await fetchItems();
  };

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ color: colors.primary.blue }}>
        Supervisor Dashboard — Bodega {warehouseCode} · Turno {shiftLabel}
      </h1>

      <BulkActionBar pendingCount={items.length} onApproveAll={approveAll} />

      {loading ? (
        <p>Cargando…</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: `2px solid ${colors.ui.border}` }}>
              <th style={{ padding: 12 }}>Artículo</th>
              <th style={{ padding: 12 }}>Cant</th>
              <th style={{ padding: 12 }}>Flag</th>
              <th style={{ padding: 12 }}>Motivo</th>
              <th style={{ padding: 12 }}>Acción</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <FlaggedItemRow key={item.itemId} item={item} onApprove={approveItem} onReject={rejectItem} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
