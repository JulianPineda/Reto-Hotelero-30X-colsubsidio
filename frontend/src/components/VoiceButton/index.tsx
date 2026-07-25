import { useCallback, useRef } from 'react';
import { colors, touchTargets, typography } from '../../theme';

export type VoiceButtonPhase = 'idle' | 'listening' | 'processing' | 'disabled';

const PHASE_LABELS: Record<VoiceButtonPhase, string> = {
  idle: 'Mantén presionado para hablar',
  listening: 'Escuchando…',
  processing: 'Procesando…',
  disabled: 'No disponible sin conexión',
};

// CLAUDE.md §2 — colors sourced from theme.ts, never ad-hoc hex.
const PHASE_COLORS: Record<VoiceButtonPhase, string> = {
  idle: colors.primary.blue,
  listening: colors.primary.yellow,
  processing: colors.neutral.grafito,
  disabled: colors.neutral.grafito40,
};

export interface VoiceButtonProps {
  phase: VoiceButtonPhase;
  onPressStart: () => void;
  onPressEnd: () => void;
}

/**
 * CLAUDE.md §4: minimum 120×120px, the primary affordance of CountSession.
 * Push-to-talk — press-and-hold, not a toggle — so release always maps to
 * ptt_stop even if the pointer leaves the button while still held.
 */
export function VoiceButton({ phase, onPressStart, onPressEnd }: VoiceButtonProps) {
  const isPressedRef = useRef(false);

  const handleStart = useCallback(() => {
    if (phase === 'disabled' || phase === 'processing' || isPressedRef.current) return;
    isPressedRef.current = true;
    onPressStart();
  }, [phase, onPressStart]);

  const handleEnd = useCallback(() => {
    if (!isPressedRef.current) return;
    isPressedRef.current = false;
    onPressEnd();
  }, [onPressEnd]);

  return (
    <button
      type="button"
      aria-label={PHASE_LABELS[phase]}
      disabled={phase === 'disabled'}
      onMouseDown={handleStart}
      onMouseUp={handleEnd}
      onMouseLeave={handleEnd}
      onTouchStart={(event) => {
        event.preventDefault();
        handleStart();
      }}
      onTouchEnd={(event) => {
        event.preventDefault();
        handleEnd();
      }}
      style={{
        width: touchTargets.voiceButton,
        height: touchTargets.voiceButton,
        borderRadius: '50%',
        border: 'none',
        background: PHASE_COLORS[phase],
        color: '#ffffff',
        fontFamily: typography.fontFamily,
        fontSize: typography.sizes.label,
        fontWeight: 700,
        cursor: phase === 'disabled' ? 'not-allowed' : 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        padding: 8,
        boxShadow: phase === 'listening' ? `0 0 0 8px ${colors.primary.yellow}33` : 'none',
        userSelect: 'none',
      }}
    >
      {PHASE_LABELS[phase]}
    </button>
  );
}
