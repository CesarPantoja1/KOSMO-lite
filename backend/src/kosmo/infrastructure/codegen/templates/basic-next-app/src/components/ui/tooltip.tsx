"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  position?: "top" | "bottom" | "left" | "right";
  className?: string;
}

export function Tooltip({
  content,
  children,
  position = "top",
  className,
}: TooltipProps) {
  const [visible, setVisible] = useState(false);

  const positionStyles = {
    top: { bottom: "100%", left: "50%", transform: "translateX(-50%)", marginBottom: "6px" },
    bottom: { top: "100%", left: "50%", transform: "translateX(-50%)", marginTop: "6px" },
    left: { right: "100%", top: "50%", transform: "translateY(-50%)", marginRight: "6px" },
    right: { left: "100%", top: "50%", transform: "translateY(-50%)", marginLeft: "6px" },
  };

  return (
    <div
      className={cn("position-relative d-inline-flex", className)}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <div
          role="tooltip"
          className="position-absolute bg-dark text-white rounded px-2 py-1 small shadow user-select-none text-nowrap pointer-events-none"
          style={{
            ...positionStyles[position],
            fontSize: "0.75rem",
            zIndex: 1080,
          }}
        >
          {content}
        </div>
      )}
    </div>
  );
}
