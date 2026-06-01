import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/caseChat.service', () => ({
  getOrCreateCaseSession: vi.fn(),
  getCaseSessionMessages: vi.fn(),
  deleteCaseSession: vi.fn(),
  streamCaseChatMessage: vi.fn(),
}));

import {
  deleteCaseSession,
  getCaseSessionMessages,
  getOrCreateCaseSession,
  streamCaseChatMessage,
  type CaseSession,
  type StreamHandlers,
} from '@/services/caseChat.service';
import { useCaseChatStore } from '@/stores/useCaseChatStore';
import { useStudioStore } from '@/stores/useStudioStore';
import { useWorkspaceSplitStore } from '@/stores/useWorkspaceSplitStore';

const mocks = {
  getOrCreate: getOrCreateCaseSession as unknown as ReturnType<typeof vi.fn>,
  getMessages: getCaseSessionMessages as unknown as ReturnType<typeof vi.fn>,
  delete: deleteCaseSession as unknown as ReturnType<typeof vi.fn>,
  stream: streamCaseChatMessage as unknown as ReturnType<typeof vi.fn>,
};

const CASE_ID = '26_10700';

const fakeSession: CaseSession = {
  id: 'sess-1',
  case_id: CASE_ID,
  user_id: 'user-1',
  title: 'Chat',
  created_at: '2026-05-15T10:00:00Z',
  updated_at: '2026-05-15T10:00:00Z',
};

function seedSlice(caseId: string, overrides: Partial<{
  session: CaseSession | null;
  messages: never[];
  isLoadingHistory: boolean;
  isStreaming: boolean;
  error: string | null;
  hasUnread: boolean;
}> = {}) {
  useCaseChatStore.setState((state) => ({
    byCase: {
      ...state.byCase,
      [caseId]: {
        session: null,
        messages: [],
        isLoadingHistory: false,
        isStreaming: false,
        error: null,
        hasUnread: false,
        ...overrides,
      },
    },
  }));
}

function resetStore() {
  useCaseChatStore.setState({ byCase: {} });
}

beforeEach(() => {
  for (const fn of Object.values(mocks)) fn.mockReset();
  // Post-stream reconcile calls getCaseSessionMessages — give every test
  // a benign default. Tests that care about hydration override this.
  mocks.getMessages.mockResolvedValue({ data: { messages: [], has_more: false } });
  resetStore();
});

afterEach(() => {
  resetStore();
});

