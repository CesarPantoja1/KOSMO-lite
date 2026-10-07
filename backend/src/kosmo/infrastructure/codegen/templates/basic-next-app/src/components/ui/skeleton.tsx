import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  width?: string | number;
  height?: string | number;
  circle?: boolean;
}

export function Skeleton({
  width,
  height = "1rem",
  circle = false,
  className,
  style,
  ...props
}: SkeletonProps) {
  const customStyle = {
    width: typeof width === "number" ? `${width}px` : width,
    height: typeof height === "number" ? `${height}px` : height,
    ...style,
  };

  return (
    <div
      className={cn(
        "kosmo-skeleton",
        circle && "rounded-circle",
        className
      )}
      style={customStyle}
      aria-hidden="true"
      {...props}
    />
  );
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("card p-3 d-flex flex-column gap-3", className)}>
      <div className="d-flex align-items-center gap-3">
        <Skeleton circle width={40} height={40} />
        <div className="d-flex flex-column gap-2 flex-grow-1">
          <Skeleton width="60%" height={14} />
          <Skeleton width="40%" height={10} />
        </div>
      </div>
      <Skeleton width="100%" height={20} />
      <Skeleton width="80%" height={14} />
    </div>
  );
}
