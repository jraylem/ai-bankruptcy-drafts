const SESSION_SYNC_SOURCE = 'jurisgentic-session-sync';
const SESSION_SYNC_TYPE = 'session-sync';
export const SESSION_SYNC_STORAGE_KEY = 'jurisgentic-session-sync';

export type SessionSyncAction = 'pdf-upserted' | 'review-task-started';

export interface LegacySessionSyncPayload {
  type: 'pdf-updated' | 'review-task-started';
  sessionId: string;
  taskId?: string;
}

export interface SessionSyncMessage {
  source: typeof SESSION_SYNC_SOURCE;
  type: typeof SESSION_SYNC_TYPE;
  action: SessionSyncAction;
  sessionId: string;
  previousSessionId?: string;
  taskId?: string;
}

export const emitSessionSyncMessage = (
  payload: Omit<SessionSyncMessage, 'source' | 'type'>
) => {
  if (typeof window === 'undefined' || window.parent === window) {
    return;
  }

  window.parent.postMessage(
    {
      source: SESSION_SYNC_SOURCE,
      type: SESSION_SYNC_TYPE,
      ...payload,
    },
    window.location.origin
  );
};

export const parseSessionSyncPayload = (value: string): LegacySessionSyncPayload | null => {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as Partial<LegacySessionSyncPayload | SessionSyncMessage>;
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }

    if (parsed.type === 'pdf-updated' && typeof parsed.sessionId === 'string') {
      return {
        type: parsed.type,
        sessionId: parsed.sessionId,
      };
    }

    if (parsed.type === 'review-task-started' && typeof parsed.sessionId === 'string') {
      return {
        type: parsed.type,
        sessionId: parsed.sessionId,
        taskId: typeof parsed.taskId === 'string' ? parsed.taskId : undefined,
      };
    }

    if (parsed.type === SESSION_SYNC_TYPE && parsed.action === 'pdf-upserted' && typeof parsed.sessionId === 'string') {
      return {
        type: 'pdf-updated',
        sessionId: parsed.sessionId,
      };
    }

    if (
      parsed.type === SESSION_SYNC_TYPE &&
      parsed.action === 'review-task-started' &&
      typeof parsed.sessionId === 'string'
    ) {
      return {
        type: 'review-task-started',
        sessionId: parsed.sessionId,
        taskId: typeof parsed.taskId === 'string' ? parsed.taskId : undefined,
      };
    }
  } catch {
    return null;
  }

  return null;
};

export const isSessionSyncMessage = (data: unknown): data is SessionSyncMessage => {
  if (!data || typeof data !== 'object') {
    return false;
  }

  const candidate = data as Partial<SessionSyncMessage>;
  return (
    candidate.source === SESSION_SYNC_SOURCE &&
    candidate.type === SESSION_SYNC_TYPE &&
    (candidate.action === 'pdf-upserted' || candidate.action === 'review-task-started') &&
    typeof candidate.sessionId === 'string'
  );
};
