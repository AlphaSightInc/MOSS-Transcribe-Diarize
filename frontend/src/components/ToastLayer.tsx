import type { ToastItem } from "../state/ui";

interface ToastLayerProps {
  onDismiss: (id: string) => void;
  toasts: readonly ToastItem[];
}

export function ToastLayer({ onDismiss, toasts }: ToastLayerProps) {
  return (
    <section className="toast-layer" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <button
          key={toast.id}
          type="button"
          className="toast"
          data-tone={toast.tone}
          onClick={() => onDismiss(toast.id)}
        >
          <span className="toast-marker" aria-hidden="true" />
          <span>{toast.message}</span>
        </button>
      ))}
    </section>
  );
}
