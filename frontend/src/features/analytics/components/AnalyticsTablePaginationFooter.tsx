import React, { useMemo } from 'react';
import { SelectDropdown } from '@/components/common';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import { getPaginationItems } from '@/features/analytics/utils/pagination.helpers';

interface AnalyticsTablePaginationFooterProps {
  page: number;
  totalPages: number;
  pageSize: number;
  pageSizeOptions: Array<{ label: string; value: string }>;
  onPageChange: (nextPage: number) => void;
  onPageSizeChange: (nextPageSize: number) => void;
  className?: string;
  keyPrefix?: string;
}

export const AnalyticsTablePaginationFooter: React.FC<AnalyticsTablePaginationFooterProps> = ({
  page,
  totalPages,
  pageSize,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
  className = '',
  keyPrefix = 'analytics-table-pagination',
}) => {
  const paginationItems = useMemo(() => getPaginationItems(page, totalPages), [page, totalPages]);

  return (
    <div className={`flex items-center justify-between gap-3 px-4 py-3 ${className}`}>
      <div className="flex items-center gap-2">
        <p className="text-xs text-muted">
          Page {formatAnalyticsNumber(page)} of {formatAnalyticsNumber(totalPages)}
        </p>
        <span className="text-xs text-subtle">•</span>
        <div className="min-w-[90px]">
          <SelectDropdown
            value={String(pageSize)}
            onChange={(value) => onPageSizeChange(Number(value))}
            options={pageSizeOptions}
            className="w-full"
            size="sm"
          />
        </div>
      </div>

      {totalPages > 1 ? (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="rounded-xl border border-border px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            Prev
          </button>
          {paginationItems.map((item, index) =>
            item === 'ellipsis' ? (
              <span key={`${keyPrefix}-ellipsis-${index}`} className="px-1 text-xs text-subtle">
                …
              </span>
            ) : (
              <button
                key={`${keyPrefix}-${item}`}
                type="button"
                onClick={() => onPageChange(item)}
                aria-current={item === page ? 'page' : undefined}
                className={`min-w-8 rounded-xl border px-2 py-1.5 text-xs font-medium transition ${
                  item === page
                    ? 'border-option-selected-ring bg-app-accent-soft text-app-accent-text'
                    : 'border-border text-text-secondary hover:bg-surface-muted'
                }`}
              >
                {formatAnalyticsNumber(item)}
              </button>
            )
          )}
          <button
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="rounded-xl border border-border px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
};
