import { cn } from '@/utils';
import { PresentationShapeCard } from '../PresentationShapeCard';
import {
  AUTHOR_INPUT_KINDS,
  PRESENTATION_SHAPES,
  SOURCE_KINDS,
  type AuthorInputKind,
  type PresentationShape,
  type SourceKind,
} from '../types';

interface UserInputStepProps {
  source: SourceKind;
  presentationShape: PresentationShape;
  authorInputKind: AuthorInputKind | null;
  onChangePresentationShape: (shape: PresentationShape) => void;
  onChangeAuthorInputKind: (kind: AuthorInputKind) => void;
}

export const UserInputStep = ({
  source,
  presentationShape,
  authorInputKind,
  onChangePresentationShape,
  onChangeAuthorInputKind,
}: UserInputStepProps) => {
  if (source === 'author_input') {
    return (
      <div className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-text-secondary">
            How will you fill this in?
          </h3>
          <p className="mt-1 text-sm text-subtle">
            Pick how you'd like to enter the value when drafting the document.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          {AUTHOR_INPUT_KINDS.map((meta) => {
            const isSelected = authorInputKind === meta.key;
            return (
              <button
                key={meta.key}
                type="button"
                onClick={() => onChangeAuthorInputKind(meta.key)}
                className={cn(
                  'cursor-pointer rounded-xl border bg-surface p-4 text-left transition-all',
                  isSelected
                    ? 'border-app-accent shadow-sm ring-2 ring-app-accent/20'
                    : 'border-border hover:border-app-accent/40 hover:bg-surface-muted',
                )}
                aria-pressed={isSelected}
              >
                <p
                  className={cn(
                    'text-sm font-semibold',
                    isSelected ? 'text-app-accent-text' : 'text-text-secondary',
                  )}
                >
                  {meta.label}
                </p>
                <p className="mt-1 text-xs text-text-secondary">{meta.description}</p>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  const isRaw = presentationShape === 'raw';
  const sourceMeta = SOURCE_KINDS.find((s) => s.key === source);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-text-secondary">
          Will you choose the value when drafting?
        </h3>
        <p className="mt-1 text-sm text-subtle">
          If yes, pick how the agent should show you the choices.
        </p>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onChangePresentationShape('raw')}
          className={cn(
            'flex-1 cursor-pointer rounded-lg border px-4 py-2.5 text-sm font-semibold transition-colors',
            isRaw
              ? 'border-app-accent bg-app-accent text-white'
              : 'border-border bg-surface text-text-secondary hover:bg-surface-muted',
          )}
        >
          No — let the agent fill it in
        </button>
        <button
          type="button"
          onClick={() => onChangePresentationShape('dropdown')}
          className={cn(
            'flex-1 cursor-pointer rounded-lg border px-4 py-2.5 text-sm font-semibold transition-colors',
            !isRaw
              ? 'border-app-accent bg-app-accent text-white'
              : 'border-border bg-surface text-text-secondary hover:bg-surface-muted',
          )}
        >
          Yes — I'll pick
        </button>
      </div>

      {!isRaw && (
        <div className="space-y-2 pt-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-subtle">
            How should the choices be shown?
          </p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
            {PRESENTATION_SHAPES.filter((s) => {
              if (s.key === 'raw') return false;
              const allowed = sourceMeta?.allowedShapes;
              return allowed ? allowed.includes(s.key) : true;
            }).map((meta) => (
              <PresentationShapeCard
                key={meta.key}
                shape={meta.key}
                label={meta.label}
                description={meta.description}
                preview={meta.preview}
                isSelected={presentationShape === meta.key}
                onSelect={() => onChangePresentationShape(meta.key)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
