import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  closeOnBackdropClick?: boolean;
  closeOnEscape?: boolean;
  ariaLabelledBy?: string;
  ariaLabel?: string;
  initialFocusRef?: React.RefObject<HTMLElement>;
  returnFocusRef?: React.RefObject<HTMLElement>;
  panelClassName?: string;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  children,
  closeOnBackdropClick = true,
  closeOnEscape = true,
  ariaLabelledBy,
  ariaLabel,
  initialFocusRef,
  returnFocusRef,
  panelClassName,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const fallbackFocusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen || !closeOnEscape) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose, closeOnEscape]);

  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const target = initialFocusRef?.current ?? fallbackFocusRef.current;
    target?.focus();
  }, [isOpen, initialFocusRef]);

  useEffect(() => {
    if (isOpen) return;
    returnFocusRef?.current?.focus();
  }, [isOpen, returnFocusRef]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusable = panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (focusable.length === 0) {
        e.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey) {
        if (active === first || !panel.contains(active)) {
          e.preventDefault();
          last.focus();
        }
        return;
      }
      if (active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  if (!isOpen) return null;

  const handleBackdropClick = () => {
    if (closeOnBackdropClick) onClose();
  };

  const panelClasses = [
    'absolute right-0 top-0 flex h-full flex-col bg-surface shadow-2xl',
    'w-full md:w-[60vw] md:min-w-[720px] md:max-w-[1100px]',
    'motion-safe:transition-transform motion-safe:duration-200',
    'border-l border-border',
    panelClassName ?? '',
  ].join(' ');

  const content = (
    <div className="fixed inset-0 z-40">
      <div
        className="absolute inset-0 bg-app-overlay backdrop-blur-sm"
        onClick={handleBackdropClick}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={ariaLabelledBy}
        aria-label={ariaLabel}
        className={panelClasses}
      >
        {!initialFocusRef && (
          <div
            ref={fallbackFocusRef}
            tabIndex={-1}
            aria-hidden="true"
            className="sr-only outline-none"
          />
        )}
        {children}
      </div>
    </div>
  );

  return createPortal(content, document.body);
};
