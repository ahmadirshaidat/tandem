"use client";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" />
        <DialogPrimitive.Content className="dialog-content">
          <DialogPrimitive.Title asChild>
            <h2>{title}</h2>
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="dialog-description">
            {description}
          </DialogPrimitive.Description>
          <div className="dialog-actions">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
