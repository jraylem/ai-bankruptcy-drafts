/**
 * Zustand store for the v2 case-chat workspace.
 *
 * One canonical session per (user, case) — keyed by `case_id` so the
 * split-screen workspace can hold two cases' chat state concurrently
 * without one pane's stream cancelling or replacing the other's.
 *
 * Isolated from the v1 `useChatStore` (legacy) and the v2
 * `useTemplateDraftStore` (template drafts have their own SSE pipeline).
 */

import { create } from 'zustand';

import {
  deleteCaseSession,
  getCaseSessionMessages,
  getOrCreateCaseSession,
  streamCaseChatMessage,
  type CaseChatMessageRow,
  type CaseSession,
  type StreamHandle,
  type ToolCallSummary,
} from '@/services/caseChat.service';
import { useStudioStore } from '@/stores/useStudioStore';
import { useWorkspaceSplitStore } from '@/stores/useWorkspaceSplitStore';

// ─── UI-side message shapes ───────────────────────────────────────────

export interface ToolCallRender {
  id: string;
  name: string;
  input: Record<string, unknown>;
  status: 'streaming-input' | 'invoking' | 'done' | 'error';
  /**
   * Result payload from the BE (after tool execution). Null while the
   * tool call is still in-flight.
   */
  result: unknown | null;
}

interface BaseMessage {
  id: string;
  sequenceNumber: number;
  createdAt: string | null;
}

export interface UserChatMessage extends BaseMessage {
  role: 'user';
  content: string;
}

export interface AssistantChatMessage extends BaseMessage {
  role: 'assistant';
  thinking: string;
  content: string;
  toolCalls: ToolCallRender[];
  /** True while we're appending streamed deltas. False once finalized. */
  isStreaming: boolean;
  /** Set when the BE emitted an `error` frame for this turn. */
  error: string | null;
}

export type ChatMessage = UserChatMessage | AssistantChatMessage;

// ─── Per-case slice ───────────────────────────────────────────────────

export interface CaseChatSlice {
  session: CaseSession | null;
  messages: ChatMessage[];
  isLoadingHistory: boolean;
  isStreaming: boolean;
  error: string | null;
  /**
   * True after a chat turn finalizes successfully on a case the user
   * wasn't actively viewing in either workspace pane. Session-only —
   * cleared when the case is selected (primary or secondary pane) or
   * when the slice is reset. Never persisted.
   */
  hasUnread: boolean;
}

export const EMPTY_CASE_CHAT_SLICE: CaseChatSlice = Object.freeze({
  session: null,
  messages: [],
  isLoadingHistory: false,
  isStreaming: false,
  error: null,
  hasUnread: false,
});

// ─── Store shape ──────────────────────────────────────────────────────

interface CaseChatState {
  /** Per-case slices. Reads should fall back to EMPTY_CASE_CHAT_SLICE. */
  byCase: Record<string, CaseChatSlice>;

  /** Resolve or auto-create the canonical session for a case and load history. */
  loadOrCreateSession: (caseId: string) => Promise<void>;
  /** Drop a single case's client state (e.g. when closing the split pane). */
  resetCase: (caseId: string) => void;
  /** Hard reset — drop all client state. Used on logout. */
  resetAll: () => void;
  /** Send a user prompt and stream the assistant turn. */
  sendMessage: (caseId: string, content: string) => Promise<void>;
  /** Abort the in-flight stream for a case (if any). */
  cancelStream: (caseId: string) => void;
  /** Soft-delete the case's session on the server, then reset locally. */
  deleteSessionAndReset: (caseId: string) => Promise<void>;
  /**
   * Clear the unread flag for a case. Called when the user opens the
   * case in either workspace pane (wired via Zustand subscribe at the
   * bottom of this module). No-op if the case has no slice or isn't
   * currently flagged unread.
   */
  markCaseRead: (caseId: string) => void;
}

// One in-flight stream per case (keyed by caseId).
const activeStreamHandles = new Map<string, StreamHandle>();
// Tool-call args-in-progress, scoped per case so two streams don't clobber.
const toolInputAccumulators = new Map<string, Map<string, string>>();
// Per-case "the user requested a cancel" marker, consumed by the
// sendMessage finally to distinguish a cancelled turn from a successful
// finalize. Set in cancelStream, deleted in the finally block.
const cancelledStreams = new Set<string>();

