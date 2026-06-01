import React from 'react';
import { Modal } from '@/components/common';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  /** Optional structured content rendered below `message`. Use for lists
   * (e.g. a parent-templates list in the force-delete conflict path)
   * that don't compress cleanly into a single-paragraph string. */
  detail?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'danger' | 'warning';
  /** When true: disable both buttons, show a spinner on the destructive
   * button, and block backdrop / Esc dismiss. Prevents double-click +
   * mid-flight cancel during the BE round-trip. */
  isProcessing?: boolean;
}

export const DeleteConfirmModal: React.FC<DeleteConfirmModalProps> = ({
  isOpen,
  title,
  message,
  detail,
  confirmText = 'Delete',
  cancelText = 'Cancel',
  onConfirm,
  onCancel,
  variant = 'danger',
  isProcessing = false,
}) => {
  const handleCancel = () => {
    if (isProcessing) return;
    onCancel();
  };
  const getVariantColors = () => {
    switch (variant) {
      case 'danger':
        return {
          icon: 'text-app-danger-text',
          iconBg: 'bg-app-danger-soft',
          button: 'bg-red-600 hover:bg-red-700 focus:ring-app-danger-text',
        };
      case 'warning':
        return {
          icon: 'text-app-warning-text',
          iconBg: 'bg-app-warning-soft',
          button: 'bg-yellow-600 hover:bg-yellow-700 focus:ring-yellow-500',
        };
    }
  };

  const colors = getVariantColors();

  return (
    <Modal isOpen={isOpen} onClose={handleCancel} size="lg">
      {/* Modal Content */}
      <div className="bg-surface px-4 pb-4 pt-5 sm:p-6 sm:pb-4">
        <div className="sm:flex sm:items-start">
          {/* Icon */}
          <div
            className={`mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full ${colors.iconBg} sm:mx-0 sm:h-10 sm:w-10`}
          >
            <svg
              className={`h-6 w-6 ${colors.icon}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>

          {/* Content */}
          <div className="mt-3 text-center sm:ml-4 sm:mt-0 sm:text-left flex-1">
            <h3 className="text-lg font-semibold leading-6 text-text">{title}</h3>
            <div className="mt-2 space-y-3">
              <p className="text-sm text-muted">{message}</p>
              {detail}
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="gap-2 bg-surface-muted px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6">
        <button
          type="button"
          onClick={onConfirm}
          disabled={isProcessing}
          aria-busy={isProcessing}
          className={`inline-flex w-full items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold text-white shadow-sm sm:w-auto transition-colors ${colors.button} ${isProcessing ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
        >
          {isProcessing && (
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          )}
          {confirmText}
        </button>
        <button
          type="button"
          onClick={handleCancel}
          disabled={isProcessing}
          className={`mt-3 inline-flex w-full justify-center rounded-md bg-surface px-4 py-2 text-sm font-semibold text-text shadow-sm ring-1 ring-inset ring-border transition-colors hover:bg-surface-muted sm:mt-0 sm:w-auto ${isProcessing ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
        >
          {cancelText}
        </button>
      </div>
    </Modal>
  );
};
