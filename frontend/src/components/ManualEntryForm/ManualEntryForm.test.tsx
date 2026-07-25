import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ManualEntryForm } from './index';

describe('ManualEntryForm', () => {
  it('submit button is disabled until article, quantity and unit are filled', () => {
    render(<ManualEntryForm onSubmit={vi.fn()} />);

    expect(screen.getByRole('button', { name: /guardar/i })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/artículo/i), { target: { value: 'Harina' } });
    fireEvent.change(screen.getByLabelText(/cantidad/i), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText(/unidad/i), { target: { value: 'kg' } });

    expect(screen.getByRole('button', { name: /guardar/i })).toBeEnabled();
  });

  it('submits parsed values and clears the form', () => {
    const onSubmit = vi.fn();
    render(<ManualEntryForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText(/artículo/i), { target: { value: 'Harina de Trigo' } });
    fireEvent.change(screen.getByLabelText(/cantidad/i), { target: { value: '20.5' } });
    fireEvent.change(screen.getByLabelText(/unidad/i), { target: { value: 'kg' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      article: 'Harina de Trigo',
      quantity: 20.5,
      unit: 'kg',
      expiryDate: null,
    });
    expect(screen.getByLabelText(/artículo/i)).toHaveValue('');
  });

  it('includes the expiry date when provided', () => {
    const onSubmit = vi.fn();
    render(<ManualEntryForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText(/artículo/i), { target: { value: 'Leche' } });
    fireEvent.change(screen.getByLabelText(/cantidad/i), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/unidad/i), { target: { value: 'L' } });
    fireEvent.change(screen.getByLabelText(/fecha de vencimiento/i), { target: { value: '2026-08-15' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      article: 'Leche',
      quantity: 2,
      unit: 'L',
      expiryDate: '2026-08-15',
    });
  });
});
