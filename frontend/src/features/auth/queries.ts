import { useMutation, useQuery } from '@tanstack/react-query';
import { authService } from '@/services/auth.service';
import type { User } from '@/types';
import { queryClient } from '@/lib/queryClient';

export const CURRENT_USER_STALE_TIME_MS = 5 * 60 * 1000;

export const authKeys = {
  all: ['auth'] as const,
  currentUser: () => [...authKeys.all, 'me'] as const,
};

const clearNonAuthQueryCache = () => {
  queryClient.removeQueries({
    predicate: (query) => query.queryKey[0] !== authKeys.all[0],
  });
};

const clearCurrentUser = () => {
  queryClient.setQueryData(authKeys.currentUser(), null);
};

export const fetchCurrentUser = async (): Promise<User | null> => {
  const response = await authService.getCurrentUser();
  return response.data ?? null;
};

export const useCurrentUserQuery = () => {
  return useQuery({
    queryKey: authKeys.currentUser(),
    queryFn: fetchCurrentUser,
    retry: false,
    staleTime: CURRENT_USER_STALE_TIME_MS,
  });
};

export const useAuthSession = () => {
  const currentUserQuery = useCurrentUserQuery();
  const user = currentUserQuery.data ?? null;
  const isAccepted = user?.is_accepted !== false;

  return {
    user,
    isAuthenticated: Boolean(user && isAccepted),
    isInitializing: currentUserQuery.isLoading,
    isFetching: currentUserQuery.isFetching,
    error: currentUserQuery.error,
  };
};

export class AuthApiError extends Error {
  code?: string;
  constructor(message: string, code?: string) {
    super(message);
    this.name = 'AuthApiError';
    this.code = code;
  }
}

export const EMAIL_NOT_CONFIRMED_CODE = 'email_not_confirmed';
export const ACCOUNT_NOT_ACCEPTED_CODE = 'account_not_accepted';

export const useLoginMutation = () => {
  return useMutation({
    mutationFn: async (credentials: { email: string; password: string }) => {
      const response = await authService.login(credentials);
      if (response.error || !response.data?.user) {
        throw new AuthApiError(response.error || 'Login failed', response.code);
      }
      if (response.data.user.is_accepted === false) {
        clearCurrentUser();
        throw new AuthApiError('Account pending approval', ACCOUNT_NOT_ACCEPTED_CODE);
      }
      return response.data.user;
    },
    onSuccess: (user) => {
      clearNonAuthQueryCache();
      queryClient.setQueryData(authKeys.currentUser(), user);
    },
  });
};

export const useRegisterMutation = () => {
  return useMutation({
    mutationFn: async (data: {
      email: string;
      password: string;
      firstName: string;
      lastName: string;
      firmName: string;
    }) => {
      const response = await authService.register({
        email: data.email,
        password: data.password,
        first_name: data.firstName,
        last_name: data.lastName,
        firm_name: data.firmName,
      });

      if (response.error) {
        throw new AuthApiError(response.error, response.code);
      }

      return { email: data.email };
    },
  });
};

export const useVerifyEmailMutation = () => {
  return useMutation({
    mutationFn: async (token: string) => {
      const response = await authService.verifyEmail(token);
      if (response.error || !response.data?.user) {
        throw new AuthApiError(response.error || 'Verification failed', response.code);
      }
      if (response.data.user.is_accepted === false) {
        clearCurrentUser();
        throw new AuthApiError('Account pending approval', ACCOUNT_NOT_ACCEPTED_CODE);
      }
      return response.data.user;
    },
    onSuccess: (user) => {
      clearNonAuthQueryCache();
      queryClient.setQueryData(authKeys.currentUser(), user);
    },
  });
};

export const useResendVerificationMutation = () => {
  return useMutation({
    mutationFn: async (email: string) => {
      const response = await authService.resendVerification(email);
      if (response.error) {
        throw new AuthApiError(response.error, response.code);
      }
    },
  });
};

export const useLogoutMutation = () => {
  return useMutation({
    mutationFn: async () => {
      await authService.logout();
    },
    onMutate: () => {
      clearCurrentUser();
      clearNonAuthQueryCache();
    },
    onSettled: () => {
      clearCurrentUser();
      clearNonAuthQueryCache();
    },
  });
};
