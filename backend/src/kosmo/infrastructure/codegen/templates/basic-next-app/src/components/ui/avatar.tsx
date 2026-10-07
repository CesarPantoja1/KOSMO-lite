import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type AvatarSize = "sm" | "md" | "lg" | "xl";

export interface AvatarProps extends HTMLAttributes<HTMLDivElement> {
  src?: string;
  alt?: string;
  fallback?: string;
  size?: AvatarSize;
  variant?: "primary" | "secondary" | "success" | "warning" | "danger" | "light";
}

const variantBgClasses = {
  primary: "bg-primary text-white",
  secondary: "bg-secondary text-white",
  success: "bg-success text-white",
  warning: "bg-warning text-dark",
  danger: "bg-danger text-white",
  light: "bg-light text-dark border",
} as const;

const sizePx = {
  sm: 32,
  md: 40,
  lg: 48,
  xl: 64,
} as const;

export function Avatar({
  src,
  alt = "",
  fallback = "U",
  size = "md",
  variant = "primary",
  className,
  ...props
}: AvatarProps) {
  const dimension = sizePx[size];

  return (
    <div
      className={cn(
        "rounded-circle d-inline-flex align-items-center justify-content-center overflow-hidden fw-semibold user-select-none",
        variantBgClasses[variant],
        className
      )}
      style={{ width: dimension, height: dimension, minWidth: dimension }}
      {...props}
    >
      {src ? (
        <img
          src={src}
          alt={alt}
          className="w-100 h-100 object-fit-cover"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).style.display = "none";
          }}
        />
      ) : (
        <span>{fallback.slice(0, 2).toUpperCase()}</span>
      )}
    </div>
  );
}
