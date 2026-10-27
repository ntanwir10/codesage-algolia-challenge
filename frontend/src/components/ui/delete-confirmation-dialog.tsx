import { useEffect, useId, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DeleteConfirmationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  isDeleting?: boolean;
  variant?: "danger" | "warning";
}

export function DeleteConfirmationDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = "Delete",
  cancelText = "Cancel",
  isDeleting = false,
  variant = "danger",
}: DeleteConfirmationDialogProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);

  // Focus Cancel, and give focus back to whatever opened the dialog once it closes.
  // Not autoFocus: that runs first, so the opener would read as Cancel
  useEffect(() => {
    if (!isOpen) return;
    const opener = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector("button")?.focus();
    return () => opener?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isDeleting) onClose();
      if (e.key !== "Tab" || !dialogRef.current) return;
      // A modal keeps Tab inside: wrap between its first and last enabled button
      const buttons = dialogRef.current.querySelectorAll<HTMLElement>("button:not(:disabled)");
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      const inside = dialogRef.current.contains(document.activeElement);
      if (!first) {
        e.preventDefault();
      } else if (!inside || document.activeElement === (e.shiftKey ? first : last)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, isDeleting, onClose]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !isDeleting) {
      onClose();
    }
  };

  const variantStyles = {
    danger: {
      icon: "🗑️",
      confirmButton: "bg-red-600 hover:bg-red-700 text-white",
      iconBg: "bg-red-100",
    },
    warning: {
      icon: "⚠️",
      confirmButton: "bg-orange-600 hover:bg-orange-700 text-white",
      iconBg: "bg-orange-100",
    },
  };

  const styles = variantStyles[variant];

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      onClick={handleBackdropClick}
    >
      <Card
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md mx-auto"
      >
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className={`p-2 ${styles.iconBg} rounded-lg`}>
              <span className="text-2xl">{styles.icon}</span>
            </div>
            <CardTitle id={titleId} className="text-lg">{title}</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground">{description}</p>

          <div className="flex gap-3 justify-end">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={isDeleting}
              className="min-w-20"
            >
              {cancelText}
            </Button>
            <Button
              onClick={onConfirm}
              disabled={isDeleting}
              className={`min-w-20 ${styles.confirmButton}`}
            >
              {isDeleting ? (
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Deleting...</span>
                </div>
              ) : (
                confirmText
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
