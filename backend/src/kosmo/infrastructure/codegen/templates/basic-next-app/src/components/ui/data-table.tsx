"use client";

import { useState, useMemo, type ReactNode } from "react";
import { Search, ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyState } from "./empty-state";

export interface Column<T> {
  key: keyof T | string;
  header: string;
  render?: (item: T) => ReactNode;
  sortable?: boolean;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  searchKey?: keyof T | string;
  searchPlaceholder?: string;
  pageSize?: number;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  searchKey,
  searchPlaceholder = "Buscar registros...",
  pageSize = 10,
  emptyTitle = "Sin registros",
  emptyDescription = "No hay datos para mostrar con los filtros aplicados.",
  className,
}: DataTableProps<T>) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [currentPage, setCurrentPage] = useState(1);

  const filteredData = useMemo(() => {
    if (!search || !searchKey) return data;
    const q = search.toLowerCase();
    return data.filter((item) => {
      const val = item[searchKey as string];
      return String(val ?? "").toLowerCase().includes(q);
    });
  }, [data, search, searchKey]);

  const sortedData = useMemo(() => {
    if (!sortKey) return filteredData;
    return [...filteredData].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal === bVal) return 0;
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortOrder === "asc" ? aVal - bVal : bVal - aVal;
      }
      const comp = String(aVal).localeCompare(String(bVal));
      return sortOrder === "asc" ? comp : -comp;
    });
  }, [filteredData, sortKey, sortOrder]);

  const totalPages = Math.ceil(sortedData.length / pageSize) || 1;
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, currentPage, pageSize]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      if (sortOrder === "asc") setSortOrder("desc");
      else {
        setSortKey(null);
        setSortOrder("asc");
      }
    } else {
      setSortKey(key);
      setSortOrder("asc");
    }
  };

  return (
    <div className={cn("d-flex flex-column gap-3", className)}>
      {searchKey && (
        <div className="d-flex align-items-center justify-content-between gap-3">
          <div className="input-group" style={{ maxWidth: "320px" }}>
            <span className="input-group-text bg-white border-end-0">
              <Search size={16} className="text-muted" />
            </span>
            <input
              type="text"
              className="form-control border-start-0 ps-0 shadow-none small"
              placeholder={searchPlaceholder}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentPage(1);
              }}
            />
          </div>
          <span className="text-muted small">
            {sortedData.length} {sortedData.length === 1 ? "registro" : "registros"}
          </span>
        </div>
      )}

      <div className="table-responsive">
        <table className="table table-hover align-middle mb-0">
          <thead className="table-light">
            <tr>
              {columns.map((col) => {
                const keyStr = String(col.key);
                const isSorted = sortKey === keyStr;

                return (
                  <th
                    key={keyStr}
                    className={cn(
                      "small py-2 text-muted fw-semibold",
                      col.sortable && "user-select-none"
                    )}
                    style={{ cursor: col.sortable ? "pointer" : "default" }}
                    onClick={() => col.sortable && handleSort(keyStr)}
                  >
                    <div className="d-flex align-items-center gap-1">
                      <span>{col.header}</span>
                      {col.sortable && (
                        <span className="text-muted">
                          {isSorted ? (
                            sortOrder === "asc" ? (
                              <ChevronUp size={14} />
                            ) : (
                              <ChevronDown size={14} />
                            )
                          ) : (
                            <ChevronsUpDown size={14} opacity={0.4} />
                          )}
                        </span>
                      )}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {paginatedData.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="p-4 text-center">
                  <EmptyState title={emptyTitle} description={emptyDescription} />
                </td>
              </tr>
            ) : (
              paginatedData.map((row, idx) => (
                <tr key={(row as { id?: string | number }).id ?? idx}>
                  {columns.map((col) => {
                    const keyStr = String(col.key);
                    return (
                      <td key={keyStr} className="small py-2">
                        {col.render ? col.render(row) : String(row[keyStr] ?? "")}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="d-flex align-items-center justify-content-between pt-1">
          <span className="text-muted small">
            Página {currentPage} de {totalPages}
          </span>
          <div className="btn-group btn-group-sm">
            <button
              type="button"
              className="btn btn-outline-secondary"
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              Anterior
            </button>
            <button
              type="button"
              className="btn btn-outline-secondary"
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
