import { useState } from 'react';
import { colors, touchTargets } from '../../theme';
import { FlagBadge, type FlagType } from '../../components/FlagBadge';
import { TrafficLight, type TrafficLightColor } from '../../components/TrafficLight';

export interface FlaggedItem {
  itemId: string;
  articleName: string;
  quantity: number;
  unit: string | null;
  flagType: FlagType | null;
  flagReason: string | null;
  homologationScore: number | null;
  trafficLight: TrafficLightColor | null;
  isPerishable: boolean;
  historicalCounts?: { date: string; quantity: number }[];
}

export interface FlaggedItemRowProps {
  item: FlaggedItem;
  onApprove: (itemId: string, correctedQuantity: number | null) => void;
  onReject: (itemId: string, reason: string) => void;
}

/** CLAUDE.md §4: touch targets >= 48px. Click en la fila expande el detalle. */
export function FlaggedItemRow({ item, onApprove, onReject }: FlaggedItemRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [correctedQuantity, setCorrectedQuantity] = useState('');
  const [rejectReason, setRejectReason] = useState('');

  return (
    <>
      <tr
        onClick={() => setExpanded((prev) => !prev)}
        style={{ cursor: 'pointer', borderBottom: `1px solid ${colors.ui.border}` }}
      >
        <td style={{ padding: 12 }}>
          <TrafficLight color={item.trafficLight} isPerishable={item.isPerishable} />
          {item.articleName}
        </td>
        <td style={{ padding: 12 }}>
          {item.quantity} {item.unit ?? ''}
        </td>
        <td style={{ padding: 12 }}>{item.flagType && <FlagBadge flagType={item.flagType} />}</td>
        <td style={{ padding: 12 }}>{item.flagReason}</td>
        <td style={{ padding: 12 }}>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onApprove(item.itemId, correctedQuantity ? Number(correctedQuantity) : null);
            }}
            style={{
              minWidth: touchTargets.minimum,
              minHeight: touchTargets.minimum,
              background: colors.ui.success,
              color: '#ffffff',
              border: 'none',
              borderRadius: 8,
              marginRight: 8,
              cursor: 'pointer',
            }}
          >
            ✓
          </button>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onReject(item.itemId, rejectReason || 'Sin motivo especificado');
            }}
            style={{
              minWidth: touchTargets.minimum,
              minHeight: touchTargets.minimum,
              background: colors.traffic.red,
              color: '#ffffff',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
            }}
          >
            ✗
          </button>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={5} style={{ padding: 16, background: colors.ui.surface }}>
            <p>
              <strong>Motivo:</strong> {item.flagReason ?? 'N/A'}
            </p>
            <p>
              <strong>Confianza de homologación:</strong>{' '}
              {item.homologationScore != null ? item.homologationScore.toFixed(2) : 'N/A'}
            </p>
            {item.historicalCounts && item.historicalCounts.length > 0 && (
              <>
                <p>
                  <strong>Histórico de referencia:</strong>
                </p>
                <ul>
                  {item.historicalCounts.map((entry) => (
                    <li key={entry.date}>
                      {entry.date}: {entry.quantity}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <label style={{ display: 'block', marginTop: 8 }}>
              Cantidad corregida (opcional):
              <input
                type="number"
                value={correctedQuantity}
                onChange={(event) => setCorrectedQuantity(event.target.value)}
                style={{ marginLeft: 8, minHeight: touchTargets.minimum }}
              />
            </label>
            <label style={{ display: 'block', marginTop: 8 }}>
              Motivo de rechazo:
              <input
                type="text"
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                style={{ marginLeft: 8, minHeight: touchTargets.minimum, width: '60%' }}
              />
            </label>
          </td>
        </tr>
      )}
    </>
  );
}
