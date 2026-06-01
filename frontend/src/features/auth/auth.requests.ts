const CSRF_COOKIE_NAME = 'csrf_token';
const CSRF_HEADER_NAME = 'X-CSRF-Token';
const MUTATION_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export const getCsrfToken = (): string | null => {
  if (typeof document === 'undefined') {
    return null;
  }

  const cookie = document.cookie.split('; ').find((row) => row.startsWith(`${CSRF_COOKIE_NAME}=`));
  return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : null;
};

export const isMutationMethod = (method?: string): boolean => {
  return MUTATION_METHODS.has((method || 'GET').toUpperCase());
};

export const withCookieCredentials = (init: RequestInit = {}): RequestInit => {
  const method = init.method || 'GET';
  const headers = new Headers(init.headers);
  const csrfToken = getCsrfToken();

  if (csrfToken && isMutationMethod(method)) {
    headers.set(CSRF_HEADER_NAME, csrfToken);
  }

  return {
    ...init,
    credentials: 'include',
    headers,
  };
};
