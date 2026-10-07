import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface ListGroupProps extends HTMLAttributes<HTMLDivElement> {
  flush?: boolean;
}

export function ListGroup({ className, flush, ...props }: ListGroupProps) {
  return (
    <div
      className={cn("list-group", flush && "list-group-flush", className)}
      {...props}
    />
  );
}

export interface ListGroupItemProps extends HTMLAttributes<HTMLDivElement> {
  active?: boolean;
  disabled?: boolean;
  action?: boolean;
}

export function ListGroupItem({
  className,
  active,
  disabled,
  action,
  ...props
}: ListGroupItemProps) {
  return (
    <div
      className={cn(
        "list-group-item",
        active && "active",
        disabled && "disabled",
        action && "list-group-item-action",
        className
      )}
      {...props}
    />
  );
}
