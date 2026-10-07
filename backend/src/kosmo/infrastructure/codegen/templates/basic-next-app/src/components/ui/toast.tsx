"use client";

import { useEffect, useState, type ReactNode } from "react";
import { CheckCircle2, AlertCircle, AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ToastProps {
  id?: string;
  title: string;
  description?: string;
  variant?: "success" | "danger" | "warning" | "info";
  duration?: number; // ms
  onClose?: () => void;
  className?: string;
}

const icons = {
  success: <CheckCircle2 size={18} className="text-success flex-shrink-0" />,
  danger: <AlertCircle size={18} className="text-danger flex-shrink-0" />,
  warning: <AlertTriangle size={18} className="text-warning flex-shrink-0" />,
  info: <Info size={18} className="text-info flex-shrink-0" />,
};

export function Toast({
  title,
  description,
  variant = "info",
  duration = 5000,
  onClose,
  className,
}: ToastProps) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        setVisible(false);
        onClose?.();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onClose]);

  if (!visible) return null;

  return (
    <div
      className={cn(
        "toast show shadow-lg border-0 bg-white mb-2",
        className
      )}
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      style={{ minWidth: "280px" }}
    >
      <div className="toast-header border-bottom-0 pb-1 pt-2 px-3 d-flex align-items-center justify-content-between">
        <div className="d-flex align-items-center gap-2">
          {icons[variant]}
          <strong className="me-auto small text-dark">{title}</strong>
        </div>
        <button
          type="button"
          className="btn-close ms-2"
          aria-label="Cerrar"
          onClick={() => {
            setVisible(false);
            onClose?.();
          }}
        />
      </div>
      {description && (
        <div className="toast-body pt-0 pb-2 px-3 text-muted small">
          {description}
        </div>
      )}
    </div>
  );
}

export function ToastContainer({
  children,
  position = "bottom-end",
}: {
  children: ReactNode;
  position?: "top-end" | "top-start" | "bottom-end" | "bottom-start";
}) {
  const positionClasses = {
    "top-end": "top-0 end-0",
    "top-start": "top-0 start-0",
    "bottom-end": "bottom-0 end-0",
    "bottom-start": "bottom-0 start-0",
  };

  return (
    <div
      className={cn("toast-container position-fixed p-3", positionClasses[position])}
      style={{ zIndex: 1090 }}
    >
      {children}
    </div>
  );
}
