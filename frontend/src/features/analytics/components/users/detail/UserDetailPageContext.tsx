import type { Dispatch, SetStateAction } from 'react';
import { createContext, useContext } from 'react';
import type {
  UserDetailActivityQueryState,
  UserDetailSessionsQueryState,
  UserDetailViewModel,
} from '@/features/analytics/types';

interface UserDetailPageContextValue {
  detail: UserDetailViewModel;
  sessionsQuery: UserDetailSessionsQueryState;
  setSessionsQuery: Dispatch<SetStateAction<UserDetailSessionsQueryState>>;
  activityQuery: UserDetailActivityQueryState;
  setActivityQuery: Dispatch<SetStateAction<UserDetailActivityQueryState>>;
  isExporting: boolean;
  handleExportUserXlsx: () => void;
}

export const UserDetailPageContext = createContext<UserDetailPageContextValue | null>(null);

export const useUserDetailPageContext = (): UserDetailPageContextValue => {
  const context = useContext(UserDetailPageContext);

  if (!context) {
    throw new Error('useUserDetailPageContext must be used within UserDetailPageProvider');
  }

  return context;
};