describe('loadOrCreateSession', () => {
  it('populates session + messages from the single combined response', async () => {
    // BE now returns {session, messages, has_more} in one round trip;
    // the store no longer makes a follow-up GET /messages call.
    mocks.getOrCreate.mockResolvedValue({
      data: {
        session: fakeSession,
        messages: [
          {
            id: 'm1',
            case_session_id: 'sess-1',
            sequence_number: 1,
            role: 'user',
            content: 'hello',
            thinking: null,
            tool_calls: null,
            tool_call_id: null,
            created_at: null,
          },
          {
            id: 'm2',
            case_session_id: 'sess-1',
            sequence_number: 2,
            role: 'assistant',
            content: 'hi back',
            thinking: 'thinking trace',
            tool_calls: [
              { id: 'c1', name: 'case_vector_search', input: { query: 'x' } },
            ],
            tool_call_id: null,
            created_at: null,
          },
          {
            id: 'm3',
            case_session_id: 'sess-1',
            sequence_number: 3,
            role: 'tool',
            content: '{"total":2}',
            thinking: null,
            tool_calls: null,
            tool_call_id: 'c1',
            created_at: null,
          },
        ],
        has_more: false,
      },
    });

    await useCaseChatStore.getState().loadOrCreateSession(CASE_ID);
    const slice = useCaseChatStore.getState().byCase[CASE_ID]!;

    expect(slice.session?.id).toBe('sess-1');
    expect(slice.messages).toHaveLength(2);
    expect(slice.messages[0]!.role).toBe('user');
    const assistant = slice.messages[1]!;
    expect(assistant.role).toBe('assistant');
    if (assistant.role !== 'assistant') throw new Error('unreachable');
    expect(assistant.thinking).toBe('thinking trace');
    expect(assistant.toolCalls).toHaveLength(1);
    expect(assistant.toolCalls[0]!.status).toBe('done');
    expect(assistant.toolCalls[0]!.result).toEqual({ total: 2 });
    // No follow-up GET /messages should have fired.
    expect(mocks.getMessages).not.toHaveBeenCalled();
  });

  it('surfaces an error when session creation fails', async () => {
    mocks.getOrCreate.mockResolvedValue({ error: 'BE down' });
    await useCaseChatStore.getState().loadOrCreateSession(CASE_ID);
    expect(useCaseChatStore.getState().byCase[CASE_ID]?.error).toBe('BE down');
  });

  it('is a no-op when called twice for the same case (idempotent)', async () => {
    mocks.getOrCreate.mockResolvedValue({
      data: { session: fakeSession, messages: [], has_more: false },
    });
    await useCaseChatStore.getState().loadOrCreateSession(CASE_ID);
    mocks.getOrCreate.mockClear();
    await useCaseChatStore.getState().loadOrCreateSession(CASE_ID);
    expect(mocks.getOrCreate).not.toHaveBeenCalled();
  });

  it('keeps each case isolated — concurrent loads do not clobber each other', async () => {
    const otherSession: CaseSession = { ...fakeSession, id: 'sess-2', case_id: '26_20000' };
    mocks.getOrCreate.mockImplementation(async (caseId: string) => ({
      data: {
        session: caseId === CASE_ID ? fakeSession : otherSession,
        messages: [],
        has_more: false,
      },
    }));

    await Promise.all([
      useCaseChatStore.getState().loadOrCreateSession(CASE_ID),
      useCaseChatStore.getState().loadOrCreateSession('26_20000'),
    ]);

    const { byCase } = useCaseChatStore.getState();
    expect(byCase[CASE_ID]?.session?.id).toBe('sess-1');
    expect(byCase['26_20000']?.session?.id).toBe('sess-2');
  });
});

