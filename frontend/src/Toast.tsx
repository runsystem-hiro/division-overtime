import { useEffect, useRef, useState } from "react";

export type ToastKind = "success" | "info" | "warning" | "error";

type ToastProps = {
  kind: ToastKind;
  message: string;
  onClose: () => void;
  duration?: number;
};

const labels: Record<ToastKind, string> = {
  success: "完了",
  info: "お知らせ",
  warning: "注意",
  error: "エラー",
};

export function Toast({ kind, message, onClose, duration }: ToastProps) {
  const [paused, setPaused] = useState(false);
  const remainingRef = useRef(duration ?? 0);
  const startedAtRef = useRef(Date.now());

  useEffect(() => {
    if (!duration || paused) return;
    startedAtRef.current = Date.now();
    const timer = window.setTimeout(onClose, remainingRef.current);
    return () => {
      window.clearTimeout(timer);
      remainingRef.current = Math.max(
        0,
        remainingRef.current - (Date.now() - startedAtRef.current),
      );
    };
  }, [duration, onClose, paused]);

  return (
    <aside
      className={`app-toast app-toast-${kind}`}
      role={kind === "error" ? "alert" : "status"}
      aria-live={kind === "error" ? "assertive" : "polite"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <span className="app-toast-icon" aria-hidden="true">
        {kind === "success" ? "✓" : kind === "error" ? "!" : kind === "warning" ? "!" : "i"}
      </span>
      <div className="app-toast-content">
        <strong>{labels[kind]}</strong>
        <p>{message}</p>
      </div>
      <button
        className="app-toast-close"
        type="button"
        aria-label={`${labels[kind]}メッセージを閉じる`}
        onClick={onClose}
      >
        ×
      </button>
      {duration && (
        <span
          className={`app-toast-progress${paused ? " is-paused" : ""}`}
          style={{ animationDuration: `${duration}ms` }}
          aria-hidden="true"
        />
      )}
    </aside>
  );
}
