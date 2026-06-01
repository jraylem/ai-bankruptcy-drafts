/**
 * SSE stream client for v2 composer-async task updates.
 *
 * Native `EventSource` with `withCredentials: true` so the
 * `access_token` HttpOnly cookie rides along. Mirrors
 * `templateDraftEvents.service.ts` 1:1 — listens for the same event
 * shape (`snapshot`, `status_changed`, `completed`, `failed`,
 * `cancelled`, `removed`) but routes payloads into
 * `useStudioV2ComposerTasksStore`.
 *
 * The composer state machine has fewer event types than pleading
 * (no `awaiting_input`, no `existing_found`) but the wire shape is
 * identical so all listener handlers reuse the task-upsert helper.
 *
 * Reconnect: `EventSource` reconnects automatically on transient
 * errors. `Last-Event-ID` is preserved by the browser; the BE
 * resumes the Redis Stream from that cursor.
 */

import { useStudioV2ComposerTasksStore } from '@/stores/useStudioV2ComposerTasksStore';
import {
  buildComposerEventsUrl,
  type V2ComposerTask,
} from './studioV2ComposerAsync.service';

let source: EventSource | null = null;

function parseTask(raw: string): V2ComposerTask | null {
  try {
    return JSON.parse(raw) as V2ComposerTask;
  } catch (err) {
    console.warn('[composerAsyncEvents] failed to parse task payload', err);
    return null;
  }
}

function handleTaskEvent(ev: MessageEvent): void {
  const task = parseTask(ev.data);
  if (task) {
    useStudioV2ComposerTasksStore.getState().upsertTask(task);
  }
}

function handleRemovedEvent(ev: MessageEvent): void {
  try {
    const { task_id } = JSON.parse(ev.data) as { task_id?: string };
    if (task_id) {
      useStudioV2ComposerTasksStore.getState().removeTask(task_id);
    }
  } catch (err) {
    console.warn('[composerAsyncEvents] failed to parse removed payload', err);
  }
}

function handleSnapshot(ev: MessageEvent): void {
  try {
    const { tasks } = JSON.parse(ev.data) as { tasks: V2ComposerTask[] };
    useStudioV2ComposerTasksStore.getState().applySnapshot(tasks ?? []);
  } catch (err) {
    console.warn('[composerAsyncEvents] failed to parse snapshot', err);
  }
}

export function startStudioV2ComposerEventStream(): void {
  console.log('[composerAsyncEvents] start called');

  // Idempotent: don't reopen if we already have a live stream.
  if (source && source.readyState !== EventSource.CLOSED) {
    console.log('[composerAsyncEvents] already open, skipping');
    return;
  }
  if (source) {
    source.close();
    source = null;
  }

  const url = buildComposerEventsUrl();
  console.log('[composerAsyncEvents] opening EventSource', url);
  source = new EventSource(url, { withCredentials: true });

  source.addEventListener('open', () => {
    console.log('[composerAsyncEvents] stream OPEN');
  });
  source.addEventListener('snapshot', (ev) => handleSnapshot(ev as MessageEvent));
  source.addEventListener('status_changed', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('completed', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('failed', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('cancelled', (ev) => handleTaskEvent(ev as MessageEvent));
  source.addEventListener('removed', (ev) => handleRemovedEvent(ev as MessageEvent));

  source.onerror = () => {
    if (!source) return;
    if (source.readyState === EventSource.CONNECTING) {
      console.warn('[composerAsyncEvents] reconnecting…');
      return;
    }
    if (source.readyState === EventSource.CLOSED) {
      console.error('[composerAsyncEvents] stream closed permanently');
      source = null;
    }
  };
}

export function stopStudioV2ComposerEventStream(): void {
  if (source) {
    source.close();
    source = null;
  }
}

export function isStudioV2ComposerEventStreamOpen(): boolean {
  return source !== null && source.readyState !== EventSource.CLOSED;
}
