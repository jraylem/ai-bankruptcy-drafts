import React, { useState } from 'react';
import {
  LuChevronDown,
  LuChevronRight,
  LuCheck,
  LuLoader,
  LuSearch,
  LuFileText,
  LuMail,
  LuGlobe,
  LuWrench,
} from 'react-icons/lu';

import type { ToolCallRender } from '@/stores/useCaseChatStore';

interface ToolCallCardProps {
  call: ToolCallRender;
}

/**
 * One in-line tool-call card under an assistant turn.
 *
 * Renders the tool name, its input args (pretty JSON, collapsed by
 * default), and a status indicator. When the BE returns a result, the
 * card expands the result by default for the first paint, then becomes
 * collapsible.
 */
export const ToolCallCard: React.FC<ToolCallCardProps> = ({ call }) => {
  const [expanded, setExpanded] = useState<boolean>(false);

  return (
    <div className="rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-text-secondary hover:bg-surface-muted/50"
        aria-expanded={expanded}
      >
        {expanded ? (
          <LuChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" aria-hidden="true" />
        ) : (
          <LuChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" aria-hidden="true" />
        )}
        <ToolIcon name={call.name} />
        <span className="font-mono text-[12px] font-semibold text-text-secondary">
          {humanizeToolName(call.name)}
        </span>
        <StatusBadge status={call.status} />
      </button>
      {expanded && (
        <div className="space-y-2 border-t border-border bg-surface-muted/40 px-3 py-2 text-xs">
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
              Input
            </div>
            <pre className="overflow-x-auto rounded bg-surface px-2 py-1 font-mono text-[11px] leading-relaxed text-text-secondary">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </div>
          {call.result !== null && (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
                Result
              </div>
              <pre className="max-h-64 overflow-auto rounded bg-surface px-2 py-1 font-mono text-[11px] leading-relaxed text-text-secondary">
                {formatResult(call.result)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const ToolIcon: React.FC<{ name: string }> = ({ name }) => {
  const className = 'h-3.5 w-3.5 shrink-0 text-app-accent-text';
  if (name === 'case_vector_search')
    return <LuSearch className={className} aria-hidden="true" />;
  if (name === 'petition_vision_lookup')
    return <LuFileText className={className} aria-hidden="true" />;
  if (name === 'case_emails_search')
    return <LuMail className={className} aria-hidden="true" />;
  if (name === 'gmail_search')
    return <LuMail className={className} aria-hidden="true" />;
  if (name === 'web_search')
    return <LuGlobe className={className} aria-hidden="true" />;
  return <LuWrench className={className} aria-hidden="true" />;
};

const StatusBadge: React.FC<{ status: ToolCallRender['status'] }> = ({ status }) => {
  if (status === 'done') {
    return (
      <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
        <LuCheck className="h-3 w-3" aria-hidden="true" />
        Done
      </span>
    );
  }
  if (status === 'error') {
    return (
      <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-rose-700">
        Error
      </span>
    );
  }
  const label = status === 'streaming-input' ? 'Preparing' : 'Running';
  return (
    <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
      <LuLoader className="h-3 w-3 animate-spin" aria-hidden="true" />
      {label}
    </span>
  );
};

function humanizeToolName(name: string): string {
  // Friendly labels for the tools the agent commonly invokes. Falls back
  // to title-cased name for any unknown tool.
  if (name === 'case_vector_search') return 'Case File Search';
  if (name === 'petition_vision_lookup') return 'Petition Vision Lookup';
  if (name === 'case_emails_search') return 'Case Emails Search';
  if (name === 'gmail_search') return 'Gmail Search';
  if (name === 'web_search') return 'Web Search';
  return name.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatResult(result: unknown): string {
  if (typeof result === 'string') return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}
