import { useEffect, useRef } from "react";

type ConfirmDialogProps = {
  title: string;
  description: string;
  confirmLabel: string;
  tone?: "primary" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  tone = "primary",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [busy, onCancel]);

  return (
    <div
      className="modal-backdrop confirm-backdrop"
      role="presentation"
      onMouseDown={() => !busy && onCancel()}
    >
      <section
        className="modal confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="confirm-dialog-mark" aria-hidden="true">!</div>
        <div>
          <p className="eyebrow">CONFIRM ACTION</p>
          <h2 id="confirm-dialog-title">{title}</h2>
          <p id="confirm-dialog-description" className="confirm-dialog-description">
            {description}
          </p>
        </div>
        <div className="form-actions confirm-dialog-actions">
          <button
            ref={cancelRef}
            className="button-secondary"
            type="button"
            disabled={busy}
            onClick={onCancel}
          >
            キャンセル
          </button>
          <button
            className={tone === "danger" ? "button-danger" : "button-primary"}
            type="button"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "処理中…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
