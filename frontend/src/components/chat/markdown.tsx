import type { Components } from 'react-markdown';

export const CHAT_MARKDOWN_CLASSNAME =
  'prose prose-sm prose-slate max-w-none break-words sm:prose-base 2xl:prose-lg font-body text-text-secondary ' +
  '[&_p]:text-[clamp(0.9rem,0.14vw+0.87rem,1rem)] [&_p]:leading-7 [&_p]:font-normal ' +
  '[&_li]:text-[clamp(0.88rem,0.12vw+0.85rem,0.96rem)] [&_li]:leading-7 ' +
  '[&_strong]:font-poppins [&_strong]:font-semibold [&_strong]:text-text ' +
  '[&_ul>li::marker]:text-app-accent [&_ol>li::marker]:text-app-accent ' +
  '[&_blockquote]:border-l-app-accent [&_blockquote]:bg-app-accent-soft/50 [&_blockquote]:text-text-secondary ' +
  '[&_blockquote]:rounded-lg [&_blockquote]:shadow-sm [&_blockquote_p]:text-text-secondary ' +
  '[&_ol]:pl-5 [&_ul]:pl-5 [&_code]:break-words';

const tableTextSizeClass =
  'text-[clamp(0.76rem,0.14vw+0.72rem,0.95rem)] leading-6';

export const chatMarkdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="font-poppins mb-4 mt-6 text-2xl font-bold text-app-accent-text">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="font-poppins mb-3 mt-5 text-[1.35rem] font-bold text-app-accent-text">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="font-poppins mb-3 mt-4 text-[1.12rem] font-semibold text-app-accent-text">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="font-poppins mb-2 mt-4 text-base font-semibold text-app-accent-text">
      {children}
    </h4>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-5 rounded-lg border-l-4 border-l-app-accent bg-app-accent-soft/50 px-5 py-4 text-text-secondary shadow-sm">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-4 w-full overflow-x-auto rounded-lg border border-border shadow-sm">
      <table className="min-w-full border-collapse bg-surface text-left">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-muted">{children}</thead>,
  th: ({ children }) => (
    <th
      className={`border border-border px-2 py-2 align-top font-semibold text-text-secondary sm:px-3 ${tableTextSizeClass}`}
    >
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td
      className={`border border-border px-2 py-2 align-top text-muted sm:px-3 ${tableTextSizeClass}`}
    >
      {children}
    </td>
  ),
  code: ({ children }) => (
    <code className="rounded-md bg-app-accent-soft/65 px-1.5 py-0.5 font-medium text-app-accent-text">
      {children}
    </code>
  ),
  mark: ({ children }) => (
    <mark className="rounded-md bg-app-accent-soft/70 px-1.5 py-0.5 text-app-accent-text">
      {children}
    </mark>
  ),
};
