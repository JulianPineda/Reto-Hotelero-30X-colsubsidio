import { useNavigate } from 'react-router-dom';
import { colors, touchTargets, typography } from '../../theme';

/**
 * Both the operator (CountSession) and supervisor (SupervisorDashboard)
 * screens were dead ends before this — the only way back to the role menu
 * was the browser's back button, which re-triggers the router-state guard
 * in App.tsx (CountSessionRoute/SupervisorDashboardRoute) and bounces to
 * "/" anyway, just with an extra confusing hop. This makes that path
 * explicit and one click.
 */
export function BackToMenuButton() {
  const navigate = useNavigate();

  return (
    <button
      type="button"
      onClick={() => navigate('/')}
      style={{
        minHeight: touchTargets.minimum,
        padding: '0 16px',
        background: 'none',
        border: `1px solid ${colors.ui.border}`,
        borderRadius: 8,
        color: colors.neutral.grafito,
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
