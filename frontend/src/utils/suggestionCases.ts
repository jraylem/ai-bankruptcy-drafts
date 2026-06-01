export interface SuggestionCaseEntry {
  bkCaseNumber: string;
  caseNumber: string;
  circuitNumber: string;
  count: number;
  county: string;
  courtAgency: string;
  creditor: string;
  dateFiled: string;
  debtorName: string;
  district: string;
}

const normalizeSuggestionValue = (value?: string | null): string => {
  if (!value) {
    return '';
  }

  const trimmed = value.trim();
  return trimmed.toUpperCase() === 'N/A' ? '' : trimmed;
};

const splitSuggestionLines = (value?: string | null): string[] => {
  const normalized = normalizeSuggestionValue(value);

  if (!normalized) {
    return [];
  }

  return normalized
    .split(/\r?\n/)
    .map((line) => normalizeSuggestionValue(line))
    .filter((line) => line.length > 0);
};

const getSuggestionLineValue = (lines: string[], index: number): string => {
  if (lines.length === 0) {
    return '';
  }

  if (lines.length === 1) {
    return lines[0];
  }

  return lines[index] || '';
};

export const parseSuggestionCaseEntries = (
  payload: Partial<Record<string, string | null | undefined>>
): SuggestionCaseEntry[] => {
  const caseNumbers = splitSuggestionLines(payload.CaseNumber);
  const creditors = splitSuggestionLines(payload.Creditor);
  const courtAgencies = splitSuggestionLines(payload.CourtAgency);
  const counties = splitSuggestionLines(payload.County);
  const circuitNumbers = splitSuggestionLines(payload.CircuitNumber);
  const debtorNames = splitSuggestionLines(payload.DebtorName);
  const districts = splitSuggestionLines(payload.District);
  const bkCaseNumbers = splitSuggestionLines(payload.BKCaseNumber);
  const datesFiled = splitSuggestionLines(payload.DateFiled);

  return caseNumbers.map((caseNumber, index) => ({
    bkCaseNumber: getSuggestionLineValue(bkCaseNumbers, index),
    caseNumber,
    circuitNumber: getSuggestionLineValue(circuitNumbers, index),
    count: index,
    county: getSuggestionLineValue(counties, index),
    courtAgency: getSuggestionLineValue(courtAgencies, index),
    creditor: getSuggestionLineValue(creditors, index),
    dateFiled: getSuggestionLineValue(datesFiled, index),
    debtorName: getSuggestionLineValue(debtorNames, index),
    district: getSuggestionLineValue(districts, index),
  }));
};

export const normalizeSuggestionInputValue = normalizeSuggestionValue;
