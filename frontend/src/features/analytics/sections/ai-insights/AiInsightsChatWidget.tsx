import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import { FiMessageSquare, FiMinus, FiTrash2, FiX } from 'react-icons/fi';
import remarkGfm from 'remark-gfm';
import {
  clearDashboardInsightsChat,
  fetchDashboardInsightsChatHistory,
  streamDashboardInsightsChat,
} from '../../api/insights.api';
import { useDashboardInsights } from '../../hooks/useDashboardInsights';
import { useAnalyticsAiChatStore } from '../../stores/useAnalyticsAiChatStore';

type InsightsChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

type AiInsightsChatWidgetProps = {
  isVisible: boolean;
};

const MAX_CHAT_MESSAGES = 120;
const STREAM_REVEAL_CHUNK_SIZE = 8;
const STREAM_REVEAL_INTERVAL_MS = 40;

const INSIGHTS_CHAT_MARKDOWN_CLASSNAME =
  'max-w-none break-words font-body text-[14px] leading-6 text-text-secondary ' +
  '[&_p]:my-0 [&_p]:text-[14px] [&_p]:leading-6 ' +
  '[&_li]:text-[14px] [&_li]:leading-6 [&_ul]:pl-5 [&_ol]:pl-5 ' +
  '[&_code]:rounded-md [&_code]:bg-app-accent-soft/65 [&_code]:px-1.5 [&_code]:py-0.5';

const AI_INSIGHTS_MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className="mb-2 text-[14px] font-semibold leading-6 text-text-secondary">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 text-[14px] font-semibold leading-6 text-text-secondary">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 text-[14px] font-semibold leading-6 text-text-secondary">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-2 text-[14px] font-semibold leading-6 text-text-secondary">{children}</h4>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 rounded-md border-l-2 border-app-accent/45 bg-app-accent-soft/35 px-3 py-2 text-[14px] leading-6 text-text-secondary">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 w-full overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full border-collapse bg-surface text-left text-[14px] leading-6 text-text-secondary">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-muted">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-border px-2 py-1.5 align-top text-[14px] font-semibold leading-6 text-text-secondary sm:px-3">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-border px-2 py-1.5 align-top text-[14px] leading-6 text-text-secondary sm:px-3">
      {children}
    </td>
  ),
};

