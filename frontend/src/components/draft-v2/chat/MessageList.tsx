import React, { useEffect, useRef } from 'react';

import type {
  AssistantChatMessage,
  ChatMessage,
  UserChatMessage,
} from '@/stores/useCaseChatStore';

import { AssistantMessageBubble, UserMessageBubble } from './MessageBubbles';
import { ToolCallTimeline } from './ToolCallTimeline';

/**
 * "AI is typing" placeholder shown while a session is being created /
 * its transcript is being hydrated. Mirrors the empty-streaming-state
 * affordance in `AssistantMessageBubble` so the loading and streaming
 * UX read as the same operation.
 */
const AssistantTypingPlaceholder: React.FC = () => (
  <div className="flex flex-col items-start gap-2">
    <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-app-accent-text">
      <span className="inline-flex h-5 w-5 items-center justify-center rounded-md border border-border bg-surface">
        <img src="/logo.png" alt="" className="h-3 w-3 object-contain" />
      </span>
      AI Assistant
      <span className="inline-flex items-center gap-1 rounded-full bg-app-accent-soft px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-app-accent-text">
        Preparing
      </span>
    </div>
    <div className="flex items-center gap-2 rounded-2xl bg-app-accent-soft/40 px-5 py-3 text-sm text-muted">
      <span
        className="inline-block h-2 w-2 animate-bounce rounded-full bg-app-accent"
        style={{ animationDelay: '0ms' }}
        aria-hidden="true"
      />
      <span
        className="inline-block h-2 w-2 animate-bounce rounded-full bg-app-accent"
        style={{ animationDelay: '120ms' }}
        aria-hidden="true"
      />
      <span
        className="inline-block h-2 w-2 animate-bounce rounded-full bg-app-accent"
        style={{ animationDelay: '240ms' }}
        aria-hidden="true"
      />
      <span className="ml-1 text-xs">Opening this case…</span>
    </div>
  </div>
);

interface MessageListProps {
  messages: ChatMessage[];
  isLoadingHistory: boolean;
  emptyHint?: string;
}

/**
 * Scrollable transcript. Auto-pins to the bottom on new messages /
 * streaming deltas so the user sees the latest output. If the user
 * manually scrolls up (within the last ~80px), we stop pinning until
 * they hit the bottom again.
 */
export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isLoadingHistory,
  emptyHint,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const shouldPinRef = useRef<boolean>(true);
  // Window during which scroll events are programmatic (our own pin
  // calls) and must NOT toggle shouldPinRef off. Without this, our own
  // `scrollTop = scrollHeight` assignment fires a scroll event whose
  // distance-from-bottom reads as non-zero (because markdown layout is
  // still settling), which would falsely disengage the pin.
  const programmaticUntilRef = useRef<number>(0);

  const pinToBottom = (): void => {
    const el = scrollRef.current;
    if (!el) return;
    programmaticUntilRef.current = performance.now() + 200;
    el.scrollTop = el.scrollHeight;
  };

  useEffect(() => {
    if (!shouldPinRef.current) return;
    pinToBottom();
  }, [messages]);

  // ResizeObserver on the inner content div: streamed tokens, markdown
  // blocks settling layout, and tool cards expanding their result panels
  // all grow the content height AFTER React's commit phase. Re-pin to
  // the bottom on every height change so the transcript stays glued to
  // the latest output during streaming.
  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      if (!shouldPinRef.current) return;
      pinToBottom();
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>): void => {
    if (performance.now() < programmaticUntilRef.current) return;
    const el = e.currentTarget;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    shouldPinRef.current = distanceFromBottom < 80;
  };

  if (isLoadingHistory) {
    return (
      <div className="flex-1 overflow-y-auto px-6 py-8 sm:px-10">
        <div className="mx-auto flex max-w-5xl flex-col gap-8">
          <AssistantTypingPlaceholder />
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
        <p className="text-sm font-semibold text-text-secondary">
          Ask anything about this case.
        </p>
        <p className="max-w-md text-xs text-muted">
          {emptyHint ??
            'I can search the case file, the petition itself, and case-related emails. Type / to draft from a template instead.'}
        </p>
      </div>
    );
  }

  // A single user turn can produce multiple assistant rows when the
  // agent loops over tool calls. Group those rows under a single
  // "AI Assistant" header with tight inner spacing so the turn reads
  // as one conversational block, not three stacked turns.
  const groups: Array<UserChatMessage | AssistantChatMessage[]> = [];
  for (const m of messages) {
    if (m.role === 'user') {
      groups.push(m);
      continue;
    }
    const last = groups[groups.length - 1];
    if (Array.isArray(last)) {
      last.push(m);
    } else {
      groups.push([m]);
    }
  }

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      style={{ overflowAnchor: 'none' }}
      className="flex-1 overflow-y-auto px-6 py-8 sm:px-10"
    >
      <div ref={contentRef} className="mx-auto flex max-w-5xl flex-col gap-8">
        {groups.map((g, idx) => {
          if (!Array.isArray(g)) {
            return <UserMessageBubble key={`u-${g.id}-${idx}`} message={g} />;
          }
          // A single assistant row → render the bubble normally so its
          // own (live-streaming) ToolCallTimeline is visible.
          if (g.length === 1) {
            return (
              <div key={`assistant-run-${g[0]!.id}`} className="flex flex-col gap-3">
                <AssistantMessageBubble message={g[0]!} showHeader />
              </div>
            );
          }
          // Multi-row turn (post-reconcile shape): a single agent turn
          // produced N persisted assistant rows (one per tool-loop
          // iteration). Flatten all tool calls across the rows into ONE
          // unified timeline so the agent's investigation reads as a
          // single connected sequence, not N fragmented mini-timelines.
          // The timeline is injected after the first row's header +
          // thinking and before the remaining rows' content.
          //
          // Intermediate iteration rows often have empty
          // thinking/content/error (only tool_calls, which we just
          // lifted up). Skip those — otherwise we'd render dangling
          // "AI ASSISTANT" headers with no body beneath them.
          const [first, ...rest] = g;
          const allCalls = g.flatMap((a) => a.toolCalls);
          const visibleRest = rest.filter(
            (a) => a.thinking || a.content || a.error,
          );
          return (
            <div key={`assistant-run-${first!.id}`} className="flex flex-col gap-3">
              <AssistantMessageBubble message={first!} showHeader hideToolCalls />
              {allCalls.length > 0 && (
                <div className="w-full max-w-[95%]">
                  <ToolCallTimeline calls={allCalls} />
                </div>
              )}
              {visibleRest.map((a) => (
                <AssistantMessageBubble
                  key={a.id}
                  message={a}
                  showHeader={false}
                  hideToolCalls
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
};
