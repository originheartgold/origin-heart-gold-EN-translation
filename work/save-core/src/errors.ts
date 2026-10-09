/** Expected, actionable failures at the editor boundary. */
export type EditorErrorCode = 'invalid-save' | 'invalid-pokemon' | 'invalid-input' | 'invalid-reference' | 'read-failed';
export type EditorErrorContext =
  | { readonly kind: 'wrong-pocket'; readonly itemId: number; readonly pocketLabel: string }
  | { readonly kind: 'duplicate-item'; readonly itemId: number };
export class EditorError extends Error {
  override readonly name = 'EditorError';
  constructor(readonly code: EditorErrorCode, message: string, readonly context?: EditorErrorContext, options?: ErrorOptions) {
    super(message, options);
  }
}
/** Never display arbitrary thrown objects or implementation exceptions as advice. */
export function editorErrorMessage(error: unknown, itemName?: (id: number) => string | undefined): string {
  if (!(error instanceof EditorError)) return 'Something went wrong. Your original save file was not changed. Please reload the editor and try again.';
  const context = error.context;
  if (context) {
    const item = itemName?.(context.itemId) ?? `Item #${context.itemId}`;
    switch (context.kind) {
      case 'wrong-pocket': return `${item} does not belong in ${context.pocketLabel}.`;
      case 'duplicate-item': return `${item} occurs more than once. Change its quantity instead.`;
    }
  }
  return error.message;
}