describe('sendMessage', () => {
  it('streams events into store state and reconciles from DB on completion', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    // Mock the post-stream reconcile fetch — a tool-using turn persists
    // as: user → assistant(tool_call) → tool → assistant(text). The
    // reconcile replaces the optimistic single-bubble state with this.
    mocks.getMessages.mockResolvedValue({
      data: {
        messages: [
          {
            id: 'm1', case_session_id: 'sess-1', sequence_number: 1,
            role: 'user', content: 'how many creditors?',
            thinking: null, tool_calls: null, tool_call_id: null, created_at: null,
          },
          {
            id: 'm2', case_session_id: 'sess-1', sequence_number: 2,
            role: 'assistant', content: '', thinking: 'reasoning…',
            tool_calls: [{ id: 'c1', name: 'case_vector_search', input: { query: 'creditors' } }],
            tool_call_id: null, created_at: null,
          },
          {
            id: 'm3', case_session_id: 'sess-1', sequence_number: 3,
            role: 'tool', content: '{"total":12}',
            thinking: null, tool_calls: null, tool_call_id: 'c1', created_at: null,
          },
          {
            id: 'm4', case_session_id: 'sess-1', sequence_number: 4,
            role: 'assistant', content: 'There are 12 unsecured creditors.',
            thinking: null, tool_calls: null, tool_call_id: null, created_at: null,
          },
        ],
        has_more: false,
      },
    });

    let captured: StreamHandlers | null = null;
    let resolveDone: () => void = () => {};
    const donePromise = new Promise<void>((res) => {
      resolveDone = res;
    });
    mocks.stream.mockImplementation((_sid: string, _msg: string, handlers: StreamHandlers) => {
      captured = handlers;
      return { abort: vi.fn(), done: donePromise };
    });

    const sendPromise = useCaseChatStore.getState().sendMessage(CASE_ID, 'how many creditors?');
    await Promise.resolve();
    // Mid-stream the FE still shows ONE optimistic assistant bubble.
    let slice = useCaseChatStore.getState().byCase[CASE_ID]!;
    expect(slice.messages).toHaveLength(2);
    expect(slice.messages[0]!.role).toBe('user');
    expect(slice.messages[1]!.role).toBe('assistant');
    expect(slice.isStreaming).toBe(true);

    expect(captured).not.toBeNull();
    const handlers = captured!;
    handlers.onThinkingDelta?.('reasoning…');
    handlers.onContentDelta?.('There are 12 unsecured creditors.');
    handlers.onMessageComplete?.('m4', 4);

    resolveDone();
    await sendPromise;

    // Post-stream: reconcile replaced the optimistic state with the
    // canonical persisted shape. Tool rows fold into their prior
    // assistant's toolCalls (no separate bubble), so 4 persisted rows
    // (user, assistant-with-tool-call, tool, assistant-text) hydrate
    // into 3 visible messages.
    slice = useCaseChatStore.getState().byCase[CASE_ID]!;
    expect(slice.messages).toHaveLength(3);
    expect(slice.messages.map((m) => m.role)).toEqual(['user', 'assistant', 'assistant']);
    const toolCallBubble = slice.messages[1]!;
    if (toolCallBubble.role !== 'assistant') throw new Error('unreachable');
    expect(toolCallBubble.toolCalls).toHaveLength(1);
    expect(toolCallBubble.toolCalls[0]!.result).toEqual({ total: 12 });
    expect(toolCallBubble.toolCalls[0]!.status).toBe('done');
    const finalBubble = slice.messages[2]!;
    if (finalBubble.role !== 'assistant') throw new Error('unreachable');
    expect(finalBubble.content).toBe('There are 12 unsecured creditors.');
    expect(slice.isStreaming).toBe(false);
  });

  it('does nothing when content is empty', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    await useCaseChatStore.getState().sendMessage(CASE_ID, '   ');
    expect(mocks.stream).not.toHaveBeenCalled();
    expect(useCaseChatStore.getState().byCase[CASE_ID]?.messages).toHaveLength(0);
  });

  it('surfaces stream-level errors on the assistant message', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    // On error, the user's message was persisted before streaming began
    // but no assistant rows landed. Reconcile finds only the user row.
    mocks.getMessages.mockResolvedValue({
      data: {
        messages: [
          {
            id: 'u1', case_session_id: 'sess-1', sequence_number: 1,
            role: 'user', content: 'x',
            thinking: null, tool_calls: null, tool_call_id: null, created_at: null,
          },
        ],
        has_more: false,
      },
    });

    let captured: StreamHandlers | null = null;
    let resolveDone: () => void = () => {};
    const donePromise = new Promise<void>((res) => {
      resolveDone = res;
    });
    mocks.stream.mockImplementation((_sid: string, _msg: string, handlers: StreamHandlers) => {
      captured = handlers;
      return { abort: vi.fn(), done: donePromise };
    });
    const send = useCaseChatStore.getState().sendMessage(CASE_ID, 'x');
    await Promise.resolve();
    // While streaming, the optimistic assistant bubble carries the error.
    captured!.onError?.('Agent died');
    const midStream = useCaseChatStore.getState().byCase[CASE_ID]!;
    const optimistic = midStream.messages.find((m) => m.role === 'assistant');
    expect(optimistic).toBeDefined();
    if (optimistic && optimistic.role === 'assistant') {
      expect(optimistic.error).toBe('Agent died');
      expect(optimistic.isStreaming).toBe(false);
    }
    resolveDone();
    await send;
    // After reconcile the optimistic bubble is gone; user row remains.
    expect(useCaseChatStore.getState().byCase[CASE_ID]?.isStreaming).toBe(false);
  });

  it('streams for two cases concurrently without cross-talk', async () => {
    const otherSession: CaseSession = { ...fakeSession, id: 'sess-2', case_id: '26_20000' };
    seedSlice(CASE_ID, { session: fakeSession });
    seedSlice('26_20000', { session: otherSession });

    const handlersByCase = new Map<string, StreamHandlers>();
    const resolversByCase = new Map<string, () => void>();
    mocks.stream.mockImplementation((sid: string, _msg: string, handlers: StreamHandlers) => {
      handlersByCase.set(sid, handlers);
      let resolve = () => {};
      const done = new Promise<void>((r) => {
        resolve = r;
      });
      resolversByCase.set(sid, resolve);
      return { abort: vi.fn(), done };
    });

    const sendA = useCaseChatStore.getState().sendMessage(CASE_ID, 'a');
    const sendB = useCaseChatStore.getState().sendMessage('26_20000', 'b');
    await Promise.resolve();

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.isStreaming).toBe(true);
    expect(useCaseChatStore.getState().byCase['26_20000']?.isStreaming).toBe(true);

    handlersByCase.get('sess-1')!.onContentDelta?.('a-reply');
    handlersByCase.get('sess-2')!.onContentDelta?.('b-reply');

    const sliceA = useCaseChatStore.getState().byCase[CASE_ID]!;
    const sliceB = useCaseChatStore.getState().byCase['26_20000']!;
    const assistantA = sliceA.messages.find((m) => m.role === 'assistant');
    const assistantB = sliceB.messages.find((m) => m.role === 'assistant');
    if (assistantA?.role === 'assistant') expect(assistantA.content).toBe('a-reply');
    if (assistantB?.role === 'assistant') expect(assistantB.content).toBe('b-reply');

    resolversByCase.get('sess-1')!();
    resolversByCase.get('sess-2')!();
    await Promise.all([sendA, sendB]);
  });
});

