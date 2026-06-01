import React from 'react';

interface BillingCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
}

export const BillingCard: React.FC<BillingCardProps> = ({ children, className = '', ...props }) => (
  <div className={`rounded-2xl bg-surface ${className}`} {...props}>{children}</div>
);
