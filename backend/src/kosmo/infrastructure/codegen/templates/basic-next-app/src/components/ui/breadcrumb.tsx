import Link from "next/link";
import { cn } from "@/lib/utils";

export interface BreadcrumbItem {
  label: string;
  href?: string;
  active?: boolean;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav aria-label="breadcrumb" className={className}>
      <ol className="breadcrumb mb-0 py-1">
        {items.map((item, index) => {
          const isLast = index === items.length - 1 || item.active;

          return (
            <li
              key={`${item.label}-${index}`}
              className={cn("breadcrumb-item small", isLast && "active")}
              aria-current={isLast ? "page" : undefined}
            >
              {isLast || !item.href ? (
                <span className={cn(isLast ? "text-dark fw-medium" : "text-muted")}>
                  {item.label}
                </span>
              ) : (
                <Link href={item.href} className="text-decoration-none text-muted">
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
