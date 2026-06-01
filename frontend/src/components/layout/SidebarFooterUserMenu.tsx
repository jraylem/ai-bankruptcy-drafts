import React from 'react';
import { UserMenu } from './UserMenu';

interface SidebarFooterUserMenuProps {
  isCollapsed: boolean;
}

export const SidebarFooterUserMenu: React.FC<SidebarFooterUserMenuProps> = ({
  isCollapsed,
}) => {
  if (isCollapsed) {
    return (
      <div className="flex justify-center p-3">
        <UserMenu isCollapsed />
      </div>
    );
  }

  return (
    <div className="p-3 pt-2">
      <UserMenu isCollapsed={false} />
    </div>
  );
};
