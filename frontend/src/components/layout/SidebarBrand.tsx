import React from 'react';

interface SidebarBrandProps {
  isCollapsed: boolean;
  onToggleCollapse?: () => void;
}

export const SidebarBrand: React.FC<SidebarBrandProps> = ({
  isCollapsed,
  onToggleCollapse,
}) => {
  if (isCollapsed) {
    return (
      <div className="flex flex-col items-center px-3 py-3">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="group relative h-8 w-8 cursor-pointer rounded-lg"
          title="Expand sidebar"
        >
          <div className="absolute inset-0 flex items-center justify-center transition-opacity duration-200 group-hover:opacity-0">
            <img src="/logo.png" alt="Logo" className="logo-on-dark h-7 w-7 object-contain" />
          </div>
          <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-surface-muted opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <svg
              className="h-4 w-4 text-text-secondary"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 5l7 7-7 7M6 5v14"
              />
            </svg>
          </div>
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between px-3 py-3">
      <img src="/logo.png" alt="Logo" className="logo-on-dark h-8 w-8 object-contain" />
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-muted hover:text-text-secondary"
        title="Collapse sidebar"
      >
        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M11 19l-7-7 7-7M18 5v14"
          />
        </svg>
      </button>
    </div>
  );
};
