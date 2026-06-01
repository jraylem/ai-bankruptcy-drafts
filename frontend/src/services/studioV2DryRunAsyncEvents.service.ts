/**
 * SSE stream client for v2 dry-run-async task updates.
 *
 * Native `EventSource` with `withCredentials: true` so the
 * `access_token` HttpOnly cookie rides along. Mirrors
 * `studioV2ComposerAsyncEvents.service.ts` 1:1 but listens for the
 * extra `awaiting_input` event the dry-run pause/resume protocol
 * needs, and routes payloads into `useStudioV2DryRunTasksStore`.
 *
 * Reconnect: `EventSource` reconnects automatically on transient
 * errors. `Last-Event-ID` is preserved by the browser; the BE
 * resumes the Redis Stream from that cursor.
 *
 * **Scope:** this consumer must ONLY be mounted on `/studio-v2` so
 * dry-run task updates don't bleed into chat or cases pages. The
 * page-level start/stop hooks enforce this (see
 * pages/studio-v2/index.tsx).
 */

import { useStudioV2DryRunTasksStore } from '@/stores/useStudioV2DryRunTasksStore';
import {
  buildDryRunAsyncEventsUrl,
  type V2DryRunTask,
} from './studioV2DryRunAsync.service';

let source: EventSource | null = null;

function parseTask(raw: string): V2DryRunTask | null {
  try {
    return JSON.parse(raw) as V2DryRunTask;
  } catch (err) {
    console.warn('[dryRunAsyncEvents] failed to parse task payload', err);
    return null;
  }
}

function handleTaskEvent(ev: MessageEvent): void {
  const task = parseTask(ev.data);
  if (task) {
    useStudioV2DryRunTasksStore.getState().upsertTask(task);
  }
}

function handleRemovedEvent(ev: MessageEvent): void {
  try {
    const { task_id } = JSON.parse(ev.data) as { task_id?: string };
    if (task_id) {
      useStudioV2DryRunTasksStore.getState().removeTask(task_id);
    }
  } catch (err) {
    console.warn('[dryRunAsyncEvents] failed to parse removed payload', err);
  }
}

function handleSnapshot(ev: MessageEvent): void {
  try {
    const { tasks } = JSON.parse(ev.data) as { tasks: V2DryRunTask[] };
    useStudioV2DryRunTasksStore.getState().applySnapshot(tasks ?? []);
  } catch (err) {
    console.warn('[dryRunAsyncEvents] failed to parse snapshot', err);
  }
}

export function startStudioV2DryRunEventStream(): void {
  console.log('[dryRunAsyncEvents] start called');

  // Idempotent: don't reopen if we already have a live stream.
  if (source && source.readyState !== EventSource.CLOSED) {
    console.log('[dryRunAsyncEvents] already open, skipping');
    return;
  }
  if (source) {
    source.close();
    source = null;
  }

  const url = buildDryRunAsyncEventsUrl();
  console.log('[dryRunAsyncEvents] opening EventSource', url);
  source = new EventSource(url, { withCredentials: true });

  source.addEventListener('open', () => {
    console.log('[dryRunAsyncEvents] stream OPEN');
  });
  source.addEventListener('snapshot', (ev) => handleSnapshot(ev as MessageEvent));
  source.addEventListener('status_changed', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('awaiting_input', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('completed', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('failed', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('cancelled', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('removed', (ev) => handleRemovedEvent(ev as MessageEvent));

  source.onerror = () => {
    if (!source) return;
    if (source.readyState === EventSource.CONNECTING) {
      console.warn('[dryRunAsyncEvents] reconnecting…');
      return;
    }
    if (source.readyState === EventSource.CLOSED) {
      console.error('[dryRunAsyncEvents] stream closed permanently');
      source = null;
    }
  };
}

export function stopStudioV2DryRunEventStream(): void {
  if (source) {
    source.close();
    source = null;
  }
}

export function isStudioV2DryRunEventStreamOpen(): boolean {
  return source !== null && source.readyState !== EventSource.CLOSED;
}
