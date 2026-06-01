import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { Drawer } from '@/components/common/Drawer';

describe('<Drawer />', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <Drawer isOpen={false} onClose={vi.fn()}>
        <div>panel content</div>
      </Drawer>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders children when open via portal to body', () => {
    render(
      <Drawer isOpen={true} onClose={vi.fn()}>
        <div>panel content</div>
      </Drawer>,
    );
    expect(screen.getByText('panel content')).toBeInTheDocument();
  });

  it('calls onClose when ESC is pressed', () => {
    const onClose = vi.fn();
    render(
      <Drawer isOpen={true} onClose={onClose}>
        <button>focused</button>
      </Drawer>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT call onClose on ESC when closeOnEscape=false', () => {
    const onClose = vi.fn();
    render(
      <Drawer isOpen={true} onClose={onClose} closeOnEscape={false}>
        <div>x</div>
      </Drawer>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose on backdrop click by default', () => {
    const onClose = vi.fn();
    render(
      <Drawer isOpen={true} onClose={onClose}>
        <div>x</div>
      </Drawer>,
    );
    const backdrop = document.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT call onClose on backdrop click when closeOnBackdropClick=false', () => {
    const onClose = vi.fn();
    render(
      <Drawer isOpen={true} onClose={onClose} closeOnBackdropClick={false}>
        <div>x</div>
      </Drawer>,
    );
    const backdrop = document.querySelector('[aria-hidden="true"]') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('sets aria-modal="true" and role="dialog" on the panel', () => {
    render(
      <Drawer isOpen={true} onClose={vi.fn()} ariaLabel="Test drawer">
        <div>x</div>
      </Drawer>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('traps Tab focus inside the panel', () => {
    render(
      <Drawer isOpen={true} onClose={vi.fn()}>
        <button>first</button>
        <button>middle</button>
        <button>last</button>
      </Drawer>,
    );
    const first = screen.getByRole('button', { name: 'first' });
    const last = screen.getByRole('button', { name: 'last' });
    last.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(first);
  });
});
