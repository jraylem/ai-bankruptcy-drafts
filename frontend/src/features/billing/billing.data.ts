import { FiDatabase, FiFileText, FiLayers, FiMessageSquare } from 'react-icons/fi';
import type { BillingOverview, BillingUsageCategoryId } from './types/billing.types';

export const BILLING_MODEL_LABELS: Record<BillingOverview['billingModel'], string> = {
  pay_as_you_go: 'Pay as you go',
};

export const BILLING_USAGE_CATEGORY_METADATA: Record<
  BillingUsageCategoryId,
  {
    description: string;
    icon: BillingOverview['usageCategories'][number]['icon'];
  }
> = {
  agt_composition: {
    description: 'Agent template composition and workflow configuration.',
    icon: FiLayers,
  },
  chat: {
    description: 'Assistant conversations and case-aware chat interactions.',
    icon: FiMessageSquare,
  },
  ingestion: {
    description: 'Document uploads, parsing, and case file indexing.',
    icon: FiDatabase,
  },
  pleading_generation: {
    description: 'Draft generation for pleadings and related legal documents.',
    icon: FiFileText,
  },
};
