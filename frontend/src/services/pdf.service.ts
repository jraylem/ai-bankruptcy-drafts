

import { apiService } from './api';
import { API_ENDPOINTS, API_BASE_URL } from '@/constants';
import type { ApiResponse } from '@/types';
import { withCookieCredentials } from '@/features/auth/auth.requests';

interface UploadPDFResponse {
  message: string;
  id?: string;
  url?: string;
  num_pages?: number;
}

interface PDFMetadata {
  id: string;
  filename: string;
  file_path: string;
  download_url: string;
  original_filename: string;
  file_size: number;
  uploaded_at: string;
}

interface PDFListResponse {
  session_id: string;
  pdfs: PDFMetadata[];
}

interface ExtractPetitionResponse {
  message: string;
  session_id: string;
  case_number: string;
  filename: string;
  download_url: string;
  status?: 'available_to_download';
}

export const pdfService = {
  async uploadPDF(
    file: File,
    sessionId: string,
    collectionName: string = 'default_collection'
  ): Promise<ApiResponse<UploadPDFResponse>> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', sessionId);
    formData.append('collection_name', collectionName);

    return apiService.post<UploadPDFResponse>(API_ENDPOINTS.PDF.UPLOAD, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 60000, // 1 minute timeout for file uploads
    });
  },

  async deletePDFFromSession(sessionId: string): Promise<ApiResponse<void>> {
    return apiService.delete<void>(API_ENDPOINTS.PDF.DELETE_FROM_SESSION(sessionId));
  },

  async listPDFsBySession(sessionId: string): Promise<ApiResponse<PDFListResponse>> {
    return apiService.get<PDFListResponse>(API_ENDPOINTS.PDF.LIST_BY_SESSION(sessionId));
  },

  async downloadPDF(pdfId: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.PDF.DOWNLOAD(pdfId)}`, withCookieCredentials({
      method: 'GET',
    }));

    if (!response.ok) {
      throw new Error('Failed to download PDF');
    }

    return response.blob();
  },

  async extractPetitionByCaseNumber(
    caseNumber: string,
    sessionId: string
  ): Promise<ApiResponse<ExtractPetitionResponse>> {
    try {
      const formData = new FormData();
      formData.append('case_number', caseNumber);
      formData.append('session_id', sessionId);

      const response = await fetch(`${API_BASE_URL}/api/extract-petition`, withCookieCredentials({
        method: 'POST',
        body: formData,
      }));

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));

        if (errorData.detail && Array.isArray(errorData.detail)) {
          const errorMessages = errorData.detail.map((err: { msg: string }) => err.msg).join(', ');
          return { error: `Validation error: ${errorMessages}` };
        }

        return {
          error: errorData.detail || errorData.message || 'Failed to extract petition',
          reason: response.status === 410 ? 'link_expired' : 'not_found',
        };
      }

      const data = await response.json();
      return { data };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : 'Failed to extract petition',
      };
    }
  },

  async downloadPetitionFromEmail(
    caseNumber: string,
    sessionId: string
  ): Promise<ApiResponse<ExtractPetitionResponse>> {
    try {
      const formData = new FormData();
      formData.append('case_number', caseNumber);
      formData.append('session_id', sessionId);

      const response = await fetch(`${API_BASE_URL}/api/extract-petition/from-email`, withCookieCredentials({
        method: 'POST',
        body: formData,
      }));

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));

        if (errorData.detail && Array.isArray(errorData.detail)) {
          const errorMessages = errorData.detail.map((err: { msg: string }) => err.msg).join(', ');
          return { error: `Validation error: ${errorMessages}` };
        }

        return {
          error: errorData.detail || errorData.message || 'Failed to download petition',
          reason: response.status === 410 ? 'link_expired' : 'not_found',
        };
      }

      const data = await response.json();
      return { data };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : 'Failed to download petition',
      };
    }
  },

  async downloadBankruptcyPetition(downloadUrl: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}${downloadUrl}`, withCookieCredentials({
      method: 'GET',
    }));

    if (!response.ok) {
      throw new Error('Failed to download bankruptcy petition PDF');
    }

    return response.blob();
  },

  async uploadOrderDelayMotion(
    file: File,
    sessionId: string,
    taskId: string,
  ): Promise<{ success: boolean; processed_count: number; errors?: string[] }> {
    try {
      const formData = new FormData();
      formData.append('files', file);
      formData.append('session_id', sessionId);
      formData.append('task_id', taskId);

      const response = await fetch(`${API_BASE_URL}/api/upload-order-delay-motion`, withCookieCredentials({
        method: 'POST',
        body: formData,
      }));

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        return {
          success: false,
          processed_count: 0,
          errors: [errorData.detail || 'Failed to upload Motion to Delay document'],
        };
      }

      const data = await response.json();
      return {
        success: data.success ?? true,
        processed_count: data.processed_count ?? 1,
        errors: data.errors,
      };
    } catch (error) {
      return {
        success: false,
        processed_count: 0,
        errors: [error instanceof Error ? error.message : 'Upload failed'],
      };
    }
  },

  async uploadLOESupportingDocs(
    files: File[],
    sessionId: string,
    taskId: string,
    storePermanently: boolean = false
  ): Promise<{ success: boolean; processed_count: number; errors?: string[] }> {
    try {
      const formData = new FormData();
      files.forEach((file) => formData.append('files', file));
      formData.append('session_id', sessionId);
      formData.append('task_id', taskId);
      formData.append('store_permanently', String(storePermanently));

      const response = await fetch(`${API_BASE_URL}/api/upload-loe-supporting-docs`, withCookieCredentials({
        method: 'POST',
        body: formData,
      }));

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        return {
          success: false,
          processed_count: 0,
          errors: [errorData.detail || 'Failed to upload supporting documents'],
        };
      }

      const data = await response.json();
      return {
        success: data.success ?? true,
        processed_count: data.processed_count ?? files.length,
        errors: data.errors,
      };
    } catch (error) {
      return {
        success: false,
        processed_count: 0,
        errors: [error instanceof Error ? error.message : 'Upload failed'],
      };
    }
  },
};
