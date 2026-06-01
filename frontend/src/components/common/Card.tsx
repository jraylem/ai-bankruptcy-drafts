import React from 'react';
import { cn } from '@/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  variant?: 'default' | 'bordered' | 'elevated';
}

export const Card: React.FC<CardProps> = ({
  children,
  variant = 'default',
  className,
  ...props
}) => {
  const variants = {
    default: 'bg-surface rounded-lg shadow-sm border border-border',
    bordered: 'bg-surface rounded-lg border-2 border-border',
    elevated: 'bg-surface rounded-lg shadow-lg',
  };

  return (
    <div className={cn(variants[variant], 'p-6', className)} {...props}>
      {children}
    </div>
  );
};

interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const CardHeader: React.FC<CardHeaderProps> = ({ children, className, ...props }) => {
  return (
    <div className={cn('mb-4', className)} {...props}>
      {children}
    </div>
  );
};

interface CardTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {
  children: React.ReactNode;
}

export const CardTitle: React.FC<CardTitleProps> = ({ children, className, ...props }) => {
  return (
    <h3 className={cn('text-xl font-semibold text-text', className)} {...props}>
      {children}
    </h3>
  );
};

interface CardContentProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const CardContent: React.FC<CardContentProps> = ({ children, className, ...props }) => {
  return (
    <div className={cn('text-text-secondary', className)} {...props}>
      {children}
    </div>
  );
};
