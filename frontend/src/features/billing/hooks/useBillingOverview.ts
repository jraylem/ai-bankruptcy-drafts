import { useQuery } from '@tanstack/react-query';
import { fetchBillingCostDrivers, fetchBillingOverview } from '../api/billing.api';
import type { BillingCostDriversGroup } from '../types/billing.types';

export const billingKeys = {
  all: ['billing'] as const,
  costDrivers: (group: BillingCostDriversGroup) =>
    [...billingKeys.all, 'cost-drivers', group] as const,
  overview: () => [...billingKeys.all, 'overview'] as const,
  subscription: () => [...billingKeys.all, 'subscription'] as const,
};

export const useBillingOverview = (enabled = true) =>
  useQuery({
    enabled,
    queryKey: billingKeys.overview(),
    queryFn: fetchBillingOverview,
    retry: false,
    staleTime: 60_000,
  });

export const useBillingCostDrivers = (group: BillingCostDriversGroup, enabled = true) =>
  useQuery({
    enabled,
    queryKey: billingKeys.costDrivers(group),
    queryFn: () => fetchBillingCostDrivers(group),
    retry: false,
    staleTime: 60_000,
  });
