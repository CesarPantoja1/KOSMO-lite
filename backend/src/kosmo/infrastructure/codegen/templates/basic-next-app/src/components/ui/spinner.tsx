import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface SpinnerProps extends HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "md" | "lg";
  variant?: "primary" | "secondary" | "success" | "danger" | "warning" | "light" | "dark";
  type?: "border" | "grow";
}

const textColors = {
  primary: "text-primary",
  secondary: "text-secondary",
  success: "text-success",
  danger: "text-danger",
  warning: "text-warning",
  light: "text-light",
  dark: "text-dark",
};

export function Spinner({
  size = "md",
  variant = "primary",
  type = "border",
  className,
  ...props
}: SpinnerProps) {
  const spinnerClass = type === "border" ? "spinner-border" : "spinner-grow";

  return (
    <div
      className={cn(
        spinnerClass,
        textColors[variant],
        size === "sm" && "spinner-border-sm",
        className
      )}
      style={size === "lg" ? { width: "3rem", height: "3rem" } : undefined}
      role="status"
      {...props}
    >
      <span className="visually-hidden">Cargando...</span>
    </div>
  );
}

export function LoadingOverlay({ text = "Cargando..." }: { text?: string }) {
  return (
    <div className="d-flex flex-column align-items-center justify-content-center p-5 gap-3">
      <Spinner size="lg" variant="primary" />
      <span className="text-muted small fw-medium">{text}</span>
    </div>
  );
}
