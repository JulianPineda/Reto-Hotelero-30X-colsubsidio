import { colors, touchTargets } from '../../theme';

export interface BulkActionBarProps {
  pendingCount: number;
  onApproveAll: () => void;
}

export function BulkActionBar({ pendingCount, onApproveAll }: BulkActionBarProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 0',
      }}
    >
      <span>{pendingCount} ítems pendientes de revisión</span>
      <button
        type="button"
        onClick={onApproveAll}
        disabled={pendingCount === 0}
        style={{
          minHeight: touchTargets.minimum,
          padding: '0 20px',
          background: colors.ui.success,
          color: '#ffffff',
          border: 'none',
          borderRadius: 8,
          fontWeight: 600,
          cursor: pendingCount === 0 ? 'not-allowed' : 'pointer',
          opacity: pendingCount === 0 ? 0.5 : 1,
        }}
      >
        Aprobar todos ✓
      </button>
    </div>
  );
}
