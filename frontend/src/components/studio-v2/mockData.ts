/**
 * FE-only display fixtures for the wizard's Fine-tune step.
 *
 * These are GENUINELY mock data — the FE wizard hasn't been wired to
 * fetch the real ATTORNEYS roster / reference_data rows from the BE
 * yet, so the constant + attorney dropdowns in the Fine-tune step
 * pull options from these hardcoded lists.
 *
 * When the wizard is wired to fetch the live reference data, both
 * exports below should be deleted and the consuming components
 * (`steps/RefinementStep.tsx`, `steps/PreviewStep.tsx`) should pull
 * from the BE instead.
 */

export interface MockAttorney {
  id: string;
  display_name: string;
  bar_number: string;
}

// Stands in for the firm-wide ATTORNEYS reference_data row at draft time.
export const MOCK_ATTORNEYS: MockAttorney[] = [
  { id: 'att-1', display_name: 'Nick F. Heredia, Esq.', bar_number: 'CA 234567' },
  { id: 'att-2', display_name: 'Maria Lopez, Esq.', bar_number: 'CA 198765' },
  { id: 'att-3', display_name: 'David Chen, Esq.', bar_number: 'CA 312890' },
  { id: 'att-4', display_name: 'Sarah O\'Brien, Esq.', bar_number: 'CA 287654' },
];

export interface MockFirmConstant {
  short_code: string;
  display_name: string;
  value: string;
  description: string | null;
}

// Stands in for the firm-wide reference_data rows (non-ATTORNEYS).
export const MOCK_FIRM_CONSTANTS: MockFirmConstant[] = [
  {
    short_code: 'firm_address',
    display_name: 'Firm Mailing Address',
    value: '1234 Legal Way, Suite 500, Los Angeles, CA 90001',
    description: 'Office mailing address on the letterhead.',
  },
  {
    short_code: 'firm_phone',
    display_name: 'Firm Phone Number',
    value: '(213) 555-1234',
    description: 'Main office line.',
  },
  {
    short_code: 'firm_email',
    display_name: 'Firm Contact Email',
    value: 'contact@example-firm.com',
    description: 'General intake inbox.',
  },
  {
    short_code: 'default_disclaimer',
    display_name: 'Standard Disclaimer',
    value:
      'This communication contains confidential, privileged information from the offices of Example Firm LLP. If you received this in error, please notify the sender and delete.',
    description: 'Footer disclaimer for outbound mail.',
  },
  {
    short_code: 'ch13_trustee',
    display_name: 'Chapter 13 Trustee',
    value: 'Kathy A. Dockery',
    description: 'Standing trustee for Chapter 13 filings.',
  },
  {
    short_code: 'court_address',
    display_name: 'Bankruptcy Court Address',
    value: 'United States Bankruptcy Court, 255 E Temple St, Los Angeles, CA 90012',
    description: 'Central District filing address.',
  },
];
