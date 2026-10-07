"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DropdownItem {
  id: string;
  label: string;
  icon?: ReactNode;
  variant?: "default" | "danger";
  disabled?: boolean;
  onClick: () => void;
}

export interface DropdownProps {
  label: ReactNode;
  items: DropdownItem[];
  variant?: "primary" | "secondary" | "outline" | "light";
  size?: "sm" | "md" | "lg";
  align?: "start" | "end";
  className?: string;
}

export function Dropdown({
  label,
  items,
  variant = "outline",
  size = "md",
  align = "start",
  className,
}: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const variantBtnClasses = {
    primary: "btn-primary",
    secondary: "btn-secondary",
    outline: "btn-outline-secondary",
    light: "btn-light border",
  };

  const sizeBtnClasses = {
    sm: "btn-sm",
    md: "",
    lg: "btn-lg",
  };

  return (
    <div ref={containerRef} className={cn("dropdown position-relative d-inline-block", className)}>
      <button
        type="button"
        className={cn(
          "btn d-inline-flex align-items-center gap-2",
          variantBtnClasses[variant],
          sizeBtnClasses[size]
        )}
        aria-expanded={isOpen}
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <span>{label}</span>
        <ChevronDown size={14} className={cn("transition-transform", isOpen && "rotate-180")} />
      </button>

      {isOpen && (
        <ul
          className={cn(
            "dropdown-menu show shadow-sm mt-1 position-absolute",
            align === "end" && "dropdown-menu-end"
          )}
          style={{ zIndex: 1020, display: "block" }}
        >
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={cn(
                  "dropdown-item small d-flex align-items-center gap-2 py-2",
                  item.variant === "danger" && "text-danger",
                  item.disabled && "disabled"
                )}
                disabled={item.disabled}
                onClick={() => {
                  item.onClick();
                  setIsOpen(false);
                }}
              >
                {item.icon && <span className="text-muted">{item.icon}</span>}
                <span>{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
