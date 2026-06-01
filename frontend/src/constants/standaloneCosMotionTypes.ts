export interface StandaloneCosMotionTypeOption {
  label: string;
  value: string;
}

// Mirrors backend motion context labels for standalone Certificate of Service.
export const STANDALONE_COS_MOTION_TYPE_OPTIONS: StandaloneCosMotionTypeOption[] = [
  { label: 'Motion to Extend Automatic Stay', value: 'Motion to Extend Automatic Stay' },
  { label: 'Motion to Modify Plan', value: 'Motion to Modify Plan' },
  { label: 'Motion to Value Personal Property', value: 'Motion to Value Personal Property' },
  { label: 'Motion to Withdraw as Counsel', value: 'Motion to Withdraw as Counsel' },
  { label: 'Motion to Waive Filing Fee', value: 'Motion to Waive Filing Fee' },
  { label: 'Motion/Objection to Claim', value: 'Motion/Objection to Claim' },
  { label: 'Motion to Delay', value: 'Motion to Delay' },
  { label: 'Motion to Reinstate', value: 'Motion to Reinstate' },
  { label: 'Suggestion of Bankruptcy', value: 'Suggestion of Bankruptcy' },
  { label: 'Letter of Explanation to Trustee', value: 'Letter of Explanation to Trustee' },
  { label: 'Notice of Withdrawal', value: 'Notice of Withdrawal' },
];
