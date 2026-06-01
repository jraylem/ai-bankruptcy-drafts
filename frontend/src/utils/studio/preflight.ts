
import type {
  ConstantsSourceParams,
  ReferenceData,
  TemplateVariable,
  VectorSourceParams,
} from '@/types/studio';

export const preflightTemplateSpec = (
  spec: TemplateVariable[],
  referenceData: ReferenceData[],
): string[] => {
  const errors: string[] = [];
  const knownShortCodes = new Set(referenceData.map((r) => r.short_code));

  for (const v of spec) {
    if (!v.source) {
      errors.push(`Variable '${v.template_variable}' is missing source`);
      continue;
    }
    
    if (v.source === 'case_vector') continue;

    if (!v.source_params) {
      errors.push(`Variable '${v.template_variable}' is missing source_params`);
      continue;
    }
    if (v.source === 'constants') {
      const params = v.source_params as ConstantsSourceParams;
      if (!params.short_code) {
        errors.push(
          `Variable '${v.template_variable}' with source 'constants' requires short_code in source_params`,
        );
      } else if (!knownShortCodes.has(params.short_code)) {
        errors.push(
          `Variable '${v.template_variable}' references unknown constant '${params.short_code}'`,
        );
      }
    }
    if (v.source === 'law_practice_vector') {
      const params = v.source_params as VectorSourceParams;
      if (!params.text_query?.trim()) {
        errors.push(
          `Variable '${v.template_variable}' with source 'law_practice_vector' requires a non-empty text_query`,
        );
      }
    }
  }
  return errors;
};
