import { API_ENDPOINTS } from '@/constants';
import type { ApiResponse, User } from '@/types';
import { apiService } from './api';

export type OnboardingStatus = 'pending' | 'completed';

export interface OnboardingStatusResponse {
  onboarding_status: OnboardingStatus;
}

export interface FirmResponse {
  id: string;
  name: string;
  owner_email: string;
  subscription_status: string;
  plan_id?: string | null;
  seat_limit: number;
  onboarding_status: OnboardingStatus;
  is_active: boolean;
  created_at: string;
  address?: string | null;
  firm_type?: string | null;
  contact_number?: string | null;
}

export interface FirmUpdatePayload {
  name?: string;
  address?: string;
  firm_type?: string;
  contact_number?: string;
}

export interface InviteMemberPayload {
  email: string;
  permissions?: string[];
  role: 'admin' | 'member';
}

export interface InvitationResponse {
  id: string;
  email: string;
  role: string;
  expires_at: string;
}

export interface FirmMemberResponse {
  id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
  role_display: string;
  permissions?: string[] | null;
  is_active: boolean;
  invitation_accepted_at?: string | null;
}

export interface AcceptInvitationPayload {
  token: string;
  password?: string;
  first_name?: string;
  last_name?: string;
}

export interface AcceptInvitationResponse {
  /**
   * Backend still returns the access token for backward compatibility, but the
   * browser session is established through HttpOnly auth cookies.
   */
  access_token: string;
  token_type: string;
  user?: User;
}

export const firmsService = {
  getFirm(): Promise<ApiResponse<FirmResponse>> {
    return apiService.get<FirmResponse>(API_ENDPOINTS.FIRMS.ME);
  },

  getOnboardingStatus(): Promise<ApiResponse<OnboardingStatusResponse>> {
    return apiService.get<OnboardingStatusResponse>(API_ENDPOINTS.FIRMS.ONBOARDING_STATUS);
  },

  updateFirm(payload: FirmUpdatePayload): Promise<ApiResponse<FirmResponse>> {
    return apiService.patch<FirmResponse>(API_ENDPOINTS.FIRMS.ME, payload);
  },

  listMembers(): Promise<ApiResponse<FirmMemberResponse[]>> {
    return apiService.get<FirmMemberResponse[]>(API_ENDPOINTS.FIRMS.MEMBERS);
  },

  inviteMember(payload: InviteMemberPayload): Promise<ApiResponse<InvitationResponse>> {
    return apiService.post<InvitationResponse>(API_ENDPOINTS.FIRMS.INVITE, payload);
  },

  updateMemberPermissions(
    userId: string,
    permissions: string[]
  ): Promise<ApiResponse<FirmMemberResponse>> {
    return apiService.patch<FirmMemberResponse>(API_ENDPOINTS.FIRMS.MEMBER_PERMISSIONS(userId), {
      permissions,
    });
  },

  removeMember(userId: string): Promise<ApiResponse<{ message: string }>> {
    return apiService.delete<{ message: string }>(API_ENDPOINTS.FIRMS.MEMBER(userId));
  },

  listPendingInvitations(): Promise<ApiResponse<InvitationResponse[]>> {
    return apiService.get<InvitationResponse[]>(API_ENDPOINTS.SETTINGS.FIRM_INVITATIONS);
  },

  resendInvitation(invitationId: string): Promise<ApiResponse<InvitationResponse>> {
    return apiService.post<InvitationResponse>(
      API_ENDPOINTS.SETTINGS.RESEND_FIRM_INVITATION(invitationId)
    );
  },

  revokeInvitation(invitationId: string): Promise<ApiResponse<{ message: string }>> {
    return apiService.delete<{ message: string }>(
      API_ENDPOINTS.SETTINGS.FIRM_INVITATION(invitationId)
    );
  },

  acceptInvitation(payload: AcceptInvitationPayload): Promise<ApiResponse<AcceptInvitationResponse>> {
    return apiService.post<AcceptInvitationResponse>(API_ENDPOINTS.FIRMS.ACCEPT_INVITE, payload);
  },
};