function getToolAccumulators(caseId: string): Map<string, string> {
  let inner = toolInputAccumulators.get(caseId);
  if (!inner) {
    inner = new Map<string, string>();
    toolInputAccumulators.set(caseId, inner);
  }
  return inner;
}

// ─── Hydration: BE message rows → UI ChatMessage[] ────────────────────

function hydrateMessages(rows: CaseChatMessageRow[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  // tool rows are attached to the most recent assistant message by tool_call_id.
  for (const row of rows) {
    if (row.role === 'user') {
      result.push({
        id: row.id,
        sequenceNumber: row.sequence_number,
        createdAt: row.created_at,
        role: 'user',
        content: row.content,
      });
    } else if (row.role === 'assistant') {
      // Older persisted rows may carry duplicate entries for the same
      // tool_call_id (BE used to merge LangChain's local-shape +
      // content-block server-shape into one tool_calls JSON; the local
      // copy had empty input). Dedupe by id and prefer the entry whose
      // input has actual fields, so the live tool card shows the real
      // query even for those rows.
      const toolCalls = dedupeToolCalls(row.tool_calls ?? []).map((tc) =>
        buildToolCallRender(tc, /* result */ null, 'done'),
      );
      result.push({
        id: row.id,
        sequenceNumber: row.sequence_number,
        createdAt: row.created_at,
        role: 'assistant',
        thinking: row.thinking ?? '',
        content: row.content,
        toolCalls,
        isStreaming: false,
        error: null,
      });
    } else if (row.role === 'tool') {
      const target = findLastAssistant(result);
      if (target && row.tool_call_id) {
        const match = target.toolCalls.find((tc) => tc.id === row.tool_call_id);
        if (match) {
          match.result = parseToolResultPayload(row.content);
          match.status = 'done';
        }
      }
    }
  }
  return result;
}

function buildToolCallRender(
  tc: ToolCallSummary,
  result: unknown | null,
  status: ToolCallRender['status'],
): ToolCallRender {
  return {
    id: tc.id,
    name: tc.name,
    input: tc.input ?? {},
    status,
    result,
  };
}

/**
 * Merge duplicate tool_call entries by id. Server tools (web_search)
 * are sometimes stored twice — once with empty input from LangChain's
 * local-shape, once with the real input from the server_tool_use
 * content block. Prefer the entry whose `input` has actual fields so
 * the rendered card shows the real query.
 */
function dedupeToolCalls(calls: ToolCallSummary[]): ToolCallSummary[] {
  const byId = new Map<string, ToolCallSummary>();
  for (const tc of calls) {
    const existing = byId.get(tc.id);
    if (!existing) {
      byId.set(tc.id, tc);
      continue;
    }
    const existingHasInput =
      existing.input && Object.keys(existing.input).length > 0;
    const incomingHasInput = tc.input && Object.keys(tc.input).length > 0;
    if (!existingHasInput && incomingHasInput) {
      byId.set(tc.id, tc);
    }
  }
  return Array.from(byId.values());
}

function findLastAssistant(msgs: ChatMessage[]): AssistantChatMessage | null {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m && m.role === 'assistant') return m;
  }
  return null;
}

