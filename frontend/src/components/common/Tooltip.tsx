import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

type TooltipSide = 'top' | 'bottom' | 'left' | 'right';

interface TooltipProps {
  label: React.ReactNode;
  side?: TooltipSide;
  delayMs?: number;
  className?: string;
  children: React.ReactNode;
}

const ARROW_CLASSES: Record<TooltipSide, string> = {
  top: 'left-1/2 top-full -translate-x-1/2 border-x-transparent border-b-transparent border-t-gray-900 dark:border-t-slate-100',
  bottom: 'left-1/2 bottom-full -translate-x-1/2 border-x-transparent border-t-transparent border-b-gray-900 dark:border-b-slate-100',
  left: 'top-1/2 left-full -translate-y-1/2 border-y-transparent border-r-transparent border-l-gray-900 dark:border-l-slate-100',
  right: 'top-1/2 right-full -translate-y-1/2 border-y-transparent border-l-transparent border-r-gray-900 dark:border-r-slate-100',
};

const GAP_PX = 6;

interface AnchorPos {
  top: number;
  left: number;
  transform: string;
}

const computeAnchor = (rect: DOMRect, side: TooltipSide): AnchorPos => {
  switch (side) {
    case 'top':
      return {
        top: rect.top - GAP_PX,
        left: rect.left + rect.width / 2,
        transform: 'translate(-50%, -100%)',
      };
    case 'bottom':
      return {
        top: rect.bottom + GAP_PX,
        left: rect.left + rect.width / 2,
        transform: 'translate(-50%, 0)',
      };
    case 'left':
      return {
        top: rect.top + rect.height / 2,
        left: rect.left - GAP_PX,
        transform: 'translate(-100%, -50%)',
      };
    case 'right':
      return {
        top: rect.top + rect.height / 2,
        left: rect.right + GAP_PX,
        transform: 'translate(0, -50%)',
      };
  }
};

/**
 * Hover/focus tooltip. Portals to <body> with fixed positioning so it
 * escapes any `overflow-hidden` ancestor and never clips behind sibling
 * stacking contexts.
 */
export const Tooltip: React.FC<TooltipProps> = ({
  label,
  side = 'top',
  delayMs = 200,
  className = '',
  children,
}) => {
  const [isVisible, setIsVisible] = useState<boolean>(false);
  const [anchor, setAnchor] = useState<AnchorPos | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const timerRef = useRef<number | null>(null);
  const tooltipId = useId();

  const clearTimer = (): void => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const updateAnchor = (): void => {
    const node = triggerRef.current;
    if (!node) return;
    setAnchor(computeAnchor(node.getBoundingClientRect(), side));
  };

  const show = (): void => {
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      updateAnchor();
      setIsVisible(true);
    }, delayMs);
  };

  const hide = (): void => {
    clearTimer();
    setIsVisible(false);
  };

  useEffect(() => {
    if (!isVisible) return;
    const handler = (): void => updateAnchor();
    window.addEventListener('scroll', handler, true);
    window.addEventListener('resize', handler);
    return () => {
      window.removeEventListener('scroll', handler, true);
      window.removeEventListener('resize', handler);
    };
  }, [isVisible, side]);

  return (
    <>
      <span
        ref={triggerRef}
        className={`relative inline-flex ${className}`}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        aria-describedby={isVisible ? tooltipId : undefined}
      >
        {children}
      </span>
      {isVisible && anchor && typeof document !== 'undefined'
        ? createPortal(
            <span
              role="tooltip"
              id={tooltipId}
              style={{
                position: 'fixed',
                top: anchor.top,
                left: anchor.left,
                transform: anchor.transform,
              }}
              className="pointer-events-none z-[100] w-max max-w-[min(20rem,calc(100vw-1rem))] rounded-md bg-gray-900 px-2.5 py-1.5 text-[11px] font-medium leading-snug text-white shadow-lg ring-1 ring-black/5 dark:bg-slate-100 dark:text-slate-900 dark:ring-white/10 [overflow-wrap:anywhere] [text-wrap:pretty]"
            >
              {label}
              <span className={`absolute h-0 w-0 border-4 ${ARROW_CLASSES[side]}`} aria-hidden="true" />
            </span>,
            document.body,
          )
        : null}
    </>
  );
};

export default Tooltip;
