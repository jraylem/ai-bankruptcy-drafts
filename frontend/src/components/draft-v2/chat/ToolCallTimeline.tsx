import React from 'react';

import type { ToolCallRender } from '@/stores/useCaseChatStore';

import { ToolCallCard } from './ToolCallCard';

interface ToolCallTimelineProps {
  calls: ToolCallRender[];
}

/**
 * Renders a list of tool calls as a vertical timeline: a hairline rail
 * down the left, a status-colored dot per step, and the existing
 * ToolCallCard body to the right of each dot. Communicates that the
 * agent's research was a SEQUENCE of investigative steps, not a stack
 * of independent boxes. Each node remains expandable to inspect its
 * input/result.
 */
export const ToolCallTimeline: React.FC<ToolCallTimelineProps> = ({ calls }) => {
  if (calls.length === 0) return null;
  return (
    <div className="relative flex flex-col gap-3 pl-7">
      <div
        aria-hidden="true"
        className="absolute left-[10px] top-3 bottom-3 border-l-2 border-dotted border-app-accent/70"
      />
      {calls.map((call) => {
        const isActive =
          call.status === 'streaming-input' || call.status === 'invoking';
        return (
          <div key={call.id} className="relative">
            <span
              aria-hidden="true"
              className="absolute -left-[22px] top-3 flex h-3 w-3"
            >
              {isActive && (
                <span
                  className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${dotColor(call.status)}`}
                />
              )}
              <span
                className={`relative inline-flex h-3 w-3 rounded-full ${dotColor(call.status)}`}
              />
            </span>
            <ToolCallCard call={call} />
          </div>
        );
      })}
    </div>
  );
};

function dotColor(status: ToolCallRender['status']): string {
  if (status === 'done') return 'bg-emerald-500';
  if (status === 'error') return 'bg-rose-500';
  return 'bg-app-accent';
}
