/** Wire types for /api/v2/core/case-inbox.
 *  Keep in sync with bkdrafts-be/src/core/components/case_inbox/schemas.py. */

export type SsnExtractionStatus = 'found' | 'not_found' | 'scanned_image';

export type CaseInboxStatus =
  | 'ingesting'
  | 'ready'
  | 'accepted'
  | 'archived'
  | 'failed_ingest';

/** Nested summary of the matched unfiled case, embedded on inbox entries
 *  that the matcher flagged. Renders the "Existing unfiled case found"
 *  heads-up block in the Accept/Reject modals. */
export interface MatchedUnfiledCaseSummary {
  id: string;
  case_name: string;
  ssn_last4: string | null;
  created_at: string; // ISO datetime
}

export interface CaseInboxEntry {
  id: string;
  case_number: string | null;
  case_name: string | null;
  ssn_last4: string | null;
  ssn_extraction_status: SsnExtractionStatus;
  court_district: string | null;
  status: CaseInboxStatus;
  source: string;
  received_at: string | null; // ISO datetime
  created_at: string;
  archived_at: string | null;
  /** NULL when archived by the cron timeout; populated when a user
   *  explicitly clicked Dismiss. UI uses this to render
   *  "timed out Xd ago" vs "dismissed by Maria Xh ago". */
  dismissed_by_user_id: string | null;
  /** Presigned R2 URL, 1h TTL. Re-signed on every list response. */
  petition_pdf_url: string | null;
  /** Phase 2 unfiled-petition match. Populated at ingest time; re-
   *  evaluated at accept/dismiss time. When non-null, the modal shows
   *  a heads-up that this notice will merge into the matched case. */
  matches_unfiled_case_id: string | null;
  matched_unfiled_case: MatchedUnfiledCaseSummary | null;
}

/** Minimal case row returned alongside an inbox action when a merge
 *  happened (Accept-merge or Reject-merge). Drives the outcome-aware
 *  toast on the inbox page. */
export interface MergedCaseSummary {
  id: string;
  case_name: string;
  case_number: string | null;
}

export interface CaseInboxListResponse {
  entries: CaseInboxEntry[];
}

export interface CaseInboxDismissResponse {
  ok: boolean;
  id: string;
  /** Populated only on the Phase 2 reject-with-merge path. NULL when
   *  the inbox row had no matching unfiled counterpart (pure-archive). */
  case: MergedCaseSummary | null;
}
