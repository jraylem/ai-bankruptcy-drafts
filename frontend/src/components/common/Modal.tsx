import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | 'full';
  showCloseButton?: boolean;
  closeOnBackdropClick?: boolean;
  closeOnEscape?: boolean;
  /**
   * When true, draws an animated violet "traveling" border around the modal
   * panel — used as an ambient loading cue (e.g. the completed-draft viewer
   * while it fetches the docx envelope).
   */
  glowingBorder?: boolean;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  children,
  size = 'md',
  showCloseButton = true,
  closeOnBackdropClick = true,
  closeOnEscape = true,
  glowingBorder = false,
}) => {
  useEffect(() => {
    if (!isOpen || !closeOnEscape) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose, closeOnEscape]);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const getSizeClass = () => {
    switch (size) {
      case 'sm':
        return 'max-w-sm';
      case 'md':
        return 'max-w-md';
      case 'lg':
        return 'max-w-lg';
      case 'xl':
        return 'max-w-xl';
      case '2xl':
        return 'max-w-2xl';
      case '3xl':
        return 'max-w-[980px]';
      case 'full':
        return 'max-w-[90vw]';
      default:
        return 'max-w-lg';
    }
  };

  const handleBackdropClick = () => {
    if (closeOnBackdropClick) {
      onClose();
    }
  };

  const modalContent = (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-app-overlay transition-opacity backdrop-blur-sm"
        onClick={handleBackdropClick}
      />

      {/* Modal Container */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className={`relative w-full ${getSizeClass()}`}>
          {glowingBorder && (
            <svg
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-visible"
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient
                  id="glow-border-gradient-a"
                  x1="0%"
                  y1="0%"
                  x2="100%"
                  y2="100%"
                >
                  <stop offset="0%" stopColor="#ec4899" />
                  <stop offset="40%" stopColor="#a855f7" />
                  <stop offset="70%" stopColor="#8b5cf6" />
                  <stop offset="100%" stopColor="#60a5fa" />
                </linearGradient>
              </defs>
              <rect
                className="glow-border-line"
                x="0"
                y="0"
                width="100%"
                height="100%"
                rx="22"
                ry="22"
                fill="none"
                stroke="url(#glow-border-gradient-a)"
                strokeWidth="1"
                strokeLinecap="round"
                pathLength="100"
                strokeDasharray="22 78"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
          )}
          <div
            className="app-modal-panel relative w-full transform overflow-hidden rounded-[22px] border border-border bg-surface shadow-xl transition-all"
            onClick={(e) => e.stopPropagation()}
          >
          {/* Close Button */}
          {showCloseButton && (
            <button
              onClick={onClose}
              className="absolute top-4 right-4 z-10 cursor-pointer text-subtle transition-colors hover:text-text-secondary"
              aria-label="Close modal"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          )}

          {/* Modal Content */}
          {children}
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};
