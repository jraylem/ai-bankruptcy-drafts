const configuredApiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const API_BASE_URL = import.meta.env.DEV ? '' : configuredApiUrl;
export const APP_NAME = import.meta.env.VITE_APP_NAME || 'Jurisgentic';

export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: '/api/auth/login',
    REGISTER: '/api/auth/register',
    LOGOUT: '/api/auth/logout',
    ME: '/api/auth/me',
    REFRESH: '/api/auth/refresh',
    VERIFY_EMAIL: '/api/auth/verify-email',
    RESEND_VERIFICATION: '/api/auth/resend-verification',
    USER_APPROVAL: (token: string) => `/api/auth/user-approval/${encodeURIComponent(token)}`,
  },
  BILLING: {
    CHECKOUT: '/api/billing/checkout',
    COST_DRIVERS: '/api/billing/cost-drivers',
    INVOICES: '/api/billing/invoices',
    OVERVIEW: '/api/billing/overview',
    PAYMENT_METHOD: '/api/billing/payment-method',
    PLANS: '/api/billing/plans',
    PORTAL: '/api/billing/portal',
    SUBSCRIPTION: '/api/billing/subscription',
    USAGE_BREAKDOWN: '/api/billing/usage-breakdown',
  },
  FIRMS: {
    ME: '/api/firms/me',
    MEMBERS: '/api/firms/members',
    MEMBER: (userId: string) => `/api/firms/members/${encodeURIComponent(userId)}`,
    MEMBER_PERMISSIONS: (userId: string) =>
      `/api/firms/members/${encodeURIComponent(userId)}/permissions`,
    INVITE: '/api/firms/invite',
    ACCEPT_INVITE: '/api/firms/invite/accept',
    ONBOARDING_STATUS: '/api/firms/onboarding-status',
  },
  SETTINGS: {
    USER: '/api/settings/user',
    FIRM: '/api/settings/firm',
    PERMISSIONS: '/api/settings/permissions',
    PASSWORD: '/api/settings/password',
    BILLING_SUMMARY: '/api/settings/billing-summary',
    FIRM_ACTIVITY: '/api/settings/firm/activity',
    FIRM_INVITATIONS: '/api/settings/firm/invitations',
    FIRM_MEMBER_ROLE: (userId: string) =>
      `/api/settings/firm/members/${encodeURIComponent(userId)}/role`,
    SECURITY_SESSIONS: '/api/settings/security/sessions',
    SECURITY_SESSIONS_REVOKE_ALL: '/api/settings/security/sessions/revoke-all',
    SECURITY_SESSION: (sessionId: string) =>
      `/api/settings/security/sessions/${encodeURIComponent(sessionId)}`,
    SECURITY_2FA: '/api/settings/security/2fa',
    FIRM_INVITATION: (invitationId: string) =>
      `/api/settings/firm/invitations/${encodeURIComponent(invitationId)}`,
    RESEND_FIRM_INVITATION: (invitationId: string) =>
      `/api/settings/firm/invitations/${encodeURIComponent(invitationId)}/resend`,
  },
  DASHBOARD: {
    CASES: '/api/dashboard/cases',
    USERS: '/api/dashboard/users',
    MOTIONS: '/api/dashboard/motions',
    EXPORT: {
      USERS: '/api/dashboard/export/export/users',
      USER: (userId: string) => `/api/dashboard/export/export/users/${encodeURIComponent(userId)}`,
    },
    ANALYTICS: {
      USERS: '/api/dashboard/analytics/users',
      USER_DETAIL: (userId: string) =>
        `/api/dashboard/analytics/users/${encodeURIComponent(userId)}`,
      CASES: '/api/dashboard/analytics/cases',
      CASE_DETAIL: (sessionId: string) => `/api/dashboard/analytics/cases/${sessionId}`,
      MOTIONS: '/api/dashboard/analytics/motions',
      INSIGHTS: '/api/dashboard/analytics/insights',
      INSIGHTS_EXPLAIN: '/api/dashboard/analytics/insights/explain',
      INSIGHTS_CHAT: '/api/dashboard/analytics/insights/chat',
      INSIGHTS_CHAT_STREAM: '/api/dashboard/analytics/insights/chat/stream',
      MOTION_SESSION_DETAIL: (sessionId: string) =>
        `/api/dashboard/analytics/motions/sessions/${sessionId}`,
    },
    ACTIVITY: {
      FEED: '/api/dashboard/activity/feed',
      LOG: '/api/dashboard/activity-log',
      ACTIONS: '/api/dashboard/activity-log/actions',
    },
    SYSTEM: {
      STATUS: '/api/dashboard/system/status',
    },
    KPIS: {
      API_CALLS: '/api/dashboard/kpis/api-calls',
    },
    CHARTS: {
      MOTIONS_DAILY: '/api/dashboard/charts/motions-daily',
      CASES_DAILY: '/api/dashboard/charts/cases-daily',
      USERS_DAILY: '/api/dashboard/charts/users-daily',
      MOTIONS_BY_TYPE: '/api/dashboard/charts/motions-by-type',
    },
  },
  PDF: {
    UPLOAD: '/api/upload-pdf',
    DELETE_FROM_SESSION: (sessionId: string) => `/api/sessions/${sessionId}/pdfs`,
    LIST_BY_SESSION: (sessionId: string) => `/api/sessions/${sessionId}/pdfs`,
    DOWNLOAD: (pdfId: string) => `/api/pdf/${pdfId}/download`,
  },
  CORE: {
    CASES: '/api/v2/core/cases',
    CASES_EXTRACT_BY_NUMBER: '/api/v2/core/cases/extract-by-number',
    CASE_BY_ID: (caseId: string) => `/api/v2/core/cases/${encodeURIComponent(caseId)}`,
    CASE_PETITION_URL: (caseId: string) =>
      `/api/v2/core/cases/${encodeURIComponent(caseId)}/petition-url`,
    TEMPLATES: '/api/v2/core/template',
    TEMPLATE_BY_ID: (templateId: string) =>
      `/api/v2/core/template/${encodeURIComponent(templateId)}`,
    TEMPLATE_BUNDLING_CONFIG: (templateId: string) =>
      `/api/v2/core/template/${encodeURIComponent(templateId)}/bundling-config`,
    TEMPLATE_CONNECTORS: '/api/v2/core/template/connectors',
    TEMPLATE_REFERENCE_DATA: '/api/v2/core/template/reference-data',
    TEMPLATE_REFERENCE_DATA_BY_CODE: (shortCode: string) =>
      `/api/v2/core/template/reference-data/${encodeURIComponent(shortCode)}`,
    ATTORNEYS: '/api/v2/core/attorneys',
    ATTORNEY_BY_ID: (attorneyId: string) =>
      `/api/v2/core/attorneys/${encodeURIComponent(attorneyId)}`,
    TEMPLATE_COMPOSER_PARSE: '/api/v2/core/template/composer/parse',
    TEMPLATE_COMPOSER_GENERATE: (templateName: string) =>
      `/api/v2/core/template/composer/generate-template?template_name=${encodeURIComponent(templateName)}`,
    TEMPLATE_COMPOSER_COMPOSE_AGENT_CONFIG: (templateId: string) =>
      `/api/v2/core/template/composer/compose-agent-config?template_id=${encodeURIComponent(templateId)}`,
    TEMPLATE_COMPOSER_REGENERATE: (templateId: string) =>
      `/api/v2/core/template/composer/regenerate-template/${encodeURIComponent(templateId)}`,
    TEMPLATE_DRY_RUN: '/api/v2/core/template/dry-run',
    TEMPLATE_DRY_RUN_RESUME: '/api/v2/core/template/dry-run/resume',
    CASE_SUPPORTING_DOCS: (caseId: string) =>
      `/api/v2/core/cases/${encodeURIComponent(caseId)}/supporting-docs`,
    DRAFT: '/api/v2/core/draft',
    DRAFT_RESUME: '/api/v2/core/draft/resume',
    COSTS_SUMMARY: '/api/v2/core/costs/summary',
    CASE_INBOX_LIST: '/api/v2/core/case-inbox/list',
    CASE_INBOX_ARCHIVED: '/api/v2/core/case-inbox/archived',
    CASE_INBOX_ACCEPT: (id: string) =>
      `/api/v2/core/case-inbox/${encodeURIComponent(id)}/accept`,
    CASE_INBOX_DISMISS: (id: string) =>
      `/api/v2/core/case-inbox/${encodeURIComponent(id)}/dismiss`,
  },
  PLEADING_V2: {
    START: '/api/v2/core/pleading/start',
    SUBMIT_INPUT: (taskId: string) =>
      `/api/v2/core/pleading/${encodeURIComponent(taskId)}/submit-input`,
    USE_EXISTING: (taskId: string) =>
      `/api/v2/core/pleading/${encodeURIComponent(taskId)}/use-existing`,
    REGENERATE: (taskId: string) =>
      `/api/v2/core/pleading/${encodeURIComponent(taskId)}/regenerate`,
    CANCEL: (taskId: string) =>
      `/api/v2/core/pleading/${encodeURIComponent(taskId)}/cancel`,
    DISMISS: (taskId: string) =>
      `/api/v2/core/pleading/${encodeURIComponent(taskId)}`,
    TASKS: '/api/v2/core/pleading/tasks',
    TASK_BY_ID: (taskId: string) =>
      `/api/v2/core/pleading/${encodeURIComponent(taskId)}`,
    EVENTS: '/api/v2/core/pleading/events',
    CASE_GENERATION_LOGS: '/api/v2/core/pleading/case-generation-logs',
    CASE_GENERATION_LOG_DOWNLOAD: (logId: string) =>
      `/api/v2/core/pleading/case-generation-logs/${encodeURIComponent(logId)}/download-url`,
    CASE_GENERATION_LOG_DOWNLOAD_PDF: (logId: string) =>
      `/api/v2/core/pleading/case-generation-logs/${encodeURIComponent(logId)}/download-pdf`,
    CASE_GENERATION_LOG_AUTOSAVE: (logId: string) =>
      `/api/v2/core/pleading/case-generation-logs/${encodeURIComponent(logId)}/docx`,
  },
  CHAT_V2: {
    SESSION_GET_OR_CREATE: '/api/v2/core/chat/sessions/get-or-create',
    SESSION_MESSAGES: (sessionId: string) =>
      `/api/v2/core/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    SESSION_STREAM: (sessionId: string) =>
      `/api/v2/core/chat/sessions/${encodeURIComponent(sessionId)}/stream`,
    SESSION_DELETE: (sessionId: string) =>
      `/api/v2/core/chat/sessions/${encodeURIComponent(sessionId)}`,
  },
  STUDIO_V2: {
    // Composer flow
    COMPOSER_PARSE: '/api/v3/studio/composer/parse',
    COMPOSER_GENERATE: '/api/v3/studio/composer/generate-template',
    COMPOSER_REGENERATE: (templateId: string) =>
      `/api/v3/studio/templates/${encodeURIComponent(templateId)}/composer/regenerate-template`,
    // Template CRUD
    TEMPLATES: '/api/v3/studio/templates',
    TEMPLATE_BY_ID: (templateId: string) =>
      `/api/v3/studio/templates/${encodeURIComponent(templateId)}`,
    TEMPLATE_FIELD_PATCH: (templateId: string, fieldId: string) =>
      `/api/v3/studio/templates/${encodeURIComponent(templateId)}/fields/${encodeURIComponent(fieldId)}`,
    TEMPLATE_BUNDLING_CONFIG: (templateId: string) =>
      `/api/v3/studio/templates/${encodeURIComponent(templateId)}/bundling-config`,
    // Dry-run (Phase 2)
    DRY_RUN: (templateId: string) =>
      `/api/v3/studio/templates/${encodeURIComponent(templateId)}/dry-run`,
    DRY_RUN_RESUME: (templateId: string) =>
      `/api/v3/studio/templates/${encodeURIComponent(templateId)}/dry-run/resume`,
    // Publish (Phase 3 — slice 3A)
    TEMPLATE_PUBLISH: (templateId: string) =>
      `/api/v3/studio/templates/${encodeURIComponent(templateId)}/publish`,
    // Composer-async (Phase 2.6A) — Taskiq + Redis state + per-user SSE
    // to keep template upload + regenerate off the synchronous request
    // path (prod 504s when TemplateAgentV2 takes >30s).
    COMPOSER_ASYNC_GENERATE: '/api/v3/studio/composer-async/generate',
    COMPOSER_ASYNC_REGENERATE: '/api/v3/studio/composer-async/regenerate',
    COMPOSER_ASYNC_TASKS: '/api/v3/studio/composer-async/tasks',
    COMPOSER_ASYNC_TASK_BY_ID: (taskId: string) =>
      `/api/v3/studio/composer-async/tasks/${encodeURIComponent(taskId)}`,
    COMPOSER_ASYNC_CANCEL: (taskId: string) =>
      `/api/v3/studio/composer-async/${encodeURIComponent(taskId)}/cancel`,
    COMPOSER_ASYNC_DISMISS: (taskId: string) =>
      `/api/v3/studio/composer-async/${encodeURIComponent(taskId)}`,
    COMPOSER_ASYNC_EVENTS: '/api/v3/studio/composer-async/events',
    // Dry-run-async (Phase 3 — slice 3C) — Taskiq + Redis state + per-user SSE
    // so paralegals can fire multiple dry-runs in parallel without
    // blocking the studio page. Mirrors composer-async architecture
    // with pause/resume protocol layered on top (AWAITING_INPUT →
    // /submit-input → RESUMING → COMPLETED).
    DRY_RUN_ASYNC_START: '/api/v3/studio/dry-run-async/start',
    DRY_RUN_ASYNC_SUBMIT_INPUT: (taskId: string) =>
      `/api/v3/studio/dry-run-async/${encodeURIComponent(taskId)}/submit-input`,
    DRY_RUN_ASYNC_CANCEL: (taskId: string) =>
      `/api/v3/studio/dry-run-async/${encodeURIComponent(taskId)}/cancel`,
    DRY_RUN_ASYNC_DISMISS: (taskId: string) =>
      `/api/v3/studio/dry-run-async/${encodeURIComponent(taskId)}`,
    DRY_RUN_ASYNC_TASKS: '/api/v3/studio/dry-run-async/tasks',
    DRY_RUN_ASYNC_TASK_BY_ID: (taskId: string) =>
      `/api/v3/studio/dry-run-async/tasks/${encodeURIComponent(taskId)}`,
    DRY_RUN_ASYNC_EVENTS: '/api/v3/studio/dry-run-async/events',
  },
} as const;

export const PDF_CONFIG = {
  MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
  ALLOWED_TYPES: ['application/pdf'],
  DEFAULT_SCALE: 1.0,
  MIN_SCALE: 0.5,
  MAX_SCALE: 3.0,
  SCALE_STEP: 0.25,
} as const;

export const STORAGE_KEYS = {
  THEME: 'theme',
} as const;

export const MESSAGE_ROLES = {
  USER: 'user',
  ASSISTANT: 'assistant',
  SYSTEM: 'system',
} as const;
