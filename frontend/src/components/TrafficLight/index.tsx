import { colors } from '../../theme';

export type TrafficLightColor = 'red' | 'yellow' | 'green';

const TRAFFIC_COLORS: Record<TrafficLightColor, string> = {
  red: colors.traffic.red,
  yellow: colors.traffic.yellow,
  green: colors.traffic.green,
};

export interface TrafficLightProps {
  color: TrafficLightColor | null;
  isPerishable: boolean;
  /** Days until expiry — drives the tooltip text. Omit if unknown. */
  daysRemaining?: number | null;
}

function tooltipText(daysRemaining: number | null | undefined, color: TrafficLightColor): string {
  if (daysRemaining == null) return `Semáforo: ${color}`;
  if (daysRemaining < 0) return 'Vencido';
  if (daysRemaining === 0) return 'Vence hoy';
  return `Vence en ${daysRemaining} día${daysRemaining === 1 ? '' : 's'}`;
}

/**
 * CLAUDE.md §3.6 + T-017: dot de 16x16px, siempre visible cuando
 * is_perishable=true — incluida la lista de conteo, no solo el Supervisor
 * Dashboard.
 */
export function TrafficLight({ color, isPerishable, daysRemaining }: TrafficLightProps) {
  if (!isPerishable || !color) return null;

  const label = tooltipText(daysRemaining, color);

  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      style={{
        display: 'inline-block',
        width: 16,
        height: 16,
        borderRadius: '50%',
        background: TRAFFIC_COLORS[color],
        marginRight: 6,
      }}
    />
  );
}
