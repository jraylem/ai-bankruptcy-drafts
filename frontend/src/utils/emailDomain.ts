export const getEmailDomain = (email: string): string => {
  const [, domain = ''] = email.trim().toLowerCase().split('@');
  return domain;
};

export const normalizeAllowedDomain = (domain: string): string =>
  domain.trim().toLowerCase().replace(/^@+/, '');

export const isEmailInAllowedDomain = (email: string, allowedDomain: string): boolean =>
  Boolean(allowedDomain) && getEmailDomain(email) === normalizeAllowedDomain(allowedDomain);
