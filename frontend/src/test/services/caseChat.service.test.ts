import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiService = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  default: apiService,
  apiService,
}));

vi.mock('@/utils', () => ({
  storage: {
    get: vi.fn(() => 'fake-jwt'),
  },
}));

import {
  deleteCaseSession,
  getCaseSessionMessages,
  getOrCreateCaseSession,
  streamCaseChatMessage,
} from '@/services/caseChat.service';
import { API_ENDPOINTS } from '@/constants';

const ok = <T>(data: T) => ({ data });

beforeEach(() => {
  for (const fn of Object.values(apiService)) fn.mockReset();
});

afterEach(() => {
  for (const fn of Object.values(apiService)) fn.mockReset();
});

describe('REST', () => {
  it('getOrCreateCaseSession POSTs to /chat/sessions/get-or-create with case_id', async () => {
    apiService.post.mockResolvedValue(ok({ id: 'sess-1' }));
    await getOrCreateCaseSession('26_10700');
    expect(apiService.post).toHaveBeenCalledWith(
      API_ENDPOINTS.CHAT_V2.SESSION_GET_OR_CREATE,
      { case_id: '26_10700' },
    );
  });

  it('getCaseSessionMessages threads limit + before_sequence as query params', async () => {
    apiService.get.mockResolvedValue(ok({ messages: [], has_more: false }));
    await getCaseSessionMessages('sess-1', { limit: 10, beforeSequence: 42 });
    const expectedPath = `${API_ENDPOINTS.CHAT_V2.SESSION_MESSAGES('sess-1')}?limit=10&before_sequence=42`;
    expect(apiService.get).toHaveBeenCalledWith(expectedPath);
  });

  it('getCaseSessionMessages omits query string when no opts provided', async () => {
    apiService.get.mockResolvedValue(ok({ messages: [], has_more: false }));
    await getCaseSessionMessages('sess-1');
    expect(apiService.get).toHaveBeenCalledWith(
      API_ENDPOINTS.CHAT_V2.SESSION_MESSAGES('sess-1'),
    );
  });

  it('deleteCaseSession DELETEs the session path', async () => {
    apiService.delete.mockResolvedValue(ok({ deleted: true, session_id: 'sess-1' }));
    await deleteCaseSession('sess-1');
    expect(apiService.delete).toHaveBeenCalledWith(
      API_ENDPOINTS.CHAT_V2.SESSION_DELETE('sess-1'),
    );
  });
});

describe('streamCaseChatMessage', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function mockStreamBody(frames: string[]): Response {
    const encoder = new TextEncoder();
    let i = 0;
    const stream = new ReadableStream({
      pull(controller) {
        if (i >= frames.length) {
          controller.close();
          return;
        }
        controller.enqueue(encoder.encode(frames[i]!));
        i += 1;
      },
    });
    return new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }

  it('parses SSE frames and dispatches typed handlers in order', async () => {
    const frames = [
      'event: thinking_delta\ndata: {"delta":"hmm"}\n\n',
      'event: tool_use_start\ndata: {"tool_call_id":"c1","tool_name":"case_vector_search"}\n\n',
      'event: tool_use_input_delta\ndata: {"tool_call_id":"c1","delta":"{\\"q"}\n\n',
      'event: tool_result\ndata: {"tool_call_id":"c1","tool_name":"case_vector_search","result":{"total":2}}\n\n',
      'event: content_delta\ndata: {"delta":"final "}\n\n',
      'event: content_delta\ndata: {"delta":"answer."}\n\n',
      'event: message_complete\ndata: {"message_id":"m1","sequence_number":7}\n\n',
    ];
    globalThis.fetch = vi.fn(async () => mockStreamBody(frames)) as typeof fetch;

    const events: string[] = [];
    const handlers = {
      onThinkingDelta: (d: string) => events.push(`think:${d}`),
      onContentDelta: (d: string) => events.push(`content:${d}`),
      onToolUseStart: (id: string, name: string) => events.push(`start:${id}:${name}`),
      onToolUseInputDelta: (id: string, d: string) => events.push(`input:${id}:${d}`),
      onToolResult: (id: string, name: string, result: unknown) =>
        events.push(`result:${id}:${name}:${JSON.stringify(result)}`),
      onMessageComplete: (id: string, seq: number) => events.push(`done:${id}:${seq}`),
      onError: (m: string) => events.push(`error:${m}`),
    };

    const handle = streamCaseChatMessage('sess-1', 'how many creditors?', handlers);
    await handle.done;

    expect(events).toEqual([
      'think:hmm',
      'start:c1:case_vector_search',
      'input:c1:{"q',
      'result:c1:case_vector_search:{"total":2}',
      'content:final ',
      'content:answer.',
      'done:m1:7',
    ]);
  });

  it('emits an onError handler on non-2xx response', async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: 'Session not found' }), {
          status: 404,
        }),
    ) as typeof fetch;

    const onError = vi.fn();
    await streamCaseChatMessage('sess-x', 'hello', { onError }).done;
    expect(onError).toHaveBeenCalledWith('Session not found');
  });

  it('uses cookie credentials and does not send Authorization header', async () => {
    const captured: RequestInit[] = [];
    globalThis.fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      captured.push(init ?? {});
      return mockStreamBody([]);
    }) as typeof fetch;

    await streamCaseChatMessage('sess-1', 'hi', {}).done;
    const init = captured[0];
    expect(init?.credentials).toBe('include');
    const headers = init?.headers as Headers;
    expect(headers.get('Authorization')).toBeNull();
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('handles frame split across multiple chunks', async () => {
    const frames = [
      'event: content_delta\ndata: {"delta":"',
      'hello world"}\n\n',
    ];
    globalThis.fetch = vi.fn(async () => mockStreamBody(frames)) as typeof fetch;

    const seen: string[] = [];
    await streamCaseChatMessage('sess-1', 'x', {
      onContentDelta: (d) => seen.push(d),
    }).done;
    expect(seen).toEqual(['hello world']);
  });
});
