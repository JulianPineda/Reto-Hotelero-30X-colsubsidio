import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OfflineBanner } from './index';

describe('OfflineBanner', () => {
  it('renders nothing when online', () => {
    const { container } = render(<OfflineBanner isOffline={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the offline message when offline', () => {
    render(<OfflineBanner isOffline={true} />);
    expect(screen.getByRole('status')).toHaveTextContent(/sin conexión/i);
  });
});