function parseToolResultPayload(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

// ─── Store ────────────────────────────────────────────────────────────

export const useCaseChatStore = create<CaseChatState>((set, get) => ({
  byCase: {},

  loadOrCreateSession: async (caseId) => {
    const existing = get().byCase[caseId];
    if (existing?.session) return;
    patchSlice(set, caseId, {
      session: null,
      messages: [],
      isLoadingHistory: true,
      error: null,
    });
    cancelCaseStream(caseId);

    // Single round trip: BE returns `{session, messages, has_more}` so
    // we don't follow up with a separate GET /messages call.
    const resp = await getOrCreateCaseSession(caseId);
    if (resp.error || !resp.data) {
      patchSlice(set, caseId, {
        isLoadingHistory: false,
        error: resp.error ?? 'Failed to open chat session',
      });
      return;
    }

    patchSlice(set, caseId, {
      session: resp.data.session,
      messages: hydrateMessages(resp.data.messages),
      isLoadingHistory: false,
      error: null,
    });
  },

  resetCase: (caseId) => {
    cancelCaseStream(caseId);
    set((state) => {
      if (!(caseId in state.byCase)) return state;
      const nextByCase = { ...state.byCase };
      delete nextByCase[caseId];
      return { byCase: nextByCase };
    });
  },

  resetAll: () => {
    for (const caseId of Array.from(activeStreamHandles.keys())) {
      cancelCaseStream(caseId);
    }
    set({ byCase: {} });
  },

  sendMessage: async (caseId, content) => {
    const slice = get().byCase[caseId];
    const session = slice?.session;
    if (!session) {
      patchSlice(set, caseId, { error: 'No active chat session.' });
      return;
    }
    const trimmed = content.trim();
    if (!trimmed) return;
    if (slice.isStreaming) return; // ignore double-sends while a turn is in-flight

    const userId = `local-user-${Date.now()}`;
    const assistantId = `local-assistant-${Date.now()}`;
    const userMsg: UserChatMessage = {
      id: userId,
      sequenceNumber: nextOptimisticSequence(slice.messages),
      createdAt: new Date().toISOString(),
      role: 'user',
      content: trimmed,
    };
    const assistantMsg: AssistantChatMessage = {
      id: assistantId,
      sequenceNumber: userMsg.sequenceNumber + 1,
      createdAt: null,
      role: 'assistant',
      thinking: '',
      content: '',
      toolCalls: [],
      isStreaming: true,
      error: null,
    };
    patchSlice(set, caseId, {
      messages: [...slice.messages, userMsg, assistantMsg],
      isStreaming: true,
      error: null,
    });
    getToolAccumulators(caseId).clear();

    const handle = streamCaseChatMessage(session.id, trimmed, {
      onThinkingDelta: (delta) =>
        patchAssistant(set, get, caseId, assistantId, (m) => ({
          thinking: m.thinking + delta,
        })),
      onContentDelta: (delta) =>
        patchAssistant(set, get, caseId, assistantId, (m) => ({
          content: m.content + delta,
        })),
      onToolUseStart: (toolCallId, toolName) =>
        patchAssistant(set, get, caseId, assistantId, (m) => ({
          toolCalls: [
            ...m.toolCalls,
            {
              id: toolCallId,
              name: toolName,
              input: {},
              status: 'streaming-input',
              result: null,
            },
          ],
        })),
      onToolUseInputDelta: (toolCallId, delta) => {
        const accum = getToolAccumulators(caseId);
        const prior = accum.get(toolCallId) ?? '';
        const next = prior + delta;
        accum.set(toolCallId, next);
        let parsed: Record<string, unknown> = {};
        try {
          parsed = JSON.parse(next) as Record<string, unknown>;
        } catch {
          // mid-stream JSON; keep the rendered input as-is until it parses.
          return;
        }
        patchAssistant(set, get, caseId, assistantId, (m) => ({
          toolCalls: m.toolCalls.map((tc) =>
            tc.id === toolCallId
              ? { ...tc, input: parsed, status: 'invoking' }
              : tc,
          ),
        }));
      },
      onToolResult: (toolCallId, _toolName, result) =>
        patchAssistant(set, get, caseId, assistantId, (m) => ({
          toolCalls: m.toolCalls.map((tc) =>
            tc.id === toolCallId
              ? { ...tc, status: 'done', result }
              : tc,
          ),
        })),
      onMessageComplete: (messageId, sequenceNumber) =>
        patchAssistant(set, get, caseId, assistantId, () => ({
          id: messageId,
          sequenceNumber,
          isStreaming: false,
          createdAt: new Date().toISOString(),
        })),
      onError: (message) =>
        patchAssistant(set, get, caseId, assistantId, () => ({
          isStreaming: false,
          error: message,
        })),
    });
    activeStreamHandles.set(caseId, handle);

    try {
      await handle.done;
    } finally {
      if (activeStreamHandles.get(caseId) === handle) {
        activeStreamHandles.delete(caseId);
      }
      patchSlice(set, caseId, { isStreaming: false });

      // Unread bookkeeping: a successful finalize on a case the user
      // wasn't viewing in either pane flags it unread. Cancels and
      // errors don't count — both are user-visible "this didn't ship"
      // signals and shouldn't promote the row to "new activity".
      const wasCancelled = cancelledStreams.delete(caseId);
      const finalSlice = get().byCase[caseId];
      const finalAssistant = finalSlice?.messages.find(
        (m): m is AssistantChatMessage =>
          m.role === 'assistant' && m.id === assistantId,
      );
      const hadError = finalAssistant?.error != null;
      if (!wasCancelled && !hadError) {
        const focusedPrimary = useStudioStore.getState().selectedCaseId;
        const focusedSecondary =
          useWorkspaceSplitStore.getState().secondaryCaseId;
        if (caseId !== focusedPrimary && caseId !== focusedSecondary) {
          patchSlice(set, caseId, { hasUnread: true });
        }
      }

      // Reconcile with DB: a single user turn can produce MULTIPLE
      // assistant rows when the agent makes tool calls (one per
      // iteration of the tool loop). The optimistic single-bubble
      // streaming state has to be replaced with the real persisted
      // shape so reload, refresh, and history-rebuild all agree.
      // Best-effort — a fetch failure leaves the optimistic state in
      // place rather than dropping the user back into an empty thread.
      const sessionId = get().byCase[caseId]?.session?.id;
      if (sessionId) {
        try {
          const fresh = await getCaseSessionMessages(sessionId, { limit: 200 });
          if (
            fresh &&
            !fresh.error &&
            fresh.data &&
            get().byCase[caseId]?.session?.id === sessionId
          ) {
            patchSlice(set, caseId, {
              messages: hydrateMessages(fresh.data.messages),
            });
          }
        } catch {
          // swallow — optimistic state stays visible
        }
      }
    }
  },

  cancelStream: (caseId) => {
    cancelledStreams.add(caseId);
    cancelCaseStream(caseId);
    patchSlice(set, caseId, { isStreaming: false });
  },

  markCaseRead: (caseId) => {
    const slice = get().byCase[caseId];
    if (!slice || !slice.hasUnread) return;
    patchSlice(set, caseId, { hasUnread: false });
  },

  deleteSessionAndReset: async (caseId) => {
    const sid = get().byCase[caseId]?.session?.id;
    if (!sid) return;
    await deleteCaseSession(sid);
    get().resetCase(caseId);
  },
}));

// ─── Helpers ──────────────────────────────────────────────────────────

function nextOptimisticSequence(messages: ChatMessage[]): number {
  if (!messages.length) return 1;
  return messages[messages.length - 1]!.sequenceNumber + 1;
}

type StoreSet = (
  partial:
    | Partial<CaseChatState>
    | ((state: CaseChatState) => Partial<CaseChatState>),
) => void;

function patchSlice(
  set: StoreSet,
  caseId: string,
  patch: Partial<CaseChatSlice>,
): void {
  set((state) => {
    const prior = state.byCase[caseId] ?? EMPTY_CASE_CHAT_SLICE;
    return {
      byCase: {
        ...state.byCase,
        [caseId]: { ...prior, ...patch },
      },
    };
  });
}

function patchAssistant(
  set: StoreSet,
  get: () => CaseChatState,
  caseId: string,
  assistantId: string,
  updater: (m: AssistantChatMessage) => Partial<AssistantChatMessage>,
): void {
  const slice = get().byCase[caseId];
  if (!slice) return;
  const messages = slice.messages.map((m) => {
    if (m.role !== 'assistant' || m.id !== assistantId) return m;
    return { ...m, ...updater(m) };
  });
  patchSlice(set, caseId, { messages });
}

function cancelCaseStream(caseId: string): void {
  const handle = activeStreamHandles.get(caseId);
  if (handle) {
    handle.abort();
    activeStreamHandles.delete(caseId);
  }
  toolInputAccumulators.get(caseId)?.clear();
}

// ─── Cross-store subscriptions ────────────────────────────────────────
//
// Selecting a case (either pane) clears its unread flag. Subscribing
// here keeps the studio / workspace-split stores ignorant of chat state
// — they don't import this module, no circular dep.
useStudioStore.subscribe((state, prev) => {
  const id = state.selectedCaseId;
  if (id && id !== prev.selectedCaseId) {
    useCaseChatStore.getState().markCaseRead(id);
  }
});

useWorkspaceSplitStore.subscribe((state, prev) => {
  const id = state.secondaryCaseId;
  if (id && id !== prev.secondaryCaseId) {
    useCaseChatStore.getState().markCaseRead(id);
  }
});
