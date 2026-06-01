import {
  FiMail,
  FiFolder,
  FiBookmark,
  FiCalendar,
  FiEdit3,
  FiGitBranch,
  FiLink,
  FiUserCheck,
} from 'react-icons/fi';
import type { SourceKind } from './types';

const ICON_BY_SOURCE: Record<SourceKind, typeof FiMail> = {
  gmail: FiMail,
  case_file: FiFolder,
  attorney: FiUserCheck,
  constants: FiBookmark,
  current_date: FiCalendar,
  author_input: FiEdit3,
  derived_from_variable: FiGitBranch,
  value_from_parent_bundle: FiLink,
};

interface SourceIconProps {
  source: SourceKind;
  className?: string;
}

export const SourceIcon = ({ source, className }: SourceIconProps) => {
  const Icon = ICON_BY_SOURCE[source];
  return <Icon className={className} />;
};
