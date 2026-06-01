import { FiArrowDown, FiArrowUp, FiChevronDown } from 'react-icons/fi';

export interface SortableHeaderProps<TSortKey extends string> {
  label: string;
  sortKey: TSortKey;
  activeSortKey: TSortKey;
  sortDir: 'asc' | 'desc';
  onToggle: (nextSortKey: TSortKey) => void;
  className?: string;
}

const renderSortIcon = (isActive: boolean, dir: 'asc' | 'desc') => {
  if (!isActive) {
    return <FiChevronDown className="h-3.5 w-3.5 text-subtle/70" />;
  }
  if (dir === 'asc') {
    return <FiArrowUp className="h-3.5 w-3.5 text-app-accent" />;
  }
  return <FiArrowDown className="h-3.5 w-3.5 text-app-accent" />;
};

export const SortableHeader = <TSortKey extends string>({
  label,
  sortKey,
  activeSortKey,
  sortDir,
  onToggle,
  className = '',
}: SortableHeaderProps<TSortKey>) => {
  const isActive = activeSortKey === sortKey;

  return (
    <button
      type="button"
      onClick={() => onToggle(sortKey)}
      aria-label={`Sort by ${label}${isActive ? ` (${sortDir})` : ''}`}
      className={`inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted transition-colors hover:text-text ${className}`}
    >
      <span>{label}</span>
      {renderSortIcon(isActive, sortDir)}
    </button>
  );
};
