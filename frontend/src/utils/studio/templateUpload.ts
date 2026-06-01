/**
 * Shared constants and helpers for DOCX template uploads. Used by both the
 * UploadTemplateModal (toolbar Upload button) and the StudioTemplateUploader
 * (empty-state inline uploader) so file rules + auto-name derivation stay
 * consistent across entry points.
 */

export const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

export const MAX_SIZE_BYTES = 10 * 1024 * 1024;

export const deriveTemplateName = (filename: string): string =>
  filename.replace(/\.docx$/i, '').replace(/[-_]+/g, ' ').trim() || 'Untitled Template';
