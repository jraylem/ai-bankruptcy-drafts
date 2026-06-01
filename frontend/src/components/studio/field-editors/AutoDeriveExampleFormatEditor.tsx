import React, { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import type { TemplateVariable } from '@/types/studio';

interface AutoDeriveExampleFormatEditorProps {
  children: TemplateVariable[];
  value: string;
  onChange: (composed: string) => void;
}

const PRESET_SEPARATORS: { label: string; value: string }[] = [
  { label: '–', value: ' - ' },
  { label: '|', value: ' | ' },
  { label: ',', value: ', ' },
  { label: ':', value: ': ' },
];
const DEFAULT_SEPARATOR = ' - ';

interface ParsedFormat {
  order: string[];
  separator: string;
}

const parseExisting = (value: string, children: TemplateVariable[]): ParsedFormat => {
  const declaredOrder = children.map((c) => c.template_variable);
  if (!value) {
    return { order: declaredOrder, separator: DEFAULT_SEPARATOR };
  }

  const positioned: { templateVariable: string; index: number; markerLength: number }[] = [];
  for (const child of children) {
    const marker = child.template_property_marker ?? '';
    if (!marker) continue;
    const idx = value.indexOf(marker);
    if (idx === -1) continue;
    positioned.push({
      templateVariable: child.template_variable,
      index: idx,
      markerLength: marker.length,
    });
  }
  if (positioned.length === 0) {
    return { order: declaredOrder, separator: DEFAULT_SEPARATOR };
  }
  positioned.sort((a, b) => a.index - b.index);

  const recoveredOrder = positioned.map((p) => p.templateVariable);
  for (const child of declaredOrder) {
    if (!recoveredOrder.includes(child)) recoveredOrder.push(child);
  }

  let separator = DEFAULT_SEPARATOR;
  if (positioned.length >= 2) {
    const first = positioned[0]!;
    const second = positioned[1]!;
    const between = value.slice(first.index + first.markerLength, second.index);
    if (between) separator = between;
  }

  return { order: recoveredOrder, separator };
};

const composeFormat = (
  order: string[],
  separator: string,
  children: TemplateVariable[]
): string => {
  const byName = new Map(children.map((c) => [c.template_variable, c]));
  return order
    .map((name) => byName.get(name)?.template_property_marker ?? '')
    .filter((segment) => segment.length > 0)
    .join(separator);
};

export const AutoDeriveExampleFormatEditor = ({
  children,
  value,
  onChange,
}: AutoDeriveExampleFormatEditorProps): ReactElement => {
  const [order, setOrder] = useState<string[]>(() => parseExisting(value, children).order);
  const [separator, setSeparator] = useState<string>(
    () => parseExisting(value, children).separator
  );
  const [isCustomSeparator, setIsCustomSeparator] = useState<boolean>(
    () => !PRESET_SEPARATORS.some((p) => p.value === parseExisting(value, children).separator)
  );

  const [liftedIndex, setLiftedIndex] = useState<number | null>(null);
  const dragSourceRef = useRef<number | null>(null);

  const childByName = useMemo(
    () => new Map(children.map((c) => [c.template_variable, c])),
    [children]
  );

  const composed = useMemo(
    () => composeFormat(order, separator, children),
    [order, separator, children]
  );

  const lastEmittedRef = useRef<string | null>(null);
  useEffect(() => {
    if (composed === lastEmittedRef.current) return;
    if (composed === value) {
      lastEmittedRef.current = composed;
      return;
    }
    lastEmittedRef.current = composed;
    onChange(composed);
  }, [composed, value, onChange]);

  useEffect(() => {
    setOrder((prev) => {
      const known = new Set(children.map((c) => c.template_variable));
      const filtered = prev.filter((n) => known.has(n));
      const declaredOrder = children.map((c) => c.template_variable);
      for (const name of declaredOrder) {
        if (!filtered.includes(name)) filtered.push(name);
      }
      return filtered;
    });
  }, [children]);

  const movePill = (from: number, to: number): void => {
    if (from === to || from < 0 || to < 0) return;
    setOrder((prev) => {
      if (from >= prev.length || to >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved!);
      return next;
    });
  };

  const handleDragStart = (idx: number) => (e: React.DragEvent): void => {
    dragSourceRef.current = idx;
    e.dataTransfer.effectAllowed = 'move';
    
    e.dataTransfer.setData('text/plain', String(idx));
  };
  const handleDragOver = (e: React.DragEvent): void => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };
  const handleDrop = (idx: number) => (e: React.DragEvent): void => {
    e.preventDefault();
    const from = dragSourceRef.current;
    dragSourceRef.current = null;
    if (from === null) return;
    movePill(from, idx);
  };

  const handlePillKeyDown = (idx: number) => (e: React.KeyboardEvent): void => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      if (liftedIndex === null) {
        setLiftedIndex(idx);
      } else {
        setLiftedIndex(null);
      }
      return;
    }
    if (e.key === 'Escape' && liftedIndex !== null) {
      e.preventDefault();
      setLiftedIndex(null);
      return;
    }
    if (liftedIndex === null) return;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const target = Math.max(0, liftedIndex - 1);
      movePill(liftedIndex, target);
      setLiftedIndex(target);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      const target = Math.min(order.length - 1, liftedIndex + 1);
      movePill(liftedIndex, target);
      setLiftedIndex(target);
    }
  };

  const hasMissingMarker = order.some(
    (name) => !(childByName.get(name)?.template_property_marker ?? '')
  );

  const segmentedClass = (active: boolean): string =>
    `rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
      active
        ? 'bg-app-accent text-white'
        : 'bg-surface text-text-secondary hover:bg-surface-muted'
    }`;

  return (
    <div className="space-y-3" data-testid="auto-derive-format-editor">
      <div className="rounded-lg border border-app-accent-soft bg-app-accent-soft/40 px-3 py-2 text-xs text-app-accent-text">
        Each pill is a slot. Reorder by dragging (or focus + Space + arrows).
        Markers shown are samples — runtime values come from the picked row.
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Separator
        </span>
        <div
          role="radiogroup"
          aria-label="Separator"
          className="flex gap-1 rounded-lg border border-border bg-surface-muted p-0.5"
        >
          {PRESET_SEPARATORS.map((p) => (
            <button
              key={p.value}
              type="button"
              role="radio"
              aria-checked={!isCustomSeparator && separator === p.value}
              onClick={() => {
                setIsCustomSeparator(false);
                setSeparator(p.value);
              }}
              className={segmentedClass(!isCustomSeparator && separator === p.value)}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            role="radio"
            aria-checked={isCustomSeparator}
            onClick={() => setIsCustomSeparator(true)}
            className={segmentedClass(isCustomSeparator)}
          >
            Custom
          </button>
        </div>
        {isCustomSeparator && (
          <input
            type="text"
            value={separator}
            onChange={(e) => setSeparator(e.target.value)}
            placeholder="e.g. — "
            className="w-32 rounded-md border border-border bg-surface px-2 py-1 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
        )}
      </div>

      <div
        data-testid="format-preview"
        className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface-muted/40 px-3 py-3"
      >
        {order.map((name, idx) => {
          const child = childByName.get(name);
          const marker = child?.template_property_marker ?? '';
          const missing = !marker;
          const isLifted = liftedIndex === idx;
          return (
            <React.Fragment key={name}>
              <span
                role="button"
                tabIndex={0}
                draggable
                aria-grabbed={isLifted}
                aria-label={`${name} — ${marker || 'no sample value'}. Press Space to lift, arrows to move.`}
                title={`${name} (drag or Space + arrows to reorder)`}
                onDragStart={handleDragStart(idx)}
                onDragOver={handleDragOver}
                onDrop={handleDrop(idx)}
                onKeyDown={handlePillKeyDown(idx)}
                data-testid={`format-pill-${name}`}
                className={`inline-flex cursor-grab select-none items-center gap-1 rounded-md border px-2 py-1 text-sm transition-shadow active:cursor-grabbing ${
                  missing
                    ? 'border-dashed border-app-warning-soft bg-app-warning-soft/40 text-app-warning-text'
                    : 'border-border bg-surface text-text-primary'
                } ${
                  isLifted
                    ? 'shadow-[0_0_0_2px_var(--color-app-accent)] ring-2 ring-app-accent ring-offset-1'
                    : 'hover:border-app-accent-soft'
                }`}
              >
                <span aria-hidden className="text-subtle">⋮⋮</span>
                <span className={missing ? 'italic' : ''}>
                  {missing ? `(${name}: no sample)` : marker}
                </span>
              </span>
              {idx < order.length - 1 && (
                <span aria-hidden className="select-none text-sm text-muted">
                  {separator}
                </span>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {hasMissingMarker && (
        <p className="text-xs text-app-warning-text">
          One or more children have no sample value. Set each child's marker (the exact
          text from the docx) before the format can fully cover them.
        </p>
      )}
    </div>
  );
};

export default AutoDeriveExampleFormatEditor;
