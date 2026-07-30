import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModalLayer } from "../src/ModalLayer";

describe("ModalLayer", () => {
  it("document.body配下へ描画し、内部操作では閉じない", () => {
    const onRequestClose = vi.fn();
    render(
      <ModalLayer onRequestClose={onRequestClose}>
        <section role="dialog" aria-label="テストモーダル">
          <button type="button">内部操作</button>
        </section>
      </ModalLayer>,
    );

    const dialog = screen.getByRole("dialog", { name: "テストモーダル" });
    const backdrop = dialog.closest(".modal-backdrop");
    expect(backdrop?.parentElement).toBe(document.body);
    expect(document.body.style.position).toBe("fixed");

    fireEvent.mouseDown(screen.getByRole("button", { name: "内部操作" }));
    expect(onRequestClose).not.toHaveBeenCalled();

    fireEvent.mouseDown(backdrop!);
    expect(onRequestClose).toHaveBeenCalledTimes(1);
  });
});
