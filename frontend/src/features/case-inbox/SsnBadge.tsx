import React from 'react';

import type { CaseInboxEntry } from '@/types/case-inbox';

export const SsnBadge: React.FC<{ entry: CaseInboxEntry }> = ({ entry }) => {
  if (entry.ssn_extraction_status === 'found' && entry.ssn_last4) {
    return (
      <span
        className="font-mono text-xs tabular-nums text-text-secondary"
        title="Extracted from PDF text"
      >
        ••••{entry.ssn_last4}
      </span>
    );
  }
  if (entry.ssn_extraction_status === 'scanned_image') {
    return (
      <span
        className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
        title="Image-only PDF — review manually after Accept"
      >
        Scanned PDF
      </span>
    );
  }
  return (
    <span className="text-xs text-muted" title="Not in PDF text">
      —
    </span>
  );
};
