import React from 'react';
import { LuUser } from 'react-icons/lu';
import { Streamdown } from 'streamdown';

import {
  CHAT_MARKDOWN_CLASSNAME,
  chatMarkdownComponents,
} from '@/components/chat/markdown';
import type {
  AssistantChatMessage,
  UserChatMessage,
} from '@/stores/useCaseChatStore';

import { ThinkingPanel } from './ThinkingPanel';
import { ToolCallTimeline } from './ToolCallTimeline';

/**
 * Three bouncing dots — shown inside the assistant content bubble while
 * the model is preparing a response and no content / tool calls have
 * arrived yet. Replaces the previous bespoke "Thinking…" placeholder.
 */
const ThinkingDots: React.FC = () => (
  <div className="flex items-center gap-1">
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
  </div>
);

/**
 * Bubble for a single user turn.
 */
export const UserMessageBubble: React.FC<{ message: UserChatMessage }> = ({
  message,
}) => (
  <div className="flex flex-col items-end gap-2">
    <div className="flex flex-row-reverse items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle">
      <span className="inline-flex h-5 w-5 items-center justify-center rounded-md border border-border bg-surface text-text-secondary">
        <LuUser className="h-3 w-3" aria-hidden="true" />
      </span>
      You
    </div>
    <div className="max-w-[85%] rounded-2xl border border-border bg-surface px-5 py-3 text-sm leading-relaxed text-text-secondary whitespace-pre-wrap">
      {message.content}
    </div>
  </div>
);

/**
 * Bubble for an assistant turn — renders (collapsible) thinking panel,
 * any tool-call cards, and the visible text. The visible text bubble
 * delegates to `StreamingText` which handles smooth character reveal,
 * stable/live markdown boundary, and the bouncing-dot "thinking"
 * indicator when no content has arrived yet.
 */
export const AssistantMessageBubble: React.FC<{
  message: AssistantChatMessage;
  /**
   * When false, the "AI Assistant" header chip is suppressed — the
   * caller (typically `MessageList`) sets this on assistant bubbles
   * that directly follow another assistant bubble, so a single
   * multi-step tool-using turn shows ONE header at the top instead
   * of one per agent iteration.
   */
  showHeader?: boolean;
  /**
   * When true, the per-bubble tool-call timeline is suppressed — the
   * caller renders ONE unified timeline at the group level so a turn
   * that spans multiple persisted assistant rows reads as a single
   * connected sequence of investigative steps, not several fragmented
   * timelines stacked vertically.
   */
  hideToolCalls?: boolean;
}> = ({ message, showHeader = true, hideToolCalls = false }) => {
  // Two indicators live in the bubble body now:
  //   - empty-state dots: shown when streaming and no visible content has
  //     arrived yet. Sits inside the bubble in place of the markdown.
  //   - still-working footer dots: shown when streaming AND content
  //     has already arrived (e.g. the model emitted intermediate text
  //     and is now running another tool call). Without this, the
  //     bubble looks "frozen" mid-turn.
  const showEmptyDots = message.isStreaming && !message.content;
  const showStillWorkingDots = message.isStreaming && Boolean(message.content);
  const showContentBubble = Boolean(message.content) || showEmptyDots;

  return (
    <div className="flex flex-col items-start gap-2">
      {showHeader && (
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-app-accent-text">
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-md border border-border bg-surface">
            <img src="/logo.png" alt="" className="h-3 w-3 object-contain" />
          </span>
          AI Assistant
          {message.isStreaming && (
            <span className="inline-flex items-center gap-1 rounded-full bg-app-accent-soft px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-app-accent-text">
              Streaming
            </span>
          )}
        </div>
      )}

      <div className="flex w-full max-w-[95%] flex-col gap-2">
        <ThinkingPanel
          thinking={message.thinking}
          isStreaming={message.isStreaming && !message.content}
        />

        {!hideToolCalls && message.toolCalls.length > 0 && (
          <ToolCallTimeline calls={message.toolCalls} />
        )}

        {showContentBubble && (
          <div className="rounded-2xl bg-app-accent-soft/60 px-5 py-3 text-sm leading-relaxed text-text-secondary">
            {showEmptyDots ? (
              <ThinkingDots />
            ) : (
              <Streamdown
                className={CHAT_MARKDOWN_CLASSNAME}
                components={chatMarkdownComponents}
                animated={false}
                parseIncompleteMarkdown
              >
                {message.content}
              </Streamdown>
            )}
          </div>
        )}

        {showStillWorkingDots && (
          <div className="px-1">
            <ThinkingDots />
          </div>
        )}

        {message.error && (
          <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-800">
            {message.error}
          </div>
        )}
      </div>
    </div>
  );
};
