/**
 * v2 case-chat REST + streaming client.
 *
 * - REST calls (get-or-create session, list messages, delete) go through
 *   `apiService` so they pick up the same JWT/Auth interceptor used by
 *   every other v2 endpoint.
 * - The streaming endpoint accepts a POST body so we can't use the native
 *   `EventSource` (which is GET-only). Instead we use `fetch` with
 *   `ReadableStream` and parse SSE frames manually. This is the same
 *   pattern used by claude.ai's web client.
 *
 * The stream handlers are intentionally typed as a discriminated bundle
 * rather than a single onEvent — the chat UI cares about each event
 * shape individually (thinking deltas pipe to one slot, content deltas
 * to another, tool cards spawn on tool_use_start, etc.).
 */

import { API_BASE_URL, API_ENDPOINTS } from '@/constants';
import { apiService } from '@/services/api';
import { withCookieCredentials } from '@/features/auth/auth.requests';
import type { ApiResponse } from '@/types';

// ─── Wire types (mirror BE schemas/dataclasses) ───────────────────────

export interface CaseSession {
  id: string;
  case_id: string;
  user_id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ToolCallSummary {
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface CaseChatMessageRow {
  id: string;
  case_session_id: string;
  sequence_number: number;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  thinking: string | null;
  tool_calls: ToolCallSummary[] | null;
  tool_call_id: string | null;
  created_at: string | null;
}

export interface MessagesPage {
  messages: CaseChatMessageRow[];
  has_more: boolean;
}

/**
 * Combined session-resolve + first-page-of-transcript shape returned by
 * `POST /chat/sessions/get-or-create`. The BE bundles the transcript
 * into the same response so the FE doesn't have to follow up with a
 * separate `GET /messages` call on every case open.
 */
export interface SessionWithHistory {
  session: CaseSession;
  messages: CaseChatMessageRow[];
  has_more: boolean;
}

// ─── SSE event types (mirror src/core/agents/llm/chat/events.py) ─────

export type ChatStreamEvent =
  | { event: 'thinking_delta'; delta: string }
  | { event: 'content_delta'; delta: string }
  | { event: 'tool_use_start'; tool_call_id: string; tool_name: string }
  | { event: 'tool_use_input_delta'; tool_call_id: string; delta: string }
  | {
      event: 'tool_result';
      tool_call_id: string;
      tool_name: string;
      result: unknown;
    }
  | { event: 'message_complete'; message_id: string; sequence_number: number }
  | { event: 'error'; message: string };

export interface StreamHandlers {
  onThinkingDelta?: (delta: string) => void;
  onContentDelta?: (delta: string) => void;
  onToolUseStart?: (toolCallId: string, toolName: string) => void;
  onToolUseInputDelta?: (toolCallId: string, delta: string) => void;
  onToolResult?: (toolCallId: string, toolName: string, result: unknown) => void;
  onMessageComplete?: (messageId: string, sequenceNumber: number) => void;
  onError?: (message: string) => void;
}

export interface StreamHandle {
  /** Abort the underlying fetch and stop further handler dispatches. */
  abort: () => void;
  /** Resolves when the stream finishes (success, error, or abort). */
  done: Promise<void>;
}

// ─── REST ────────────────────────────────────────────────────────────

export const getOrCreateCaseSession = (
  caseId: string,
): Promise<ApiResponse<SessionWithHistory>> =>
  apiService.post<SessionWithHistory>(API_ENDPOINTS.CHAT_V2.SESSION_GET_OR_CREATE, {
    case_id: caseId,
  });

export const getCaseSessionMessages = (
  sessionId: string,
  opts: { limit?: number; beforeSequence?: number } = {},
): Promise<ApiResponse<MessagesPage>> => {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  if (opts.beforeSequence !== undefined)
    params.set('before_sequence', String(opts.beforeSequence));
  const query = params.toString();
  const path = API_ENDPOINTS.CHAT_V2.SESSION_MESSAGES(sessionId);
  return apiService.get<MessagesPage>(query ? `${path}?${query}` : path);
};

export const deleteCaseSession = (
  sessionId: string,
): Promise<ApiResponse<{ deleted: boolean; session_id: string }>> =>
  apiService.delete(API_ENDPOINTS.CHAT_V2.SESSION_DELETE(sessionId));

// ─── Streaming POST ──────────────────────────────────────────────────

/**
 * Open a streaming POST to `/chat/sessions/{id}/stream`.
 *
 * Returns an abortable handle. Each parsed SSE frame is dispatched to the
 * matching `handlers.on...` callback. Caller is responsible for state
 * updates (e.g. updating Zustand). If the server emits an `error` frame
 * we surface it via `handlers.onError` and resolve `done` without
 * throwing — the FE should already be showing the partial transcript.
 */
export function streamCaseChatMessage(
  sessionId: string,
  userMessage: string,
  handlers: StreamHandlers,
): StreamHandle {
  const controller = new AbortController();
  const url = `${API_BASE_URL}${API_ENDPOINTS.CHAT_V2.SESSION_STREAM(sessionId)}`;

  const done = (async () => {
    try {
      const response = await fetch(
        url,
        withCookieCredentials({
          method: 'POST',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify({ user_message: userMessage }),
        }),
      );

      if (!response.ok) {
        const detail = await safeReadError(response);
        handlers.onError?.(detail);
        return;
      }
      if (!response.body) {
        handlers.onError?.('Stream had no response body.');
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      // Standard SSE framing: frames are separated by `\n\n`. Each frame
      // has zero or more lines like `event: <name>` or `data: <json>`.
      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        let separatorIndex = buffer.indexOf('\n\n');
        while (separatorIndex !== -1) {
          const rawFrame = buffer.slice(0, separatorIndex);
          buffer = buffer.slice(separatorIndex + 2);
          dispatchFrame(rawFrame, handlers);
          separatorIndex = buffer.indexOf('\n\n');
        }
      }
      if (buffer.trim()) {
        dispatchFrame(buffer, handlers);
      }
    } catch (err: unknown) {
      const name =
        typeof err === 'object' && err !== null && 'name' in err
          ? (err as { name?: string }).name
          : undefined;
      if (name === 'AbortError') return; // user-initiated stop
      const message = err instanceof Error ? err.message : String(err);
      handlers.onError?.(`Stream failed: ${message}`);
    }
  })();

  return {
    abort: () => controller.abort(),
    done,
  };
}

async function safeReadError(response: Response): Promise<string> {
  try {
    const body = await response.text();
    if (!body) return `Stream request failed (HTTP ${response.status}).`;
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      if (typeof parsed.detail === 'string') return parsed.detail;
    } catch {
      // not JSON — fall through and return raw body.
    }
    return body.slice(0, 500);
  } catch {
    return `Stream request failed (HTTP ${response.status}).`;
  }
}

function dispatchFrame(rawFrame: string, handlers: StreamHandlers): void {
  let eventName: string | null = null;
  let dataPayload = '';
  for (const line of rawFrame.split('\n')) {
    if (line.startsWith(':')) continue; // comment / keepalive
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      // Multi-line data frames concatenate with `\n` per the SSE spec.
      dataPayload += (dataPayload ? '\n' : '') + line.slice(5).trim();
    }
  }
  if (!eventName) return;
  let parsed: Record<string, unknown> = {};
  if (dataPayload) {
    try {
      parsed = JSON.parse(dataPayload) as Record<string, unknown>;
    } catch (err) {
      console.warn('[caseChat] failed to parse SSE data', err, dataPayload);
      return;
    }
  }
  const event: ChatStreamEvent = { event: eventName, ...parsed } as ChatStreamEvent;
  switch (event.event) {
    case 'thinking_delta':
      handlers.onThinkingDelta?.(event.delta);
      break;
    case 'content_delta':
      handlers.onContentDelta?.(event.delta);
      break;
    case 'tool_use_start':
      handlers.onToolUseStart?.(event.tool_call_id, event.tool_name);
      break;
    case 'tool_use_input_delta':
      handlers.onToolUseInputDelta?.(event.tool_call_id, event.delta);
      break;
    case 'tool_result':
      handlers.onToolResult?.(event.tool_call_id, event.tool_name, event.result);
      break;
    case 'message_complete':
      handlers.onMessageComplete?.(event.message_id, event.sequence_number);
      break;
    case 'error':
      handlers.onError?.(event.message);
      break;
    default:
      console.warn('[caseChat] unknown SSE event', event);
  }
}
