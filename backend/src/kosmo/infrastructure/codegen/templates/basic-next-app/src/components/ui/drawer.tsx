"use client";

import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
  position?: "start" | "end" | "top" | "bottom";
  className?: string;
}

export function Drawer({
  isOpen,
  onClose,
  title,
  description,
  children,
  position = "end",
  className,
}: DrawerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    if (isOpen) {
      document.body.style.overflow = "hidden";
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <>
      <div
        className="offcanvas-backdrop fade show"
        onClick={onClose}
        style={{ zIndex: 1045 }}
      />
      <div
        className={cn(
          "offcanvas show shadow-lg",
          `offcanvas-${position}`,
          className
        )}
        tabIndex={-1}
        style={{ zIndex: 1050, visibility: "visible" }}
      >
        <div className="offcanvas-header border-bottom p-3">
          <div>
            {title && <h5 className="offcanvas-title fw-bold fs-6 mb-0">{title}</h5>}
            {description && <p className="text-muted small mb-0 mt-1">{description}</p>}
          </div>
          <button
            type="button"
            className="btn-close text-reset"
            aria-label="Cerrar"
            onClick={onClose}
          />
        </div>
        <div className="offcanvas-body p-3">{children}</div>
      </div>
    </>
  );
}
