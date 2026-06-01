import { type ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';
import { BundleCompanionsEditor } from './BundleCompanionsEditor';
import type { TemplateBundleRole } from '@/types/studio';

// Phase 1B "Bundle Settings" panel.
// Renders inside the studio's Bundling workspace tab. Reads + writes
// bundleRole from useStudioStore; toggling marks the template dirty so
// the next saveConfiguration() call persists to the BE via
// PUT /template/{id}/bundling-config.

interface RoleOption {
  value: TemplateBundleRole;
  label: string;
  description: string;
}

const ROLE_OPTIONS: RoleOption[] = [
  {
    value: 'standalone',
    label: 'Standalone',
    description: 'Runs on its own. Drafted directly. No children.',
  },
  {
    value: 'parent',
    label: 'Parent',
    description:
      'Runs on its own; can attach child templates at draft time (e.g. attach a Certificate of Service variant).',
  },
  {
    value: 'child_only',
    label: 'Child only',
    description:
      'Cannot be drafted directly. Only invoked when a parent template attaches this as a bundle companion. Variables can use the new “Inherit from Parent” source to mark themselves as slots that the attaching parent will fill.',
  },
];

export const TemplateBundleSettings = (): ReactElement => {
  const bundleRole = useStudioStore((s) => s.bundleRole);
  const setBundleRole = useStudioStore((s) => s.setBundleRole);

  return (
    <div>
      <div className="space-y-2">
        {ROLE_OPTIONS.map((option) => {
          const isSelected = option.value === bundleRole;
          return (
            <label
              key={option.value}
              className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 transition-colors ${
                isSelected
                  ? 'border-app-accent bg-surface ring-1 ring-app-accent'
                  : 'border-border bg-surface hover:border-indigo-200 hover:bg-indigo-50/40'
              }`}
            >
              <input
                type="radio"
                name="bundle-role"
                value={option.value}
                checked={isSelected}
                onChange={() => setBundleRole(option.value)}
                className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-indigo-600"
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-text-secondary">
                  {option.label}
                </span>
                <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                  {option.description}
                </span>
              </span>
            </label>
          );
        })}
      </div>

      <RoleBody role={bundleRole} />
    </div>
  );
};

const RoleBody = ({ role }: { role: TemplateBundleRole }): ReactElement | null => {
  // Standalone + Child only have no extra body — the radio description
  // already covers what each role means, the section's "Configure this
  // first…" copy explains the dependency direction, and `Inherit from
  // Parent` shows up as the first category in the source picker below
  // when role is child_only. The Parent role gets the inline companions
  // editor since that's where the per-attachment / per-slot work lives.
  if (role === 'parent') {
    return (
      <div className="mt-5">
        <BundleCompanionsEditor />
      </div>
    );
  }
  return null;
};

export default TemplateBundleSettings;
