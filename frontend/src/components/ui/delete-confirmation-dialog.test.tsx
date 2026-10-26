import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DeleteConfirmationDialog } from "./delete-confirmation-dialog";

const props = {
  isOpen: true,
  onConfirm: vi.fn(),
  title: "Delete Repository",
  description: "Sure?",
};

describe("DeleteConfirmationDialog", () => {
  it("is a labelled modal that focuses Cancel and closes on Escape", () => {
    const onClose = vi.fn();
    render(<DeleteConfirmationDialog {...props} onClose={onClose} />);
    expect(
      screen.getByRole("dialog", { name: "Delete Repository" })
    ).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("Cancel")).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores Escape while deleting", () => {
    const onClose = vi.fn();
    render(<DeleteConfirmationDialog {...props} onClose={onClose} isDeleting />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
