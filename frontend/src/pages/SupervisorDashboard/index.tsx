import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors, radius, shadow } from '../../theme';
import { BrandRibbon } from '../../components/BrandRibbon';
import type { FlagType } from '../../components/FlagBadge';
import { ExportIcon, HomeIcon } from '../../components/icons';
import { OptionsRibbon, type RibbonAction } from '../../components/OptionsRibbon';
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
  const navigate = useNavigate();
  const [items, setItems] = useState<FlaggedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportDone, setExportDone] = useState(false);

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

  /** T-016 already had `POST /agents/export` + the job-status/download
   * endpoints server-side, but the dashboard itself had no button for it —
   * exporting only worked via raw curl. `format: 'excel'` per this
   * screen's request; the CSV path (default) is unaffected. Downloads via
   * a fetched blob rather than a plain `<a href>` because `GET /exports/
   * {filename}` requires the same Bearer auth as everything else — a bare
   * navigation/link click can't attach that header. */
  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    setExportDone(false);
    try {
      const requestResponse = await fetch(`${apiBaseUrl}/agents/export`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ session_id: sessionId, format: 'excel' }),
      });
      if (handleUnauthorized(requestResponse, '/supervisor-login')) return;
      if (!requestResponse.ok) {
        const body: { detail?: { error?: string; message?: string } } | null = await requestResponse
          .json()
          .catch(() => null);
        if (body?.detail?.error === 'EXPORT_BLOCKED') {
          setExportError('Hay ítems marcados sin resolver — apruébalos o recházalos antes de exportar.');
        } else if (body?.detail?.error === 'ALREADY_EXPORTED') {
          setExportError('Esta sesión ya fue exportada anteriormente.');
        } else {
          setExportError('No se pudo iniciar la exportación. Intenta de nuevo.');
        }
        return;
      }
      const { job_id: jobId }: { job_id: string } = await requestResponse.json();

      let downloadUrl: string | null = null;
      for (let attempt = 0; attempt < 20 && !downloadUrl; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const statusResponse = await fetch(`${apiBaseUrl}/agents/export/jobs/${jobId}`, { headers: authHeaders });
        if (handleUnauthorized(statusResponse, '/supervisor-login')) return;
        const status: { status: string; download_url: string | null; error: string | null } =
          await statusResponse.json();
        if (status.status === 'completed') {
          downloadUrl = status.download_url;
        } else if (status.status === 'failed') {
          throw new Error(status.error ?? 'export_failed');
        }
      }
      if (!downloadUrl) throw new Error('export_timeout');

      // `download_url` from the backend is already a full "/api/v1/..."
      // path (api-contracts.md's documented contract — see
      // exporter/router.py), not a bare filename relative to `apiBaseUrl`.
      // Concatenating apiBaseUrl (which itself ends in "/api/v1") directly
      // in front of it double-prepended the prefix — confirmed live as a
      // 404 on ".../api/v1/api/v1/exports/....xlsx". Strip apiBaseUrl back
      // to just the origin first.
      const apiOrigin = apiBaseUrl.replace(/\/api\/v1\/?$/, '');
      const fileResponse = await fetch(`${apiOrigin}${downloadUrl}`, { headers: authHeaders });
      if (!fileResponse.ok) throw new Error('download_failed');
      const blob = await fileResponse.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = downloadUrl.split('/').pop() ?? 'export.xlsx';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      setExportDone(true);
    } catch {
      setExportError('No se pudo completar la exportación. Intenta de nuevo.');
    } finally {
      setExporting(false);
    }
  };

  const ribbonActions: RibbonAction[] = [
    { key: 'inicio', label: 'Inicio', icon: <HomeIcon />, onClick: () => navigate('/') },
    {
      key: 'exportar',
      label: exporting ? 'Exportando…' : 'Exportar a Excel',
      icon: <ExportIcon />,
      onClick: handleExport,
      disabled: exporting,
      variant: 'primary',
    },
  ];

  return (
    <div style={{ minHeight: '100vh' }}>
      <BrandRibbon />
      <OptionsRibbon
        title={`Supervisor — Bodega ${warehouseCode}`}
        subtitle={`Turno ${shiftLabel}`}
        actions={ribbonActions}
      />

      <div style={{ maxWidth: 960, margin: '0 auto', padding: '24px 16px' }}>
        {exportError && <p style={{ color: colors.ui.error }}>{exportError}</p>}
        {exportDone && (
          <p role="status" style={{ color: colors.ui.success, fontWeight: 600 }}>
            Exportación completada — descarga iniciada.
          </p>
        )}

        <div style={{ background: colors.ui.background, borderRadius: radius.large, boxShadow: shadow.low, overflow: 'hidden' }}>
          <div style={{ padding: '4px 16px 0' }}>
            <BulkActionBar pendingCount={items.length} onApproveAll={approveAll} />
          </div>

          {loading ? (
            <p style={{ padding: 24 }}>Cargando…</p>
          ) : items.length === 0 ? (
            <p style={{ padding: 24, textAlign: 'center', color: colors.ui.textSecondary }}>
              No hay ítems marcados para revisar en esta sesión.
            </p>
          ) : (
            // Narrow/tablet-portrait viewports: scroll the table horizontally
            // instead of squeezing 5 columns (or letting them overflow the
            // page) — the page itself must never scroll sideways.
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', minWidth: 640, borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ textAlign: 'left', borderBottom: `2px solid ${colors.ui.border}`, background: colors.ui.surface }}>
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
