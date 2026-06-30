import type { ServerValidationDetail } from '../../api/http';

interface Props {
  /** A backend 422 detail ({field?, message}). */
  serverError?: ServerValidationDetail | null;
  /** Client-side validation messages (instant feedback before save). */
  clientErrors?: string[];
}

/** Renders server 422 + client validation errors as an alert list. Surfaces every
 *  validation problem — never swallowed. */
export function ValidationErrorList({ serverError, clientErrors = [] }: Props) {
  const items: string[] = [];
  if (serverError) {
    items.push(serverError.field ? `${serverError.field}: ${serverError.message}` : serverError.message);
  }
  for (const e of clientErrors) items.push(e);
  if (items.length === 0) return null;
  return (
    <ul role="alert" className="validation-errors">
      {items.map((msg, i) => (
        <li key={i}>{msg}</li>
      ))}
    </ul>
  );
}
