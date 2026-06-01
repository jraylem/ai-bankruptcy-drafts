import React from 'react';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { AnalyticsHeader } from './AnalyticsHeader';

interface AnalyticsLayoutProps {
  children: React.ReactNode;
  title: string;
}

export const AnalyticsLayout: React.FC<AnalyticsLayoutProps> = ({ children, title }) => (
  <SidebarLayout sidebarVariant="app" className="bg-page" contentClassName="overflow-y-auto">
    <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
      <AnalyticsHeader title={title} />
      {children}
    </div>
  </SidebarLayout>
);
