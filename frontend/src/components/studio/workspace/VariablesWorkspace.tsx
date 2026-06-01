import { useCallback, useMemo, useState, type ReactElement } from 'react';
import { ConfigureVariableModal } from '../modals/ConfigureVariableModal';
import { DryRunResultBanner } from '../banners/DryRunResultBanner';
import { VariableRow } from './VariableRow';
import { ActionErrorCard } from '../banners/ActionErrorCard';
import { useStudioStore } from '@/stores/useStudioStore';
import type { ResolvedTemplateValue, TemplateVariable } from '@/types/studio';

const HIGHLIGHT_DURATION_MS = 1500;

const dependentVariableOf = (v: TemplateVariable): string | null => {
  if (v.source !== 'auto_derived_from_variable') return null;
  const params = v.source_params;
  if (!params || !('dependent_variable' in params)) return null;
  return params.dependent_variable || null;
};

interface TreeNode {
  variable: TemplateVariable;
  children: TreeNode[];
}

const buildTree = (variables: TemplateVariable[]): TreeNode[] => {
  const sorted = [...variables].sort((a, b) => a.template_index - b.template_index);
  const nodes = new Map<string, TreeNode>(
    sorted.map((v) => [v.template_variable, { variable: v, children: [] }]),
  );

  const roots: TreeNode[] = [];
  for (const v of sorted) {
    const parentName = dependentVariableOf(v);
    const parentNode = parentName ? nodes.get(parentName) : null;
    const node = nodes.get(v.template_variable)!;
    if (parentNode) {
      parentNode.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
};

interface TreeNodeViewProps {
  node: TreeNode;
  depth: number;
  parentName: string | null;
  highlightedVariable: string | null;
  resolvedByName: Map<string, ResolvedTemplateValue>;
  onSelect: (propertyName: string) => void;
}

const TreeNodeView = ({
  node,
  depth,
  parentName,
  highlightedVariable,
  resolvedByName,
  onSelect,
}: TreeNodeViewProps): ReactElement => {
  const isNested = depth > 0;
  const hasChildren = node.children.length > 0;
  const variant = isNested ? 'child' : hasChildren ? 'parent' : 'standalone';

  const row = (
    <VariableRow
      variable={node.variable}
      resolvedValue={resolvedByName.get(node.variable.template_variable)}
      isHighlighted={highlightedVariable === node.variable.template_variable}
      onClick={() => onSelect(node.variable.template_variable)}
      variant={variant}
      childCount={hasChildren ? node.children.length : undefined}
      parentName={parentName ?? undefined}
    />
  );

  if (!hasChildren) {
    return isNested ? (
      <div className="relative before:absolute before:left-[-12px] before:top-6 before:h-px before:w-3 before:bg-border">
        {row}
      </div>
    ) : (
      row
    );
  }

  const groupShell = (
    <div
      role="group"
      aria-label={`${node.variable.template_variable} and ${node.children.length} derived field${node.children.length === 1 ? '' : 's'}`}
      className="relative space-y-1.5 rounded-xl border border-border bg-surface-muted/40 p-1.5"
    >
      {row}
      <div
        role="list"
        aria-label={`${node.variable.template_variable} derived fields`}
        className="relative space-y-1.5 pl-6 before:absolute before:left-3 before:top-1 before:bottom-1 before:w-px before:bg-border"
      >
        {node.children.map((child) => (
          <TreeNodeView
            key={child.variable.template_variable}
            node={child}
            depth={depth + 1}
            parentName={node.variable.template_variable}
            highlightedVariable={highlightedVariable}
            resolvedByName={resolvedByName}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );

  return isNested ? (
    <div className="relative before:absolute before:left-[-12px] before:top-6 before:h-px before:w-3 before:bg-border">
      {groupShell}
    </div>
  ) : (
    groupShell
  );
};

export const VariablesWorkspace = (): ReactElement => {
  const templateSpec = useStudioStore((state) => state.templateSpec);
  const dryRunResult = useStudioStore((state) => state.dryRunResult);
  const draftResult = useStudioStore((state) => state.draftResult);
  const [selectedPropertyName, setSelectedPropertyName] = useState<string | null>(null);
  const [highlightedVariable, setHighlightedVariable] = useState<string | null>(null);

  const tree = useMemo(() => buildTree(templateSpec), [templateSpec]);

  const selectedVariable = useMemo(
    () =>
      selectedPropertyName
        ? templateSpec.find((v) => v.template_variable === selectedPropertyName) ?? null
        : null,
    [selectedPropertyName, templateSpec]
  );

  const resolutionSource = draftResult ?? dryRunResult;

  const resolvedByName = useMemo(() => {
    const map = new Map<string, NonNullable<typeof resolutionSource>['resolved_values'][number]>();
    if (resolutionSource) {
      for (const rv of resolutionSource.resolved_values) {
        map.set(rv.property_name, rv);
      }
    }
    return map;
  }, [resolutionSource]);

  const mappedCount = templateSpec.filter(
    (v) => v.source !== null && (v.source === 'case_vector' || v.source_params !== null)
  ).length;

  const jumpToVariable = useCallback((propertyName: string) => {
    setHighlightedVariable(propertyName);
    window.setTimeout(() => {
      setHighlightedVariable((current) => (current === propertyName ? null : current));
    }, HIGHLIGHT_DURATION_MS);
  }, []);

  if (templateSpec.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-subtle">
        <svg className="h-12 w-12 text-subtle" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <p className="text-sm">Upload a legal document to see its variables.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ActionErrorCard onJumpToVariable={jumpToVariable} />
      <DryRunResultBanner onJumpToVariable={jumpToVariable} />

      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-text-secondary">Template Variables</h3>
          <p className="text-xs text-muted">
            {mappedCount} of {templateSpec.length} variables mapped
          </p>
        </div>
      </div>

      <div className="space-y-2">
        {tree.map((node) => (
          <TreeNodeView
            key={node.variable.template_variable}
            node={node}
            depth={0}
            parentName={null}
            highlightedVariable={highlightedVariable}
            resolvedByName={resolvedByName}
            onSelect={setSelectedPropertyName}
          />
        ))}
      </div>

      <ConfigureVariableModal
        variable={selectedVariable}
        onClose={() => setSelectedPropertyName(null)}
      />
    </div>
  );
};

export default VariablesWorkspace;
