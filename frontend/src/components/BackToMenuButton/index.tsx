import { useNavigate } from 'react-router-dom';
import { colors, touchTargets, typography } from '../../theme';

export interface BackToMenuButtonProps {
  /** 'onDark' renders a translucent white style for use inside PageHeader's
   * brand-blue bar; 'default' (a plain outlined button) is for anywhere else. */
  variant?: 'default' | 'onDark';
}

/**
 * Both the operator (CountSession) and supervisor (SupervisorDashboard)
 * screens were dead ends before this — the only way back to the role menu
 * was the browser's back button, which re-triggers the router-state guard
 * in App.tsx (CountSessionRoute/SupervisorDashboardRoute) and bounces to
 * "/" anyway, just with an extra confusing hop. This makes that path
 * explicit and one click.
 */
export function BackToMenuButton({ variant = 'default' }: BackToMenuButtonProps) {
  const navigate = useNavigate();
  const onDark = variant === 'onDark';

  return (
    <button
      type="button"
      onClick={() => navigate('/')}
      style={{
        minHeight: touchTargets.minimum,
        padding: '0 16px',
        background: onDark ? 'rgba(255,255,255,0.14)' : 'none',
        border: `1px solid ${onDark ? 'rgba(255,255,255,0.5)' : colors.ui.border}`,
        borderRadius: 8,
        color: onDark ? '#ffffff' : colors.neutral.grafito,
        fontFamily: typography.fontFamily,
        fontSize: typography.sizes.base,
        fontWeight: 600,
        cursor: 'pointer',
        whiteSpace: 'nowrap',
      }}
    >
      ‹ Menú principal
    </button>
  );
}
