/**
 * SSE stream client for v2 template-draft task updates.
 *
 * Native `EventSource` is used with `withCredentials: true` so the
 * session cookie set by the cookie-auth migration rides along. No
 * `?token=` URL param is needed; the browser handles auth transparently.
 *
 * Reconnect: `EventSource` reconnects automatically on transient errors.
 * `Last-Event-ID` is preserved by the browser and the BE resumes the
 * Redis Stream from that cursor.
 */

import { API_BASE_URL, API_ENDPOINTS } from '@/constants';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import type { V2TemplateDraftTask } from './templateDraft.service';

let source: EventSource | null = null;

function buildUrl(): string {
  return `${API_BASE_URL}${API_ENDPOINTS.PLEADING_V2.EVENTS}`;
}

function parseTask(raw: string): V2TemplateDraftTask | null {
  try {
    return JSON.parse(raw) as V2TemplateDraftTask;
  } catch (err) {
    console.warn('[templateDraftEvents] failed to parse task payload', err);
    return null;
  }
}

function handleTaskEvent(ev: MessageEvent): void {
  const task = parseTask(ev.data);
  if (task) {
    useTemplateDraftStore.getState().upsertTask(task);
  }
}

function handleRemovedEvent(ev: MessageEvent): void {
  try {
    const { task_id } = JSON.parse(ev.data) as { task_id?: string };
    if (task_id) {
      useTemplateDraftStore.getState().removeTask(task_id);
    }
  } catch (err) {
    console.warn('[templateDraftEvents] failed to parse removed payload', err);
  }
}

function handleSnapshot(ev: MessageEvent): void {
  try {
    const { tasks } = JSON.parse(ev.data) as { tasks: V2TemplateDraftTask[] };
    useTemplateDraftStore.getState().applySnapshot(tasks ?? []);
  } catch (err) {
    console.warn('[templateDraftEvents] failed to parse snapshot', err);
  }
}

export function startTemplateDraftEventStream(): void {
  console.log('[templateDraftEvents] start called');

  // Idempotent: don't reopen if we already have a live stream.
  if (source && source.readyState !== EventSource.CLOSED) {
    console.log('[templateDraftEvents] already open, skipping');
    return;
  }

  if (source) {
    source.close();
    source = null;
  }

  const url = buildUrl();
  console.log('[templateDraftEvents] opening EventSource', url);
  source = new EventSource(url, { withCredentials: true });

  source.addEventListener('open', () => {
    console.log('[templateDraftEvents] stream OPEN');
  });
  source.addEventListener('snapshot', (ev) => {
    console.log('[templateDraftEvents] snapshot received');
    handleSnapshot(ev as MessageEvent);
  });
  source.addEventListener('status_changed', (ev) => {
    console.log('[templateDraftEvents] status_changed received');
    handleTaskEvent(ev as MessageEvent);
  });
  source.addEventListener('awaiting_input', (ev) => {
    console.log('[templateDraftEvents] awaiting_input received');
    handleTaskEvent(ev as MessageEvent);
  });
  source.addEventListener('existing_found', (ev) => {
    console.log('[templateDraftEvents] existing_found received');
    handleTaskEvent(ev as MessageEvent);
  });
  source.addEventListener('completed', (ev) => {
    console.log('[templateDraftEvents] completed received');
    handleTaskEvent(ev as MessageEvent);
  });
  source.addEventListener('failed', (ev) => {
    console.log('[templateDraftEvents] failed received');
    handleTaskEvent(ev as MessageEvent);
  });
  source.addEventListener('cancelled', (ev) => {
    console.log('[templateDraftEvents] cancelled received');
    handleTaskEvent(ev as MessageEvent);
  });
  source.addEventListener('removed', (ev) => {
    console.log('[templateDraftEvents] removed received');
    handleRemovedEvent(ev as MessageEvent);
  });

  source.onerror = () => {
    if (!source) return;
    if (source.readyState === EventSource.CONNECTING) {
      console.warn('[templateDraftEvents] reconnecting…');
      return;
    }
    if (source.readyState === EventSource.CLOSED) {
      console.error('[templateDraftEvents] stream closed permanently');
      source = null;
    }
  };
}

export function stopTemplateDraftEventStream(): void {
  if (source) {
    source.close();
    source = null;
  }
}

export function isTemplateDraftEventStreamOpen(): boolean {
  return source !== null && source.readyState !== EventSource.CLOSED;
}
