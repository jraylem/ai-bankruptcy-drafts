import type { ReactElement } from 'react';
import { FALLBACK_SOURCE_ICON, SOURCE_ICON_COMPONENTS } from '@/utils/studio/sourceIconMap';
import type { FieldSource } from '@/types/studio';

interface SourceIconProps {
  source: FieldSource | null | undefined;
  className?: string;
}

export const SourceIcon = ({
  source,
  className = 'h-3.5 w-3.5',
}: SourceIconProps): ReactElement => {
  const Icon = source
    ? SOURCE_ICON_COMPONENTS[source] ?? FALLBACK_SOURCE_ICON
    : FALLBACK_SOURCE_ICON;
  return <Icon className={className} aria-hidden="true" />;
};

export default SourceIcon;
