import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TimelineItemProps {
  title: string;
  timestamp?: string;
  description?: ReactNode;
  variant?: "primary" | "success" | "warning" | "danger" | "secondary";
  children?: ReactNode;
  className?: string;
}

const variantBorderColors = {
  primary: "var(--bs-primary)",
  success: "var(--bs-success)",
  warning: "var(--bs-warning)",
  danger: "var(--bs-danger)",
  secondary: "var(--bs-secondary)",
};

export function TimelineItem({
  title,
  timestamp,
  description,
  variant = "primary",
  children,
  className,
}: TimelineItemProps) {
  return (
    <div className={cn("kosmo-timeline-item", className)}>
      <div
        className="kosmo-timeline-point"
        style={{ backgroundColor: variantBorderColors[variant] }}
      />
      <div className="d-flex align-items-center justify-content-between mb-1">
        <h6 className="mb-0 fw-semibold fs-6 text-dark">{title}</h6>
        {timestamp && <span className="text-muted small" style={{ fontSize: "0.75rem" }}>{timestamp}</span>}
      </div>
      {description && <div className="text-muted small mb-2">{description}</div>}
      {children}
    </div>
  );
}

export function Timeline({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("kosmo-timeline my-2", className)}>{children}</div>;
}