describe('cancelStream + reset + deleteSessionAndReset', () => {
  it('cancelStream calls handle.abort and clears isStreaming for that case only', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    const abort = vi.fn();
    let resolveDone: () => void = () => {};
    const donePromise = new Promise<void>((res) => {
      resolveDone = res;
    });
    mocks.stream.mockReturnValue({ abort, done: donePromise });
    const send = useCaseChatStore.getState().sendMessage(CASE_ID, 'hi');
    await Promise.resolve();
    useCaseChatStore.getState().cancelStream(CASE_ID);
    expect(abort).toHaveBeenCalled();
    expect(useCaseChatStore.getState().byCase[CASE_ID]?.isStreaming).toBe(false);
    resolveDone();
    await send;
  });

  it('resetCase removes only the targeted case slice', () => {
    seedSlice(CASE_ID, { session: fakeSession, error: 'something' });
    seedSlice('26_20000', { session: { ...fakeSession, id: 'sess-2', case_id: '26_20000' } });
    useCaseChatStore.getState().resetCase(CASE_ID);
    expect(useCaseChatStore.getState().byCase[CASE_ID]).toBeUndefined();
    expect(useCaseChatStore.getState().byCase['26_20000']).toBeDefined();
  });

  it('resetAll wipes every slice', () => {
    seedSlice(CASE_ID, { session: fakeSession });
    seedSlice('26_20000', { session: { ...fakeSession, id: 'sess-2', case_id: '26_20000' } });
    useCaseChatStore.getState().resetAll();
    expect(useCaseChatStore.getState().byCase).toEqual({});
  });

  it('deleteSessionAndReset calls the API and clears that case', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    mocks.delete.mockResolvedValue({ data: { deleted: true, session_id: 'sess-1' } });
    await useCaseChatStore.getState().deleteSessionAndReset(CASE_ID);
    expect(mocks.delete).toHaveBeenCalledWith('sess-1');
    expect(useCaseChatStore.getState().byCase[CASE_ID]).toBeUndefined();
  });
});

