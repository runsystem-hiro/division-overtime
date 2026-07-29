import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toast } from "../src/Toast";

afterEach(() => {
  vi.useRealTimers();
});

describe("Toast", () => {
  it("成功通知を指定時間後に閉じる", () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    render(
      <Toast kind="success" message="更新しました" duration={5000} onClose={onClose} />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("更新しました");
    act(() => vi.advanceTimersByTime(5000));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("閉じるボタンでエラー通知を閉じる", () => {
    const onClose = vi.fn();
    render(<Toast kind="error" message="失敗しました" onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "エラーメッセージを閉じる" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
