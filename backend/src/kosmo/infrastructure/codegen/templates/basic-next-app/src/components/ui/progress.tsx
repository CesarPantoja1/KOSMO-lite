import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface ProgressProps extends HTMLAttributes<HTMLDivElement> {
  value: number; // 0 to 100
  max?: number;
  variant?: "primary" | "secondary" | "success" | "warning" | "danger" | "info";
  striped?: boolean;
  animated?: boolean;
  showLabel?: boolean;
  height?: number;
}

const variantClasses = {
  primary: "bg-primary",
  secondary: "bg-secondary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

export function Progress({
  value,
  max = 100,
  variant = "primary",
  striped = false,
  animated = false,
  showLabel = false,
  height = 8,
  className,
  ...props
}: ProgressProps) {
  const percentage = Math.min(100, Math.max(0, Math.round((value / max) * 100)));

  return (
    <div
      className={cn("progress", className)}
      role="progressbar"
      aria-valuenow={percentage}
      aria-valuemin={0}
      aria-valuemax={100}
      style={{ height: `${height}px` }}
      {...props}
    >
      <div
        className={cn(
          "progress-bar",
          variantClasses[variant],
          striped && "progress-bar-striped",
          animated && "progress-bar-animated"
        )}
        style={{ width: `${percentage}%` }}
      >
        {showLabel && height >= 14 && (
          <span className="small px-1" style={{ fontSize: "0.7rem" }}>
            {percentage}%
          </span>
        )}
      </div>
    </div>
  );
}
