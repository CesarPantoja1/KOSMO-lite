"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CommandItem {
  id: string;
  title: string;
  category?: string;
  description?: string;
  icon?: ReactNode;
  onSelect: () => void;
}

export interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  items: CommandItem[];
  placeholder?: string;
  className?: string;
}

export function CommandPalette({
  isOpen,
  onClose,
  items,
  placeholder = "Escribe para buscar o ejecutar una acción...",
  className,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        // Toggle or open
      }
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const filtered = items.filter(
    (item) =>
      item.title.toLowerCase().includes(query.toLowerCase()) ||
      item.description?.toLowerCase().includes(query.toLowerCase()) ||
      item.category?.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="modal d-block" tabIndex={-1} style={{ backgroundColor: "rgba(0,0,0,0.5)" }}>
      <div className={cn("modal-dialog modal-dialog-centered", className)} style={{ maxWidth: "560px" }}>
        <div className="modal-content shadow-lg border-0">
          <div className="modal-header border-bottom p-3">
            <div className="input-group">
              <span className="input-group-text bg-transparent border-0 pe-2">
                <Search size={18} className="text-muted" />
              </span>
              <input
                type="text"
                autoFocus
                className="form-control border-0 shadow-none ps-0"
                placeholder={placeholder}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn-close ms-2"
              aria-label="Cerrar"
              onClick={onClose}
            />
          </div>
          <div className="modal-body p-2" style={{ maxHeight: "360px", overflowY: "auto" }}>
            {filtered.length === 0 ? (
              <div className="p-4 text-center text-muted small">
                No se encontraron resultados para &quot;{query}&quot;
              </div>
            ) : (
              <div className="list-group list-group-flush">
                {filtered.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="list-group-item list-group-item-action border-0 rounded d-flex align-items-center justify-content-between p-2 my-1"
                    onClick={() => {
                      item.onSelect();
                      onClose();
                    }}
                  >
                    <div className="d-flex align-items-center gap-2">
                      {item.icon && <span className="text-muted">{item.icon}</span>}
                      <div>
                        <div className="fw-medium small text-dark">{item.title}</div>
                        {item.description && (
                          <div className="text-muted" style={{ fontSize: "0.75rem" }}>
                            {item.description}
                          </div>
                        )}
                      </div>
                    </div>
                    {item.category && (
                      <span className="badge bg-light text-muted border small">{item.category}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="modal-footer border-top py-2 px-3 justify-content-between text-muted small" style={{ fontSize: "0.75rem" }}>
            <span>Navega con las acciones</span>
            <span><kbd className="bg-light text-dark border px-1">ESC</kbd> para salir</span>
          </div>
        </div>
      </div>
    </div>
  );
}
