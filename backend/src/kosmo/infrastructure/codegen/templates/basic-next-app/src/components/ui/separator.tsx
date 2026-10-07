import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SeparatorProps {
  children?: ReactNode;
  orientation?: "horizontal" | "vertical";
  className?: string;
}

export function Separator({
  children,
  orientation = "horizontal",
  className,
}: SeparatorProps) {
  if (orientation === "vertical") {
    return (
      <div
        className={cn("vr align-self-stretch my-auto opacity-25", className)}
        role="separator"
        aria-orientation="vertical"
      />
    );
  }

  if (children) {
    return (
      <div className={cn("position-relative text-center my-3", className)} role="separator">
        <hr className="my-0 border-secondary-subtle" />
        <span className="position-absolute top-50 start-50 translate-middle bg-body px-3 text-muted small user-select-none">
          {children}
        </span>
      </div>
    );
  }

  return (
    <hr
      className={cn("my-3 border-secondary-subtle opacity-50", className)}
      role="separator"
    />
  );
}
