import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios';
import { API_BASE_URL, API_ENDPOINTS } from '@/constants';
import type { ApiResponse } from '@/types';
import { getCsrfToken, isMutationMethod } from '@/features/auth/auth.requests';

type RetriableRequestConfig = AxiosRequestConfig & {
  _retry?: boolean;
};

class ApiService {
  private api: AxiosInstance;
  private refreshPromise: Promise<void> | null = null;

  constructor() {
    this.api = axios.create({
      baseURL: API_BASE_URL,
      timeout: 300000,
      withCredentials: true,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors(): void {
    // Request interceptor
    this.api.interceptors.request.use(
      (config) => {
        const csrfToken = getCsrfToken();
        if (csrfToken && isMutationMethod(config.method)) {
          config.headers.set('X-CSRF-Token', csrfToken);
        }
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // Response interceptor
    this.api.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          const originalRequest = error.config as RetriableRequestConfig | undefined;
          const requestUrl = originalRequest?.url || '';
          const currentPath = window.location.pathname;
          const isAuthPage =
            currentPath === '/login' ||
            currentPath === '/register' ||
            currentPath === '/verify-email' ||
            currentPath === '/accept-invite' ||
            currentPath === '/user-approval';
          const isRefreshRequest = requestUrl.includes(API_ENDPOINTS.AUTH.REFRESH);
          const isLoginRequest = requestUrl.includes(API_ENDPOINTS.AUTH.LOGIN);
          const isRegisterRequest = requestUrl.includes(API_ENDPOINTS.AUTH.REGISTER);

          if (
            !isAuthPage &&
            originalRequest &&
            !originalRequest._retry &&
            !isRefreshRequest &&
            !isLoginRequest &&
            !isRegisterRequest
          ) {
            originalRequest._retry = true;

            try {
              await this.refreshSession();
              return this.api.request(originalRequest);
            } catch {
              // Fall through to frontend session cleanup and redirect.
            }
          }

          // Only redirect to login if we're not already on auth pages
          if (!isAuthPage) {
            window.location.href = '/login';
          }
          // If we're on auth pages, let the error propagate to be handled by the form
        }
        return Promise.reject(error);
      }
    );
  }

  private async refreshSession(): Promise<void> {
    if (!this.refreshPromise) {
      this.refreshPromise = axios
        .post(`${API_BASE_URL}${API_ENDPOINTS.AUTH.REFRESH}`, undefined, {
          withCredentials: true,
        })
        .then(() => undefined)
        .finally(() => {
          this.refreshPromise = null;
        });
    }

    return this.refreshPromise;
  }

  async get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    try {
      const response: AxiosResponse<T> = await this.api.get(url, config);
      return { data: response.data };
    } catch (error) {
      return this.handleError(error) as ApiResponse<T>;
    }
  }

  async post<T = unknown>(
    url: string,
    data?: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    try {
      const response: AxiosResponse<T> = await this.api.post(url, data, config);
      return { data: response.data };
    } catch (error) {
      return this.handleError(error) as ApiResponse<T>;
    }
  }

  async put<T = unknown>(
    url: string,
    data?: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    try {
      const response: AxiosResponse<T> = await this.api.put(url, data, config);
      return { data: response.data };
    } catch (error) {
      return this.handleError(error) as ApiResponse<T>;
    }
  }

  async patch<T = unknown>(
    url: string,
    data?: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    try {
      const response: AxiosResponse<T> = await this.api.patch(url, data, config);
      return { data: response.data };
    } catch (error) {
      return this.handleError(error) as ApiResponse<T>;
    }
  }

  async delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    try {
      const response: AxiosResponse<T> = await this.api.delete(url, config);
      return { data: response.data };
    } catch (error) {
      return this.handleError(error) as ApiResponse<T>;
    }
  }

  async uploadFile<T = unknown>(
    url: string,
    file: File,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response: AxiosResponse<T> = await this.api.post(url, formData, {
        ...config,
        headers: {
          'Content-Type': 'multipart/form-data',
          ...config?.headers,
        },
      });
      return { data: response.data };
    } catch (error) {
      return this.handleError(error) as ApiResponse<T>;
    }
  }

  private handleError(error: unknown): ApiResponse {
    if (axios.isAxiosError(error)) {
      const responseData = error.response?.data;

      // Handle validation errors (FastAPI format)
      if (responseData?.detail && Array.isArray(responseData.detail)) {
        // Extract the first validation error message
        const firstError = responseData.detail[0];
        if (firstError) {
          // Try to get the most user-friendly message
          const message =
            firstError.ctx?.reason || // Use the reason from context if available
            firstError.msg || // Otherwise use the full message
            'Validation error';
          return { error: message };
        }
      }

      // Handle string detail messages
      if (typeof responseData?.detail === 'string') {
        return { error: responseData.detail };
      }

      // Handle structured FastAPI HTTPException detail objects, e.g.
      //   { detail: { validation_errors: ["...", "..."] } }
      // which is the shape used by /api/v2/core/template/composer/compose-agent-config.
      if (responseData?.detail && typeof responseData.detail === 'object') {
        const detailObj = responseData.detail as Record<string, unknown>;
        if (Array.isArray(detailObj.validation_errors) && detailObj.validation_errors.length > 0) {
          const validationErrors = detailObj.validation_errors as string[];
          return {
            error: validationErrors.join(' · '),
            validationErrors,
          };
        }
        // DELETE /template/{id} returns 409 with `referencing_parents`
        // when the doomed template is referenced by other parent
        // templates' bundle_companions. Surface that payload so the
        // caller can offer force-delete.
        if (Array.isArray(detailObj.referencing_parents)) {
          return {
            error: typeof detailObj.message === 'string'
              ? detailObj.message
              : 'Template is referenced by other templates',
            conflictParents: detailObj.referencing_parents as ApiResponse['conflictParents'],
          };
        }
        const code = typeof detailObj.code === 'string' ? detailObj.code : undefined;
        if (typeof detailObj.message === 'string') {
          return { error: detailObj.message, code };
        }
        if (code) {
          return { error: code, code };
        }
      }

      // Handle other error formats
      const message = responseData?.message || error.message || 'An error occurred';
      return { error: message };
    }
    return { error: 'An unexpected error occurred' };
  }
}

export const apiService = new ApiService();
export default apiService;
