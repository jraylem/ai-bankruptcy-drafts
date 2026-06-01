import { SourceCard } from '../SourceCard';
import { SOURCE_KINDS, type SourceKind } from '../types';

interface SourceStepProps {
  selectedSource: SourceKind;
  onSelectSource: (source: SourceKind) => void;
}

export const SourceStep = ({ selectedSource, onSelectSource }: SourceStepProps) => (
  <div className="space-y-4">
    <div>
      <h3 className="text-base font-semibold text-text-secondary">
        Where does this value come from?
      </h3>
      <p className="mt-1 text-sm text-subtle">
        Pick where the agent should look to fill in this field.
      </p>
    </div>
    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
      {SOURCE_KINDS.map((meta) => (
        <SourceCard
          key={meta.key}
          source={meta.key}
          label={meta.label}
          description={meta.description}
          example={meta.example}
          isSelected={selectedSource === meta.key}
          onSelect={() => onSelectSource(meta.key)}
        />
      ))}
    </div>
  </div>
);
