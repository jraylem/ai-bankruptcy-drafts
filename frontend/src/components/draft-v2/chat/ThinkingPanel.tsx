import React, { useState } from 'react';
import { LuChevronDown, LuChevronRight, LuBrain } from 'react-icons/lu';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {
  CHAT_MARKDOWN_CLASSNAME,
  chatMarkdownComponents,
} from '@/components/chat/markdown';

interface ThinkingPanelProps {
  thinking: string;
  isStreaming: boolean;
}

/**
 * Collapsible extended-thinking display.
 *
 * Default collapsed — most attorneys want the answer, not the trace.
 * When the assistant is mid-thinking and there's no visible content yet,
 * the panel auto-expands so users see *something* happening.
 */
export const ThinkingPanel: React.FC<ThinkingPanelProps> = ({
  thinking,
  isStreaming,
}) => {
  const [expanded, setExpanded] = useState<boolean>(false);

  if (!thinking) return null;

  return (
    <div className="rounded-lg border border-border bg-surface-muted/50">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-[0.18em] text-muted hover:text-text-secondary"
        aria-expanded={expanded}
      >
        {expanded ? (
          <LuChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <LuChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        <LuBrain className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Thinking{isStreaming ? '…' : ''}</span>
        {isStreaming && (
          <span
            className="ml-auto inline-block h-2 w-2 animate-pulse rounded-full bg-app-accent"
            aria-hidden="true"
          />
        )}
      </button>
      {expanded && (
        <div className={`${CHAT_MARKDOWN_CLASSNAME} border-t border-border bg-surface px-3 py-2`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={chatMarkdownComponents}>
            {thinking}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
};
