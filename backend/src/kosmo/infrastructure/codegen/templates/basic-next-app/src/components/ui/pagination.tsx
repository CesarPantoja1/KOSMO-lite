import { cn } from "@/lib/utils";

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  className,
}: PaginationProps) {
  if (totalPages <= 1) return null;

  const pages: (number | string)[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (currentPage > 3) pages.push("...");
    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let i = start; i <= end; i++) pages.push(i);
    if (currentPage < totalPages - 2) pages.push("...");
    pages.push(totalPages);
  }

  return (
    <nav aria-label="Navegación de páginas" className={className}>
      <ul className="pagination pagination-sm mb-0">
        <li className={cn("page-item", currentPage <= 1 && "disabled")}>
          <button
            type="button"
            className="page-link"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            Anterior
          </button>
        </li>
        {pages.map((p, idx) => (
          <li
            key={`p-${idx}`}
            className={cn(
              "page-item",
              p === currentPage && "active",
              p === "..." && "disabled"
            )}
          >
            {p === "..." ? (
              <span className="page-link border-0">…</span>
            ) : (
              <button
                type="button"
                className="page-link"
                onClick={() => onPageChange(p as number)}
              >
                {p}
              </button>
            )}
          </li>
        ))}
        <li className={cn("page-item", currentPage >= totalPages && "disabled")}>
          <button
            type="button"
            className="page-link"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage >= totalPages}
          >
            Siguiente
          </button>
        </li>
      </ul>
    </nav>
  );
}
