// utils/htmlSanitizer.ts
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import he from 'he';

export type Format = 'html' | 'escaped' | 'markdown' | 'text';


export function sanitizeToHTML(raw: string, format: Format = 'text'): string {
  if (!raw) return '';

  let processed = '';

  switch (format) {
    case 'escaped':
      processed = he.decode(raw);
      break;

    case 'markdown':
      processed = marked.parse(raw);
      break;

    case 'html':
      processed = raw;
      break;

    case 'text':
    default:
      processed = raw
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br/>');
      break;
  }

  const sanitized = DOMPurify.sanitize(processed);
  return sanitized;
}
