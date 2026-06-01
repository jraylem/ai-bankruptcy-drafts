import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { FiLayout, FiMoon, FiSettings, FiSun } from 'react-icons/fi';
import { LuLayoutTemplate } from 'react-icons/lu';
import { useAuthSession, useLogoutMutation } from '@/features/auth/queries';
import { APP_PERMISSIONS, hasPermission } from '@/features/auth/permissions';
import { useThemeStore } from '@/stores/useThemeStore';
import { ThemeModeToggle } from '@/components/theme/ThemeModeToggle';
import type { User } from '@/types';

interface UserMenuProps {
  isCollapsed?: boolean;
}

export const UserMenu: React.FC<UserMenuProps> = ({ isCollapsed = false }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ bottom: 0, left: 0 });
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const { user } = useAuthSession();
  const logoutMutation = useLogoutMutation();
  const resolvedMode = useThemeStore((state) => state.resolvedMode);
  const isDarkMode = resolvedMode === 'dark';
  const navigate = useNavigate();
  const location = useLocation();
  const isSettingsPage =
    location.pathname === '/settings' || location.pathname.startsWith('/settings/');
  const canAccessAdminSettings = hasPermission(user, APP_PERMISSIONS.adminDashboard);
  const isStudioPage = location.pathname.startsWith('/studio');
  const isStudioV2Page = location.pathname === '/studio-v2';

  // Calculate dropdown position when opening
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        bottom: window.innerHeight - rect.top + 8,
        left: rect.left,
      });
    }
  }, [isOpen]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  if (!user) {
    return null;
  }

  // Get user initials for avatar
  const getInitials = (user: User): string => {
    if (user.first_name && user.last_name) {
      return `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
    }
    if (user.username) {
      return user.username.slice(0, 2).toUpperCase();
    }
    return user.email?.slice(0, 2).toUpperCase() || 'U';
  };

  const getUserDisplayName = (user: User): string => {
    if (user.first_name && user.last_name) {
      return `${user.first_name} ${user.last_name}`;
    }
    return user.username || user.email || 'User';
  };

  const handleLogout = () => {
    setIsOpen(false);
    logoutMutation.mutate(undefined, {
      onSettled: () => {
        navigate('/login', { replace: true });
      },
    });
  };

  const handleAdminSettings = () => {
    setIsOpen(false);
    navigate('/settings');
  };

  const handleStudio = () => {
    setIsOpen(false);
    navigate('/studio');
  };

  const handleStudioV2 = () => {
    setIsOpen(false);
    navigate('/studio-v2');
  };

  const dropdownContent = (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[999]" onClick={() => setIsOpen(false)} />

      {/* Dropdown Content - Fixed position */}
      <div
        ref={menuRef}
        className="fixed z-[1000] w-64 rounded-xl border border-border bg-surface py-2 shadow-lg animate-slide-up"
        style={{
          bottom: dropdownPosition.bottom,
          left: dropdownPosition.left,
        }}
      >
        {/* User Info */}
        <div className="border-b border-border/60 px-3 py-2">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center text-white font-semibold shadow-md">
              {getInitials(user)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-text truncate">{getUserDisplayName(user)}</p>
              <p className="text-xs text-muted truncate">{user.email}</p>
            </div>
          </div>
        </div>

        {/* Menu Items */}
        <div className="py-1">
          <button
            onClick={handleStudio}
            className={`w-full px-3 py-2 text-left text-sm transition-colors duration-150 flex items-center gap-3 cursor-pointer ${
              isStudioPage
                ? 'bg-app-accent-soft text-app-accent-text'
                : 'text-text-secondary hover:bg-surface-muted/70'
            }`}
          >
            <LuLayoutTemplate className="w-5 h-5" />
            <span className="font-medium">Template Studio</span>
          </button>
          <button
            onClick={handleStudioV2}
            className={`w-full px-3 py-2 text-left text-sm transition-colors duration-150 flex items-center gap-3 cursor-pointer ${
              isStudioV2Page
                ? 'bg-app-accent-soft text-app-accent-text'
                : 'text-text-secondary hover:bg-surface-muted/70'
            }`}
          >
            <FiLayout className="h-5 w-5" />
            <span className="font-medium flex-1">Template Studio V2</span>
            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-900">
              Mocked
            </span>
          </button>
          {canAccessAdminSettings ? (
            <button
              onClick={handleAdminSettings}
              className={`w-full px-3 py-2 text-left text-sm transition-colors duration-150 flex items-center gap-3 cursor-pointer ${
                isSettingsPage
                  ? 'bg-app-accent-soft text-app-accent-text'
                  : 'text-text-secondary hover:bg-surface-muted/70'
              }`}
            >
              <FiSettings className="h-5 w-5" />
              <span className="font-medium">Admin Settings</span>
            </button>
          ) : null}
          <div className="w-full px-3 py-1 text-sm transition-colors duration-150 flex items-center justify-between">
            <div className="flex items-center gap-3 text-text-secondary">
              {isDarkMode ? <FiMoon className="w-5 h-5" /> : <FiSun className="w-5 h-5" />}
              <span className="font-medium">{isDarkMode ? 'Dark mode' : 'Light mode'}</span>
            </div>
            <ThemeModeToggle className="scale-90 origin-right" />
          </div>
          <button
            onClick={handleLogout}
            className="flex w-full cursor-pointer items-center gap-3 px-3 py-2 text-left text-sm text-app-danger-text transition-colors duration-150 hover:bg-app-danger-soft"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
              />
            </svg>
            <span className="font-medium">Log out</span>
          </button>
        </div>
      </div>

      <style>{`
        @keyframes slide-up {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-slide-up {
          animation: slide-up 0.2s ease-out;
        }
      `}</style>
    </>
  );

  // Collapsed view - just avatar
  if (isCollapsed) {
    return (
      <div className="relative">
        <button
          ref={buttonRef}
          onClick={() => setIsOpen(!isOpen)}
          className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center text-white font-medium text-xs shadow-sm hover:scale-105 transition-transform cursor-pointer relative"
        >
          {getInitials(user)}
          {/* Online indicator */}
          <div className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 border-2 border-white rounded-full"></div>
        </button>

        {/* Dropdown Menu - Rendered via Portal */}
        {isOpen && createPortal(dropdownContent, document.body)}
      </div>
    );
  }

  // Expanded view - full user menu
  return (
    <div className="relative">
      {/* User Avatar Button */}
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 transition-all duration-200 hover:bg-surface-muted cursor-pointer"
      >
        {/* Avatar */}
        <div className="relative flex-shrink-0">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center text-white font-medium text-xs shadow-sm group-hover:scale-105 transition-transform duration-200">
            {getInitials(user)}
          </div>
          {/* Online indicator */}
          <div className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 border-2 border-white rounded-full"></div>
        </div>

        {/* User Info */}
        <div className="flex-1 min-w-0 text-left">
          <p className="text-xs font-medium text-text truncate">{getUserDisplayName(user)}</p>
          <p className="text-[11px] text-muted truncate">{user.email}</p>
        </div>
      </button>

      {/* Dropdown Menu - Rendered via Portal */}
      {isOpen && createPortal(dropdownContent, document.body)}
    </div>
  );
};
