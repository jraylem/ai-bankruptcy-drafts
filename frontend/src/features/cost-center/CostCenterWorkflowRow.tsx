import React from 'react';
import { LuMessageSquare, LuFileText, LuFolderInput } from 'react-icons/lu';

import type { CostsSummaryResponse } from '@/types/costs';

import { WorkflowCostCard } from './WorkflowCostCard';

interface CostCenterWorkflowRowProps {
  data: CostsSummaryResponse;
}

export const CostCenterWorkflowRow: React.FC<CostCenterWorkflowRowProps> = ({
  data,
}) => {
  const { workflow_metrics: wm } = data;

  return (
    <section
      aria-label="Workflow cost breakdown"
      className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3"
    >
      <WorkflowCostCard
        title="Chat"
        icon={<LuMessageSquare className="h-4 w-4" aria-hidden="true" />}
        totalUsd={wm.chat.total_cost_usd}
        metrics={wm.chat.metrics}
        includesHint="Full-loaded per chat session: includes the main Sonnet call + any sub-agents the chat invokes (case_vector_vision, petition_vision_lookup, user_input_heal, etc.). Per-agent split lives on the Cost by activity rail. Breakdowns: avg per session, per user message, and per case."
      />
      <WorkflowCostCard
        title="Pleadings"
        icon={<LuFileText className="h-4 w-4" aria-hidden="true" />}
        totalUsd={wm.pleadings.total_cost_usd}
        metrics={wm.pleadings.metrics}
        includesHint="Full-loaded per draft run: includes draft + template + all resolver agents (auto-derive, dropdown, reco chips, vision, etc.). Dry-runs and real pleading tasks both count. Breakdowns: avg per run and per case."
      />
      <WorkflowCostCard
        title="Case Ingestion"
        icon={<LuFolderInput className="h-4 w-4" aria-hidden="true" />}
        totalUsd={wm.case_ingest.total_cost_usd}
        metrics={wm.case_ingest.metrics}
        includesHint="Includes the LLM extraction + embedding indexing per ingested petition. Avg per case (case_ingest row count as proxy)."
      />
    </section>
  );
};