describe('hasUnread', () => {
  /**
   * Drive sendMessage through its happy path and resolve the stream
   * with a clean onMessageComplete (no error, no cancel). Returns the
   * sendPromise so the caller can await reconciliation.
   */
  async function runSuccessfulStream(caseId: string): Promise<void> {
    let captured: StreamHandlers | null = null;
    let resolveDone: () => void = () => {};
    const donePromise = new Promise<void>((res) => {
      resolveDone = res;
    });
    mocks.stream.mockImplementationOnce(
      (_sid: string, _msg: string, handlers: StreamHandlers) => {
        captured = handlers;
        return { abort: vi.fn(), done: donePromise };
      },
    );
    const send = useCaseChatStore.getState().sendMessage(caseId, 'q');
    await Promise.resolve();
    captured!.onContentDelta?.('answer');
    captured!.onMessageComplete?.('m-final', 99);
    resolveDone();
    await send;
  }

  beforeEach(() => {
    // Reset the cross-store state that drives the unread guard.
    useStudioStore.setState({ selectedCaseId: null });
    useWorkspaceSplitStore.setState({
      secondaryCaseId: null,
      focusedPane: 'primary',
    });
  });

  it('flags hasUnread when a stream finalizes on an off-pane case', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useStudioStore.setState({ selectedCaseId: 'some-other-case' });

    await runSuccessfulStream(CASE_ID);

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(true);
  });

  it('does NOT flag hasUnread when the finalize lands on the primary pane', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useStudioStore.setState({ selectedCaseId: CASE_ID });

    await runSuccessfulStream(CASE_ID);

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);
  });

  it('does NOT flag hasUnread when the finalize lands on the secondary pane', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useStudioStore.setState({ selectedCaseId: 'primary-case' });
    useWorkspaceSplitStore.setState({
      secondaryCaseId: CASE_ID,
      focusedPane: 'secondary',
    });

    await runSuccessfulStream(CASE_ID);

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);
  });

  it('does NOT flag hasUnread when the user cancels the stream', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useStudioStore.setState({ selectedCaseId: 'some-other-case' });

    let resolveDone: () => void = () => {};
    const donePromise = new Promise<void>((res) => {
      resolveDone = res;
    });
    mocks.stream.mockImplementationOnce(() => ({
      abort: vi.fn(),
      done: donePromise,
    }));
    const send = useCaseChatStore.getState().sendMessage(CASE_ID, 'q');
    await Promise.resolve();
    useCaseChatStore.getState().cancelStream(CASE_ID);
    resolveDone();
    await send;

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);
  });

  it('does NOT flag hasUnread when the stream emits an error', async () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useStudioStore.setState({ selectedCaseId: 'some-other-case' });

    let captured: StreamHandlers | null = null;
    let resolveDone: () => void = () => {};
    const donePromise = new Promise<void>((res) => {
      resolveDone = res;
    });
    mocks.stream.mockImplementationOnce(
      (_sid: string, _msg: string, handlers: StreamHandlers) => {
        captured = handlers;
        return { abort: vi.fn(), done: donePromise };
      },
    );
    const send = useCaseChatStore.getState().sendMessage(CASE_ID, 'q');
    await Promise.resolve();
    captured!.onError?.('agent crashed');
    resolveDone();
    await send;

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);
  });

  it('markCaseRead clears the flag and is a no-op when already clear', () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useCaseChatStore.setState((state) => ({
      byCase: {
        ...state.byCase,
        [CASE_ID]: { ...state.byCase[CASE_ID]!, hasUnread: true },
      },
    }));

    useCaseChatStore.getState().markCaseRead(CASE_ID);
    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);

    // Calling again is a no-op (does not throw, does not flip state).
    useCaseChatStore.getState().markCaseRead(CASE_ID);
    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);
  });

  it('selecting the case in the primary pane clears hasUnread (subscription)', () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useCaseChatStore.setState((state) => ({
      byCase: {
        ...state.byCase,
        [CASE_ID]: { ...state.byCase[CASE_ID]!, hasUnread: true },
      },
    }));

    useStudioStore.setState({ selectedCaseId: CASE_ID });

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);
  });

  it('opening the case in the secondary pane clears hasUnread (subscription)', () => {
    seedSlice(CASE_ID, { session: fakeSession });
    useCaseChatStore.setState((state) => ({
      byCase: {
        ...state.byCase,
        [CASE_ID]: { ...state.byCase[CASE_ID]!, hasUnread: true },
      },
    }));

    useWorkspaceSplitStore.setState({ secondaryCaseId: CASE_ID });

    expect(useCaseChatStore.getState().byCase[CASE_ID]?.hasUnread).toBe(false);
  });
});
