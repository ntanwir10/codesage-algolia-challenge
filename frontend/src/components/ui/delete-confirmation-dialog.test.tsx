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

  it("keeps Tab inside and gives focus back to the opener on close", () => {
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();
    const view = render(<DeleteConfirmationDialog {...props} onClose={vi.fn()} />);
    const cancel = screen.getByText("Cancel");
    const confirm = screen.getByText("Delete");

    confirm.focus();
    fireEvent.keyDown(document, { key: "Tab" }); // from the last button: wraps
    expect(cancel).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true }); // from the first: wraps back
    expect(confirm).toHaveFocus();

    view.rerender(<DeleteConfirmationDialog {...props} onClose={vi.fn()} isOpen={false} />);
    expect(opener).toHaveFocus();
    opener.remove();
  });

  it("ignores Escape while deleting", () => {
    const onClose = vi.fn();
    render(<DeleteConfirmationDialog {...props} onClose={onClose} isDeleting />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
