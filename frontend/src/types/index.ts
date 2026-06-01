export interface User {
  id: string;
  username?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  is_active?: boolean;
  is_accepted?: boolean;
  firm_id?: string | null;
  onboarding_status?: 'pending' | 'completed' | string | null;
  role?: string | null;
  permissions?: string[] | null;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

export interface ChatSession {
  id: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface PDFDocument {
  id: string;
  name: string;
  url: string;
  uploadedAt: Date;
  numPages?: number;
}

export interface ReferencingParent {
  template_id: string;
  name: string;
  companion_labels: string[];
}

export interface ApiResponse<T = unknown> {
  data?: T;
  error?: string;
  message?: string;
  reason?: 'link_expired' | 'not_found';
  validationErrors?: string[];
  /**
   * Surfaced from FastAPI HTTPException detail objects shaped like
   *   { detail: { code: '<machine-readable-code>', message: '...' } }
   * so callers can branch on a known error code (e.g. `email_not_confirmed`)
   * without string-matching the user-facing message.
   */
  code?: string;
  /**
   * Populated by handleError when the BE returns a 409 conflict detail
   * with a `referencing_parents` payload (currently only fired by
   * DELETE /api/v2/core/template/{id} when other parent templates'
   * bundle_companions reference the deletion target). Callers can offer
   * the author a force-delete option.
   */
  conflictParents?: ReferencingParent[];
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (user: User | null) => void;
}

export interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  addMessage: (message: Message) => void;
}

export interface PDFState {
  currentPDF: PDFDocument | null;
  currentPage: number;
  numPages: number;
  scale: number;
  isLoading: boolean;
  error: string | null;
  uploadPDF: (file: File) => Promise<void>;
  setCurrentPage: (page: number) => void;
  setScale: (scale: number) => void;
  clearPDF: () => void;
}
