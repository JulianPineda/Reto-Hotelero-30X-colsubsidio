import { colors, typography } from '../../theme';

export interface OfflineBannerProps {
  isOffline: boolean;
}

/**
 * CLAUDE.md §4: always visible when offline, fixed top position,
 * background #ffd000. CLAUDE.md §3.8: voice is disabled offline while
 * offline — this banner is the visible half of that rule; CountSession
 * disables VoiceButton itself.
 */
export function OfflineBanner({ isOffline }: OfflineBannerProps) {
  if (!isOffline) return null;

  return (
    <div
      role="status"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
        background: colors.primary.yellow,
        color: colors.ui.textPrimary,
        fontFamily: typography.fontFamily,
        fontWeight: 700,
        textAlign: 'center',
        padding: '8px 16px',
      }}
    >
      Sin conexión — modo offline activo. Los conteos se sincronizarán al reconectar.
    </div>
  );
}
