import { useMutation, useQuery } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import { useToastStore } from '@/stores/useToastStore';
import { fetchSettingsFirm, updateSettingsFirm } from '../api';
import type { UpdateSettingsFirmRequest } from '../api';
import { settingsKeys } from './useSettingsMembers';

export const useSettingsFirm = () =>
  useQuery({
    queryKey: settingsKeys.firm(),
    queryFn: fetchSettingsFirm,
    retry: false,
    staleTime: 60_000,
  });

export const useUpdateSettingsFirm = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: (request: UpdateSettingsFirmRequest) => updateSettingsFirm(request),
    onSuccess: (firm) => {
      queryClient.setQueryData(settingsKeys.firm(), firm);
      addToast('Firm profile updated', 'success');
    },
    onError: (error) => {
      addToast(error instanceof Error ? error.message : 'Unable to update firm profile', 'error');
    },
  });
};
