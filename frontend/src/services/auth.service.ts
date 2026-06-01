import { apiService } from './api';
import { API_ENDPOINTS } from '@/constants';
import type { User, ApiResponse } from '@/types';

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

interface LoginCredentials {
  email: string;
  password: string;
}

interface RegisterData {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  firm_name: string;
}

type UserApprovalAction = 'approve' | 'deny';

interface UserApprovalResponse {
  message: string;
  status: UserApprovalAction;
}

export const authService = {
  async login(credentials: LoginCredentials): Promise<ApiResponse<LoginResponse>> {
    return apiService.post<LoginResponse>(API_ENDPOINTS.AUTH.LOGIN, credentials);
  },

  async register(userData: RegisterData): Promise<ApiResponse<void>> {
    return apiService.post<void>(API_ENDPOINTS.AUTH.REGISTER, userData);
  },

  async logout(): Promise<ApiResponse<void>> {
    return apiService.post<void>(API_ENDPOINTS.AUTH.LOGOUT);
  },

  async getCurrentUser(): Promise<ApiResponse<User>> {
    return apiService.get<User>(API_ENDPOINTS.AUTH.ME);
  },

  async refreshToken(): Promise<ApiResponse<LoginResponse>> {
    return apiService.post<LoginResponse>(API_ENDPOINTS.AUTH.REFRESH);
  },

  async verifyEmail(token: string): Promise<ApiResponse<LoginResponse>> {
    return apiService.post<LoginResponse>(API_ENDPOINTS.AUTH.VERIFY_EMAIL, { token });
  },

  async resendVerification(email: string): Promise<ApiResponse<void>> {
    return apiService.post<void>(API_ENDPOINTS.AUTH.RESEND_VERIFICATION, { email });
  },

  async approveUserAccess(
    token: string,
    action: UserApprovalAction
  ): Promise<ApiResponse<UserApprovalResponse>> {
    const query = new URLSearchParams({ action });
    return apiService.get<UserApprovalResponse>(
      `${API_ENDPOINTS.AUTH.USER_APPROVAL(token)}?${query.toString()}`
    );
  },
};
