import { apiService } from '@/services/api';
import { API_BASE_URL, API_ENDPOINTS } from '@/constants';
import { withCookieCredentials } from '@/features/auth/auth.requests';
import type {
  DashboardAnalyticsFilters,
  DashboardInsightExplainResponse,
  DashboardInsightsChatHistoryResponse,
  DashboardInsightsChatResponse,
  DashboardInsightsChatStreamEvent,
  DashboardInsightsResponse,
} from '../types';
import { buildQueryParams, getOrThrowData } from './shared.api';

type RequestOptions = {
  signal?: AbortSignal;
};

export const fetchDashboardInsights = async (
  filters: DashboardAnalyticsFilters,
  options: RequestOptions = {}
): Promise<DashboardInsightsResponse> => {
  const response = await apiService.get<DashboardInsightsResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.INSIGHTS,
    {
      params: buildQueryParams(filters),
      signal: options.signal,
    }
  );

  return getOrThrowData(response, 'Dashboard insights response was empty');
};

export const fetchDashboardInsightExplanation = async (
  action: string,
  filters: DashboardAnalyticsFilters
): Promise<DashboardInsightExplainResponse> => {
  const response = await apiService.get<DashboardInsightExplainResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.INSIGHTS_EXPLAIN,
    {
      params: {
        action,
        Action: action,
        ...buildQueryParams(filters),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard insight explanation response was empty');
};

export const fetchDashboardInsightsChat = async (
  message: string,
  options: RequestOptions = {}
): Promise<DashboardInsightsChatResponse> => {
  const response = await apiService.post<DashboardInsightsChatResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.INSIGHTS_CHAT,
    { message },
    { signal: options.signal }
  );

  return getOrThrowData(response, 'Dashboard insights chat response was empty');
};

export const fetchDashboardInsightsChatHistory = async (
  options: RequestOptions = {}
): Promise<DashboardInsightsChatHistoryResponse> => {
  const response = await apiService.get<DashboardInsightsChatHistoryResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.INSIGHTS_CHAT,
    {
      signal: options.signal,
    }
  );

  return getOrThrowData(response, 'Dashboard insights chat history response was empty');
};

export const clearDashboardInsightsChat = async (): Promise<void> => {
  const response = await apiService.delete<{ cleared: boolean }>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.INSIGHTS_CHAT
  );

  if (response.error) {
    throw new Error(response.error);
  }
};

type StreamChunkHandler = (fullText: string, chunk: string) => void;
type StreamToolStatusHandler = (name: string, status: 'running' | 'done') => void;
type StreamOptions = {
  signal?: AbortSignal;
  onTextChunk?: StreamChunkHandler;
  onToolStatus?: StreamToolStatusHandler;
};

const parseStreamError = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail || payload.message || `Chat stream failed (${response.status})`;
  } catch {
    return `Chat stream failed (${response.status})`;
  }
};

export const streamDashboardInsightsChat = async (
  message: string,
  options: StreamOptions = {}
): Promise<DashboardInsightsChatResponse> => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  const response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.DASHBOARD.ANALYTICS.INSIGHTS_CHAT_STREAM}`, withCookieCredentials({
    method: 'POST',
    headers,
    body: JSON.stringify({ message }),
    signal: options.signal,
  }));

  if (!response.ok) {
    throw new Error(await parseStreamError(response));
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Chat stream response body was empty');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let reply = '';
  let pendingChunk = '';
  let flushTimeout: number | null = null;

  const flushPendingChunks = () => {
    if (!pendingChunk) {
      flushTimeout = null;
      return;
    }
    const chunk = pendingChunk;
    pendingChunk = '';
    flushTimeout = null;
    options.onTextChunk?.(reply, chunk);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) {
        continue;
      }

      const raw = line.slice(6).trim();
      if (!raw) {
        continue;
      }

      let event: DashboardInsightsChatStreamEvent;
      try {
        event = JSON.parse(raw) as DashboardInsightsChatStreamEvent;
      } catch {
        continue;
      }

      if (event.type === 'text_chunk') {
        const chunk = event.chunk || '';
        reply += chunk;
        pendingChunk += chunk;
        if (flushTimeout === null) {
          flushTimeout = window.setTimeout(flushPendingChunks, 16);
        }
      } else if (event.type === 'tool_status') {
        options.onToolStatus?.(event.name, event.status);
      } else if (event.type === 'error') {
        if (flushTimeout !== null) {
          window.clearTimeout(flushTimeout);
          flushTimeout = null;
        }
        if (pendingChunk) {
          flushPendingChunks();
        }
        throw new Error(event.message || 'Chat stream failed');
      }
    }
  }

  if (flushTimeout !== null) {
    window.clearTimeout(flushTimeout);
    flushTimeout = null;
  }
  if (pendingChunk) {
    flushPendingChunks();
  }

  return { reply };
};
