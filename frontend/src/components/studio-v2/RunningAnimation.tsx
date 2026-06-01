import { useEffect, useState } from 'react';
import Lottie from 'lottie-react';
import dryRunAnimation from '@/assets/lottie/dry-run.json';
import { cn } from '@/utils';

export type RunningPhase = 'initial' | 'finalizing' | 're_reading' | 'loading_document';

interface RunningAnimationProps {
  phase: RunningPhase;
  caseLabel?: string | null;
  /**
   * Controls Lottie size + heading scale. Use `xl` in the full-screen
   * overlay (initial dry-run) and `md` inside the awaiting-input modal
   * (resume / finalize stage).
   */
  size?: 'md' | 'xl';
}

// Phrase sets per phase — keeps the language honest about which
// step of the pipeline we're in. Initial runs may pause for picks;
// finalize runs go all the way to a rendered docx.
const PHRASE_SETS: Record<RunningPhase, Array<[string, string]>> = {
  initial: [
    ['Resolving', 'the fields'],
    ['Fetching', 'the sources'],
    ['Cross-referencing', 'the record'],
    ['Querying', 'the docket'],
    ['Construing', 'the statute'],
    ['Marshalling', 'the evidence'],
    ['Stipulating', 'the facts'],
    ['Annotating', 'the margins'],
    ['Filing', 'the caption'],
    ['Compiling', 'the brief'],
  ],
  finalizing: [
    ['Stitching', 'your picks in'],
    ['Healing', 'the prose'],
    ['Normalizing', 'every date'],
    ['Polishing', 'the language'],
    ['Filling', 'the placeholders'],
    ['Assembling', 'the document'],
    ['Reviewing', 'the draft'],
    ['Rendering', 'the final doc'],
    ['Certifying', 'the signature'],
  ],
  re_reading: [
    ['Re-reading', 'the document'],
    ['Re-applying', 'your corrections'],
    ['Detecting', 'variables'],
    ['Splitting', 'the captions'],
    ['Merging', 'grouped fields'],
    ['Skipping', 'your ignored text'],
    ['Mapping', 'to firm constants'],
    ['Suggesting', 'sources'],
    ['Rebuilding', 'the spec'],
  ],
  loading_document: [
    ['Fetching', 'the document'],
    ['Loading', 'the editor'],
    ['Reading', 'the file'],
    ['Opening', 'your draft'],
    ['Preparing', 'the viewer'],
    ['Rendering', 'the pages'],
  ],
};

const HEADING_TEXT: Record<RunningPhase, string> = {
  initial: 'Running the dry-run agent',
  finalizing: 'Finalizing the draft',
  re_reading: 'Re-reading the template',
  loading_document: 'Loading the document',
};

const SUBLINE_TEXT: Record<RunningPhase, string> = {
  initial: 'Reading sources, extracting candidates, and resolving every field.',
  finalizing: 'Healing your picks, filling placeholders, and rendering the document.',
  re_reading: 'Re-running the extraction agent with your skips, groups, and instruction applied.',
  loading_document: 'Fetching the file and warming up the editor.',
};

/**
 * Shared "we're working" Lottie + rotating verb-phrase view. Used:
 *   - Full-screen overlay during the initial dry-run pause window
 *     (see DryRunRunningOverlay).
 *   - In-modal hero during the resume / finalize phase (see
 *     AwaitingInputModalV2's `busy` branch) so the paralegal sees
 *     something is happening between "Finish & render" and the
 *     Draft tab appearing.
 */
export const RunningAnimation = ({
  phase,
  caseLabel,
  size = 'xl',
}: RunningAnimationProps) => {
  const phrases = PHRASE_SETS[phase];
  const [phraseIndex, setPhraseIndex] = useState<number>(0);

  useEffect(() => {
    setPhraseIndex(0);
    const id = window.setInterval(() => {
      setPhraseIndex((i) => (i + 1) % phrases.length);
    }, 1800);
    return () => window.clearInterval(id);
  }, [phrases]);

  const suffix = caseLabel ? ` for ${caseLabel}` : '';
  const sublineSuffix = caseLabel ? ` Working against ${caseLabel}.` : '';

  return (
    <div className="flex flex-col items-center gap-4">
      <Lottie
        animationData={dryRunAnimation}
        loop
        autoplay
        className={cn(
          'w-full',
          size === 'xl' ? 'h-64' : 'h-44',
        )}
      />
      <p
        key={phraseIndex}
        className={cn(
          'animate-verb-in text-center font-semibold text-text-secondary',
          size === 'xl' ? 'text-xl' : 'text-base sm:text-lg',
        )}
      >
        {phrases[phraseIndex][0]} {phrases[phraseIndex][1]}
        {suffix}…
      </p>
      <p
        className={cn(
          'max-w-sm text-center text-muted',
          size === 'xl' ? 'text-sm' : 'text-xs sm:text-sm',
        )}
      >
        {HEADING_TEXT[phase]}.{sublineSuffix} {SUBLINE_TEXT[phase]}
      </p>
    </div>
  );
};
