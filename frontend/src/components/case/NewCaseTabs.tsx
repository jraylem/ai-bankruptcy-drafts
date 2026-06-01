import { useState, type ReactElement } from 'react';

import { NewCaseDropzone } from './NewCaseDropzone';
import { NewCaseExtractByNumber } from './NewCaseExtractByNumber';

type Tab = 'upload' | 'caseNumber';

interface NewCaseTabsProps {
  isUploading: boolean;
  onSubmitFile: (file: File) => Promise<boolean>;
  onSubmitCaseNumber: (caseNumber: string) => Promise<boolean>;
}

const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: 'upload', label: 'Upload PDF' },
  { id: 'caseNumber', label: 'Case Number' },
];

export const NewCaseTabs = ({
  isUploading,
  onSubmitFile,
  onSubmitCaseNumber,
}: NewCaseTabsProps): ReactElement => {
  const [activeTab, setActiveTab] = useState<Tab>('upload');

  return (
    <div className="h-full overflow-y-auto bg-page">
      <div className="mx-auto max-w-5xl px-6 pt-10 pb-16 sm:px-10 sm:pt-14">
        <header className="max-w-3xl">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-app-accent-text">
            New Case
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-text-secondary sm:text-3xl">
            Start a new case
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Upload the petition PDF directly, or enter a case number and we&rsquo;ll fetch the
            petition from the court system for you.
          </p>
        </header>

        <div className="mt-6 flex justify-center">
          <div
            role="tablist"
            aria-label="New case source"
            className="inline-flex items-center gap-1 rounded-xl border border-border bg-surface-muted p-1"
          >
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActiveTab(tab.id)}
                  className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition ${
                    isActive
                      ? 'bg-surface text-text-secondary shadow-sm'
                      : 'text-muted hover:text-text-secondary'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-8">
          {activeTab === 'upload' ? (
            <NewCaseDropzone onSubmit={onSubmitFile} isUploading={isUploading} />
          ) : (
            <NewCaseExtractByNumber onSubmit={onSubmitCaseNumber} isUploading={isUploading} />
          )}
        </div>
      </div>
    </div>
  );
};

export default NewCaseTabs;
