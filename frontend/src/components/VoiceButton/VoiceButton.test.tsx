import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { VoiceButton } from './index';

describe('VoiceButton', () => {
  it('calls onPressStart on mouse down and onPressEnd on mouse up', () => {
    const onPressStart = vi.fn();
    const onPressEnd = vi.fn();
    render(<VoiceButton phase="idle" onPressStart={onPressStart} onPressEnd={onPressEnd} />);

    const button = screen.getByRole('button');
    fireEvent.mouseDown(button);
    expect(onPressStart).toHaveBeenCalledTimes(1);

    fireEvent.mouseUp(button);
    expect(onPressEnd).toHaveBeenCalledTimes(1);
  });

  it('does not fire onPressStart twice without a release in between', () => {
    const onPressStart = vi.fn();
    render(<VoiceButton phase="idle" onPressStart={onPressStart} onPressEnd={vi.fn()} />);

    const button = screen.getByRole('button');
    fireEvent.mouseDown(button);
    fireEvent.mouseDown(button);

    expect(onPressStart).toHaveBeenCalledTimes(1);
  });

  it('mouse leaving the button while pressed still triggers onPressEnd', () => {
    const onPressEnd = vi.fn();
    render(<VoiceButton phase="idle" onPressStart={vi.fn()} onPressEnd={onPressEnd} />);

    const button = screen.getByRole('button');
    fireEvent.mouseDown(button);
    fireEvent.mouseLeave(button);

    expect(onPressEnd).toHaveBeenCalledTimes(1);
  });

  it('is disabled and ignores press when phase is disabled', () => {
    const onPressStart = vi.fn();
    render(<VoiceButton phase="disabled" onPressStart={onPressStart} onPressEnd={vi.fn()} />);

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();

    fireEvent.mouseDown(button);
    expect(onPressStart).not.toHaveBeenCalled();
  });

  it('ignores press start while processing', () => {
    const onPressStart = vi.fn();
    render(<VoiceButton phase="processing" onPressStart={onPressStart} onPressEnd={vi.fn()} />);

    fireEvent.mouseDown(screen.getByRole('button'));
    expect(onPressStart).not.toHaveBeenCalled();
  });
});
