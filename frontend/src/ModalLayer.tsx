import { type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

type ModalLayerProps = {
  children: ReactNode;
  className?: string;
  closeOnBackdrop?: boolean;
  onRequestClose?: () => void;
};

export function ModalLayer({
  children,
  className = "",
  closeOnBackdrop = true,
  onRequestClose,
}: ModalLayerProps) {
  useEffect(() => {
    const scrollY = window.scrollY;
    const previous = {
      position: document.body.style.position,
      top: document.body.style.top,
      width: document.body.style.width,
      overflow: document.body.style.overflow,
    };

    document.body.style.position = "fixed";
    document.body.style.top = `-${scrollY}px`;
    document.body.style.width = "100%";
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.position = previous.position;
      document.body.style.top = previous.top;
      document.body.style.width = previous.width;
      document.body.style.overflow = previous.overflow;
      if (scrollY !== 0) window.scrollTo(0, scrollY);
    };
  }, []);

  return createPortal(
    <div
      className={`modal-backdrop ${className}`.trim()}
      role="presentation"
      onMouseDown={(event) => {
        if (
          closeOnBackdrop &&
          event.target === event.currentTarget &&
          onRequestClose
        ) {
          onRequestClose();
        }
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
