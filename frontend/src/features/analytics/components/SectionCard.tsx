import React from 'react';

interface SectionCardProps {
  title: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
}

export const SectionCard: React.FC<SectionCardProps> = ({
  title,
  action,
  children,
  className = '',
  headerClassName = '',
}) => (
  <section className={`flex flex-col rounded-2xl bg-surface p-6 ${className}`}>
    <div className={`mb-6 flex items-center justify-between ${headerClassName}`}>
      <div className="font-poppins text-lg font-semibold text-text-secondary">{title}</div>
      {action}
    </div>
    {children}
  </section>
);