const normalizeAssistantDisplayContent = (content: string): string => {
  if (!content) {
    return content;
  }

  return content
    .replace(/([a-z0-9])([.!?])([A-Z])/g, '$1$2\n\n$3')
    .replace(/([^\n])(\n#{1,6}\s)/g, '$1\n$2')
    .replace(/([^\n])(\n[-*]\s)/g, '$1\n$2')
    .replace(/([^\n])(\n>\s)/g, '$1\n$2');
};

const createMessageId = (prefix: string) =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export const AiInsightsChatWidget: React.FC<AiInsightsChatWidgetProps> = ({ isVisible }) => {
  const { data: insightsData } = useDashboardInsights(false);
  const {
    isOpen,
    isMinimized,
    hasInFlightRequest,
    queuedSuggestedAction,
    openWidget,
    minimizeWidget,
    restoreWidget,
    closeWidget,
    consumeQueuedPrompt,
    setInFlight,
    setLastError,
  } = useAnalyticsAiChatStore();

  const [chatMessages, setChatMessages] = useState<InsightsChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isFollowingBottom, setIsFollowingBottom] = useState(true);
  const [streamedResponse, setStreamedResponse] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const suggestionScrollRef = useRef<HTMLDivElement>(null);
  const chatTextareaRef = useRef<HTMLTextAreaElement>(null);
  const widgetContainerRef = useRef<HTMLDivElement>(null);
  const lastScrollTopRef = useRef(0);
  const latestActionRequestIdRef = useRef(0);
  const latestHistoryRequestIdRef = useRef(0);
  const hasHydratedHistoryRef = useRef(false);
  const streamRevealQueueRef = useRef('');
  const streamDrainTimerRef = useRef<number | null>(null);
  const activeChatRequestRef = useRef<AbortController | null>(null);
  const activeHistoryRequestRef = useRef<AbortController | null>(null);
  const suggestionDragRef = useRef({
    isDragging: false,
    startX: 0,
    startScrollLeft: 0,
    moved: false,
  });
  const sendMessageRef = useRef<(message: string) => Promise<void>>(async () => {});
  const shouldHydrateHistory =
    isVisible && (isOpen || isMinimized || queuedSuggestedAction !== null);
  const isBusy = isHistoryLoading || isActionLoading || isStreaming;
  const suggestedActions = insightsData?.suggested_actions ?? [];

  const appendChatMessage = useCallback((message: InsightsChatMessage) => {
    setChatMessages((current) => {
      const next = [...current, message];
      if (next.length <= MAX_CHAT_MESSAGES) {
        return next;
      }
      return next.slice(next.length - MAX_CHAT_MESSAGES);
    });
  }, []);

  const handleSuggestionsMouseDown = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const container = suggestionScrollRef.current;
    if (!container) {
      return;
    }
    suggestionDragRef.current.isDragging = true;
    suggestionDragRef.current.startX = event.clientX;
    suggestionDragRef.current.startScrollLeft = container.scrollLeft;
    suggestionDragRef.current.moved = false;
  }, []);

  const handleSuggestionsMouseMove = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const container = suggestionScrollRef.current;
    if (!container || !suggestionDragRef.current.isDragging) {
      return;
    }
    const deltaX = event.clientX - suggestionDragRef.current.startX;
    if (Math.abs(deltaX) > 3) {
      suggestionDragRef.current.moved = true;
    }
    container.scrollLeft = suggestionDragRef.current.startScrollLeft - deltaX;
    event.preventDefault();
  }, []);

  const handleSuggestionsMouseUp = useCallback(() => {
    suggestionDragRef.current.isDragging = false;
  }, []);

  const scrollChatToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    if (typeof window === 'undefined') {
      return;
    }
    const container = chatScrollRef.current;
    if (!container) {
      return;
    }
    container.scrollTo({
      top: container.scrollHeight,
      behavior,
    });
  }, []);

  const isNearBottom = useCallback((container: HTMLDivElement, threshold = 24) => {
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    return distanceFromBottom <= threshold;
  }, []);

  const handleChatScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      const container = event.currentTarget;
      const currentTop = container.scrollTop;
      const isUserScrollingUp = currentTop < lastScrollTopRef.current;
      lastScrollTopRef.current = currentTop;

      if (isUserScrollingUp) {
        setIsFollowingBottom(false);
        return;
      }

      const nearBottom = isNearBottom(container);
      setIsFollowingBottom((current) => (current === nearBottom ? current : nearBottom));
    },
    [isNearBottom]
  );

  const resizeChatTextarea = useCallback(() => {
    const textarea = chatTextareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = 'auto';
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, 36), 88);
    textarea.style.height = `${nextHeight}px`;
  }, []);

  const stopStreamDrain = useCallback(() => {
    if (streamDrainTimerRef.current === null || typeof window === 'undefined') {
      return;
    }
    window.clearInterval(streamDrainTimerRef.current);
    streamDrainTimerRef.current = null;
  }, []);

  const startStreamDrain = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (streamDrainTimerRef.current !== null) {
      return;
    }

    streamDrainTimerRef.current = window.setInterval(() => {
      const queued = streamRevealQueueRef.current;
      if (!queued) {
        stopStreamDrain();
        return;
      }

      const nextChunk = queued.slice(0, STREAM_REVEAL_CHUNK_SIZE);
      streamRevealQueueRef.current = queued.slice(nextChunk.length);
      setStreamedResponse((current) => current + nextChunk);

      if (!streamRevealQueueRef.current) {
        stopStreamDrain();
      }
    }, STREAM_REVEAL_INTERVAL_MS);
  }, [stopStreamDrain]);

  const waitForStreamDrain = useCallback(async () => {
    if (typeof window === 'undefined') {
      return;
    }
    while (streamRevealQueueRef.current.length > 0) {
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, STREAM_REVEAL_INTERVAL_MS);
      });
    }
  }, []);

  const sendInsightsChatMessage = useCallback(
    async (message: string) => {
      const prompt = message.trim();
      if (!prompt) {
        return;
      }

      if (activeChatRequestRef.current) {
        activeChatRequestRef.current.abort();
        activeChatRequestRef.current = null;
      }

      const abortController = new AbortController();
      activeChatRequestRef.current = abortController;
      const requestId = latestActionRequestIdRef.current + 1;
      latestActionRequestIdRef.current = requestId;

      setActionError(null);
      setLastError(null);
      setIsActionLoading(true);
      setInFlight(true);
      setIsFollowingBottom(true);
      setStreamStatus(null);
      streamRevealQueueRef.current = '';
      stopStreamDrain();
      setStreamedResponse('');
      setChatInput('');
      appendChatMessage({
        id: createMessageId('u'),
        role: 'user',
        content: prompt,
      });

      try {
        const response = await streamDashboardInsightsChat(prompt, {
          signal: abortController.signal,
          onTextChunk: (_fullText, chunk) => {
            if (latestActionRequestIdRef.current !== requestId) {
              return;
            }
            const nextChunk = chunk || '';
            if (!nextChunk) {
              return;
            }
            setIsActionLoading(false);
            setStreamStatus(null);
            setIsStreaming(true);
            streamRevealQueueRef.current += nextChunk;
            startStreamDrain();
          },
          onToolStatus: (name, status) => {
            if (latestActionRequestIdRef.current !== requestId) {
              return;
            }
            if (status === 'running') {
              setStreamStatus(`Analyzing ${name.replace(/_/g, ' ')}...`);
              return;
            }
            setStreamStatus('Compiling response...');
          },
        });

        if (latestActionRequestIdRef.current !== requestId) {
          return;
        }

        const fullReply = response.reply?.trim() || 'No response generated for this prompt.';
        await waitForStreamDrain();
        stopStreamDrain();
        setIsActionLoading(false);
        setStreamStatus(null);
        setIsStreaming(false);
        streamRevealQueueRef.current = '';
        setStreamedResponse('');
        setInFlight(false);
        appendChatMessage({
          id: createMessageId('a'),
          role: 'assistant',
          content: fullReply,
        });
      } catch (error) {
        if (latestActionRequestIdRef.current !== requestId) {
          return;
        }

        const normalizedMessage = error instanceof Error ? error.message.toLowerCase() : '';
        if (normalizedMessage.includes('canceled') || normalizedMessage.includes('aborted')) {
          return;
        }

        const messageText =
          error instanceof Error ? error.message : 'Failed to load chat response.';
        setActionError(messageText);
        setLastError(messageText);
        setStreamStatus(null);
        setInFlight(false);
      } finally {
        if (activeChatRequestRef.current === abortController) {
          activeChatRequestRef.current = null;
        }
        stopStreamDrain();
        if (latestActionRequestIdRef.current === requestId) {
          setIsActionLoading(false);
          setInFlight(false);
        }
      }
    },
    [
      appendChatMessage,
      setInFlight,
      setLastError,
      startStreamDrain,
      stopStreamDrain,
      waitForStreamDrain,
    ]
  );

  const handleSubmitChat = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      await sendInsightsChatMessage(chatInput);
    },
    [chatInput, sendInsightsChatMessage]
  );

  const clearInsightsChat = useCallback(async () => {
    const requestId = latestActionRequestIdRef.current + 1;
    latestActionRequestIdRef.current = requestId;

    if (activeChatRequestRef.current) {
      activeChatRequestRef.current.abort();
      activeChatRequestRef.current = null;
    }

    setActionError(null);
    setLastError(null);
    setIsActionLoading(true);
    setIsStreaming(false);
    setStreamStatus(null);
    streamRevealQueueRef.current = '';
    stopStreamDrain();
    setStreamedResponse('');
    setInFlight(false);

    try {
      await clearDashboardInsightsChat();
      if (latestActionRequestIdRef.current !== requestId) {
        return;
      }
      setChatMessages([]);
      setChatInput('');
      setIsFollowingBottom(true);
    } catch (error) {
      if (latestActionRequestIdRef.current !== requestId) {
        return;
      }
      const messageText = error instanceof Error ? error.message : 'Failed to clear insights chat.';
      setActionError(messageText);
      setLastError(messageText);
    } finally {
      if (latestActionRequestIdRef.current === requestId) {
        setIsActionLoading(false);
      }
    }
  }, [setInFlight, setLastError, stopStreamDrain]);

  const handleChatInputKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!chatInput.trim() || isBusy) {
          return;
        }
        void sendInsightsChatMessage(chatInput);
      }
    },
    [chatInput, isBusy, sendInsightsChatMessage]
  );

  useEffect(() => {
    sendMessageRef.current = sendInsightsChatMessage;
  }, [sendInsightsChatMessage]);

  useEffect(() => {
    if (!shouldHydrateHistory) {
      return;
    }
    if (hasHydratedHistoryRef.current) {
      return;
    }

    const historyRequestId = latestHistoryRequestIdRef.current + 1;
    latestHistoryRequestIdRef.current = historyRequestId;

    if (activeHistoryRequestRef.current) {
      activeHistoryRequestRef.current.abort();
      activeHistoryRequestRef.current = null;
    }

    const abortController = new AbortController();
    activeHistoryRequestRef.current = abortController;

    setIsHistoryLoading(true);
    setActionError(null);
    setLastError(null);

    void (async () => {
      try {
        const response = await fetchDashboardInsightsChatHistory({
          signal: abortController.signal,
        });

        if (latestHistoryRequestIdRef.current !== historyRequestId) {
          return;
        }

        const hydratedMessages = response.messages
          .filter(
            (message): message is { role: 'user' | 'assistant'; content: string } =>
              (message.role === 'user' || message.role === 'assistant') &&
              typeof message.content === 'string'
          )
          .map((message, index) => ({
            id: `h-${Date.now()}-${index}-${message.role}`,
            role: message.role,
            content: message.content,
          }));

        setChatMessages(hydratedMessages);
        hasHydratedHistoryRef.current = true;
      } catch (error) {
        if (latestHistoryRequestIdRef.current !== historyRequestId) {
          return;
        }
        const normalizedMessage = error instanceof Error ? error.message.toLowerCase() : '';
        if (normalizedMessage.includes('canceled') || normalizedMessage.includes('aborted')) {
          return;
        }
        const messageText =
          error instanceof Error ? error.message : 'Failed to load previous chat history.';
        setActionError(messageText);
        setLastError(messageText);
        hasHydratedHistoryRef.current = true;
      } finally {
        if (activeHistoryRequestRef.current === abortController) {
          activeHistoryRequestRef.current = null;
        }
        if (latestHistoryRequestIdRef.current === historyRequestId) {
          setIsHistoryLoading(false);
        }
      }
    })();
  }, [setLastError, shouldHydrateHistory]);

  useEffect(() => {
    if (!queuedSuggestedAction) {
      return;
    }
    if (!hasHydratedHistoryRef.current) {
      return;
    }
    if (isHistoryLoading) {
      return;
    }
    const prompt = consumeQueuedPrompt();
    if (!prompt) {
      return;
    }
    void sendMessageRef.current(prompt);
  }, [consumeQueuedPrompt, isHistoryLoading, queuedSuggestedAction]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (typeof window === 'undefined') {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      chatTextareaRef.current?.focus();
      resizeChatTextarea();
      setIsFollowingBottom(true);
      scrollChatToBottom('auto');
      const container = chatScrollRef.current;
      if (container) {
        lastScrollTopRef.current = container.scrollTop;
      }
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [isOpen, resizeChatTextarea, scrollChatToBottom]);

  useEffect(() => {
    resizeChatTextarea();
  }, [chatInput, resizeChatTextarea]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (!isFollowingBottom) {
      return;
    }

    scrollChatToBottom(isActionLoading || isStreaming ? 'auto' : 'smooth');
    if (typeof window === 'undefined') {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const container = chatScrollRef.current;
      if (container) {
        lastScrollTopRef.current = container.scrollTop;
      }
    });
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [
    chatMessages,
    isOpen,
    isActionLoading,
    isFollowingBottom,
    isStreaming,
    scrollChatToBottom,
    streamedResponse,
  ]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (typeof window === 'undefined') {
      return;
    }

    window.addEventListener('resize', resizeChatTextarea);
    return () => {
      window.removeEventListener('resize', resizeChatTextarea);
    };
  }, [isOpen, resizeChatTextarea]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleClickOutside = (event: MouseEvent) => {
      const container = widgetContainerRef.current;
      if (!container) {
        return;
      }
      if (!container.contains(event.target as Node)) {
        closeWidget();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [closeWidget, isOpen]);

  useEffect(() => {
    return () => {
      if (activeChatRequestRef.current) {
        activeChatRequestRef.current.abort();
      }
      if (activeHistoryRequestRef.current) {
        activeHistoryRequestRef.current.abort();
      }
      stopStreamDrain();
      setInFlight(false);
    };
  }, [setInFlight, stopStreamDrain]);

  const triggerLabel = useMemo(() => {
    if (hasInFlightRequest || isStreaming || isActionLoading) {
      return 'AI Chat (working)';
    }
    return 'AI Chat';
  }, [hasInFlightRequest, isActionLoading, isStreaming]);

  if (!isVisible) {
    return null;
  }

  return (
    <div
      ref={widgetContainerRef}
      className="pointer-events-none fixed bottom-4 right-8 z-50 flex w-auto max-w-[calc(100vw-1rem)] flex-col items-end gap-2"
    >
      {!isOpen ? (
        <button
          type="button"
          onClick={() => {
            if (isMinimized) {
              restoreWidget();
              return;
            }
            openWidget();
          }}
          className="ai-chat-trigger pointer-events-auto inline-flex h-10 items-center gap-2 rounded-full bg-surface px-4 text-sm font-semibold text-text shadow-[0_16px_34px_rgba(15,23,42,0.2)] transition-colors hover:bg-surface-muted"
          aria-label={triggerLabel}
        >
          <FiMessageSquare className="ai-chat-trigger-icon h-4 w-4 text-app-accent-text" />
          <span>AI Chat</span>
          {hasInFlightRequest ? (
            <span className="inline-flex items-center" aria-hidden="true">
              <svg
                className="h-4 w-4 animate-spin text-app-accent-text"
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"
                />
              </svg>
            </span>
          ) : null}
        </button>
      ) : null}

      {isOpen ? (
        <section
          aria-label="Analytics AI chat widget"
          className="pointer-events-auto fixed inset-x-2 bottom-0 h-[78vh] max-h-[700px] rounded-t-2xl border border-border/80 bg-surface/95 p-3 shadow-[0_24px_48px_rgba(15,23,42,0.24)] backdrop-blur-xl md:inset-x-auto md:bottom-4 md:right-4 md:h-auto md:w-[430px] md:max-w-[calc(100vw-2rem)] md:rounded-2xl"
        >
          <div className="mb-2 flex items-center justify-between gap-2 border-b border-border/70 px-1 pb-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-text">
              <FiMessageSquare className="h-4 w-4 text-app-accent-text" />
              Analytics AI Chat
            </div>
            <div className="flex items-center gap-1.5">
              <div className="group relative">
                <button
                  type="button"
                  onClick={() => void clearInsightsChat()}
                  disabled={isBusy || chatMessages.length === 0}
                  className="rounded-lg p-1.5 text-muted transition-colors hover:bg-app-danger-soft/55 hover:text-app-danger-text disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label="Clear chat"
                >
                  <FiTrash2 className="h-4 w-4" />
                </button>
                <span className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-border/70 bg-surface px-2 py-1 text-[11px] font-medium text-text opacity-0 shadow-sm transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
                  Clear chat
                </span>
              </div>
              <button
                type="button"
                onClick={minimizeWidget}
                className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-muted hover:text-text"
                aria-label="Minimize chat widget"
              >
                <FiMinus className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={closeWidget}
                className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-muted hover:text-text"
                aria-label="Close chat widget"
              >
                <FiX className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="space-y-2 rounded-xl border border-border/80 bg-surface-muted/60 p-2.5">
            <div
              ref={chatScrollRef}
              onScroll={handleChatScroll}
              className="max-h-[48vh] overflow-y-auto px-1 md:max-h-[50vh]"
              style={{ scrollbarColor: 'var(--app-border-strong) transparent' }}
            >
              {chatMessages.length === 0 &&
              !isActionLoading &&
              !isStreaming &&
              !isHistoryLoading ? (
                <div className="mx-auto mb-2 mt-1 flex max-w-[280px] flex-col items-center rounded-xl py-5 text-center">
                  <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-[12px] border border-border bg-surface-muted/60 shadow-[0_12px_28px_-24px_rgba(15,23,42,0.38)]">
                    <img
                      src="/logo.png"
                      alt="Jurisgentic AI"
                      className="logo-on-dark h-[20px] w-[20px] object-contain"
                    />
                  </div>
                  <p className="text-[13px] leading-5 text-muted">
                    Ask about trends, performance, users, or cases.
                  </p>
                </div>
              ) : null}

              {isHistoryLoading ? (
                <div className="mb-3 flex justify-start" aria-label="Loading chat history">
                  <div className="flex w-full max-w-[90%] items-start gap-2.5">
                    <div className="relative mt-0.5 h-9 w-9 shrink-0">
                      <div className="relative z-[1] flex h-9 w-9 items-center justify-center rounded-[12px] border border-border bg-surface shadow-[0_12px_28px_-24px_rgba(15,23,42,0.38)]">
                        <img
                          src="/logo.png"
                          alt="Jurisgentic AI"
                          className="logo-on-dark h-[18px] w-[18px] object-contain"
                        />
                      </div>
                    </div>
                    <div className="flex min-h-[40px] min-w-[64px] items-center rounded-[16px] rounded-tl-sm border border-border bg-surface px-[12px] py-[8px] text-muted shadow-[0_14px_34px_-28px_rgba(91,33,182,0.14)]">
                      {streamStatus ? (
                        <span className="text-[12px] font-medium text-subtle">{streamStatus}</span>
                      ) : (
                        <div className="flex items-center gap-0.5">
                          <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-app-accent animation-delay-0" />
                          <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-app-accent animation-delay-200" />
                          <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-app-accent animation-delay-400" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : null}

              {chatMessages.map((message) => (
                <div
                  key={message.id}
                  className={`mb-3 ${message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}`}
                >
                  {message.role === 'user' ? (
                    <div className="flex max-w-[82%] flex-col items-end">
                      <div className="rounded-[16px] rounded-br-sm bg-[#2f6bff] px-[12px] py-[8px] text-white shadow-[0_14px_32px_-26px_rgba(47,107,255,0.82)]">
                        <p className="whitespace-pre-wrap break-words text-[14px] font-medium leading-6">
                          {message.content}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="flex w-full max-w-[92%] items-start gap-2.5">
                      <div className="relative mt-0.5 h-9 w-9 shrink-0">
                        <div className="relative z-[1] flex h-9 w-9 items-center justify-center rounded-[12px] border border-border bg-surface shadow-[0_12px_28px_-24px_rgba(15,23,42,0.38)]">
                          <img
                            src="/logo.png"
                            alt="Jurisgentic AI"
                            className="logo-on-dark h-[18px] w-[18px] object-contain"
                          />
                        </div>
                      </div>
                      <div className="min-w-0 flex-1 rounded-[16px] rounded-tl-sm border border-border bg-surface px-[12px] py-[8px] text-[14px] leading-6 text-text-secondary shadow-[0_14px_34px_-28px_rgba(91,33,182,0.14)]">
                        <div className={INSIGHTS_CHAT_MARKDOWN_CLASSNAME}>
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={AI_INSIGHTS_MARKDOWN_COMPONENTS}
                          >
                            {normalizeAssistantDisplayContent(message.content)}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {isActionLoading ? (
                <div className="mb-3 flex justify-start" aria-label="Thinking">
                  <div className="flex w-full max-w-[92%] items-start gap-2.5">
                    <div className="relative mt-0.5 h-9 w-9 shrink-0">
                      <div className="relative z-[1] flex h-9 w-9 items-center justify-center rounded-[12px] border border-border bg-surface shadow-[0_12px_28px_-24px_rgba(15,23,42,0.38)]">
                        <img
                          src="/logo.png"
                          alt="Jurisgentic AI"
                          className="logo-on-dark h-[18px] w-[18px] object-contain"
                        />
                      </div>
                    </div>
                    <div className="flex min-h-[40px] min-w-[64px] items-center rounded-[16px] rounded-tl-sm border border-border bg-surface px-[12px] py-[8px] text-muted shadow-[0_14px_34px_-28px_rgba(91,33,182,0.14)]">
                      <div className="flex items-center gap-0.5">
                        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-app-accent animation-delay-0" />
                        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-app-accent animation-delay-200" />
                        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-app-accent animation-delay-400" />
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              {isStreaming ? (
                <div className="mb-3 flex justify-start">
                  <div className="flex w-full max-w-[92%] items-start gap-2.5">
                    <div className="relative mt-0.5 h-9 w-9 shrink-0">
                      <div className="relative z-[1] flex h-9 w-9 items-center justify-center rounded-[12px] border border-border bg-surface shadow-[0_12px_28px_-24px_rgba(15,23,42,0.38)]">
                        <img
                          src="/logo.png"
                          alt="Jurisgentic AI"
                          className="logo-on-dark h-[18px] w-[18px] object-contain animate-ai-avatar-presence"
                        />
                      </div>
                    </div>
                    <div className="min-w-0 flex-1 rounded-[16px] rounded-tl-sm border border-border bg-surface px-[12px] py-[8px] text-[14px] leading-6 text-text-secondary shadow-[0_14px_34px_-28px_rgba(91,33,182,0.14)]">
                      <p className="whitespace-pre-wrap break-words text-[14px] leading-6 text-text-secondary">
                        {streamedResponse}
                      </p>
                      <span className="ml-0.5 inline-block animate-pulse text-app-accent-text">
                        ▋
                      </span>
                    </div>
                  </div>
                </div>
              ) : null}

              {actionError && !isActionLoading ? (
                <p className="mb-2 rounded-lg border border-app-danger/40 bg-app-danger-soft/40 px-3 py-2 text-sm leading-relaxed text-app-danger-text">
                  {actionError}
                </p>
              ) : null}
            </div>

            {suggestedActions.length > 0 ? (
              <div
                ref={suggestionScrollRef}
                className="hide-scrollbar cursor-grab overflow-x-auto px-0.5 active:cursor-grabbing"
                onMouseDown={handleSuggestionsMouseDown}
                onMouseMove={handleSuggestionsMouseMove}
                onMouseUp={handleSuggestionsMouseUp}
                onMouseLeave={handleSuggestionsMouseUp}
              >
                <div className="flex w-max items-center gap-1.5">
                  {suggestedActions.map((action) => (
                    <button
                      key={action}
                      type="button"
                      onClick={() => {
                        if (suggestionDragRef.current.moved) {
                          suggestionDragRef.current.moved = false;
                          return;
                        }
                        void sendInsightsChatMessage(action);
                      }}
                      disabled={isBusy}
                      className="whitespace-nowrap rounded-full border border-border/70 bg-surface px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <form
              onSubmit={handleSubmitChat}
              className="relative rounded-[24px] border border-border/70 bg-surface-muted/80 px-1 py-0.5 transition-colors focus-within:border-app-accent/45"
            >
              <textarea
                ref={chatTextareaRef}
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                onKeyDown={handleChatInputKeyDown}
                rows={1}
                placeholder="Ask AI about this dashboard..."
                className="block w-full resize-none rounded-[22px] border-0 bg-transparent px-4 py-2 pr-10 text-sm text-text placeholder:text-subtle transition-all duration-200 focus:outline-none disabled:cursor-not-allowed disabled:opacity-70"
                style={{
                  minHeight: '36px',
                  maxHeight: '88px',
                  scrollbarWidth: 'thin',
                  scrollbarColor: 'var(--app-border-strong) transparent',
                }}
              />
              <button
                type="submit"
                disabled={!chatInput.trim() || isBusy}
                aria-label="Send message"
                className="absolute bottom-1 right-1 inline-flex h-8 w-8 items-center justify-center rounded-full bg-app-accent text-white shadow-[0_8px_20px_rgba(79,70,229,0.28)] transition-colors hover:brightness-95 disabled:cursor-not-allowed disabled:bg-app-accent/55 disabled:shadow-none"
              >
                {isBusy ? (
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"
                    />
                  </svg>
                ) : (
                  <svg
                    className="h-4 w-4 rotate-90"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                    />
                  </svg>
                )}
              </button>
            </form>
          </div>
        </section>
      ) : null}
    </div>
  );
};
