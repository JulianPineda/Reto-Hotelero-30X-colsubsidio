import { colors } from '../../theme';

export type FlagType = 'threshold' | 'trend' | 'both';

const FLAG_LABELS: Record<FlagType, string> = {
  threshold: 'Umbral',
  trend: 'Tendencia',
  both: 'Umbral + Tendencia',
};

// CLAUDE.md §2 — colors sourced from theme.ts, never ad-hoc hex.
const FLAG_COLORS: Record<FlagType, string> = {
  threshold: colors.flag.threshold,
  trend: colors.flag.trend,
  both: colors.flag.both,
};

export interface FlagBadgeProps {
  flagType: FlagType;
}

export function FlagBadge({ flagType }: FlagBadgeProps) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: 999,
        fontSize: '0.75rem',
        fontWeight: 700,
        color: '#ffffff',
        background: FLAG_COLORS[flagType],
        whiteSpace: 'nowrap',
      }}
    >
      {FLAG_LABELS[flagType]}
    </span>
  );
}
