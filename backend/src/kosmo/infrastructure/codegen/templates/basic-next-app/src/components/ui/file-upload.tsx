"use client";

import { useState, useRef, type ChangeEvent, type DragEvent } from "react";
import { UploadCloud, File as FileIcon, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface FileUploadProps {
  accept?: string;
  maxSizeMb?: number;
  multiple?: boolean;
  onFilesSelected?: (files: File[]) => void;
  label?: string;
  description?: string;
  className?: string;
}

export function FileUpload({
  accept,
  maxSizeMb = 10,
  multiple = false,
  onFilesSelected,
  label = "Arrastra archivos aquí o haz clic para explorar",
  description,
  className,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const filesArray = Array.from(e.dataTransfer.files);
      setSelectedFiles((prev) => (multiple ? [...prev, ...filesArray] : filesArray));
      onFilesSelected?.(filesArray);
    }
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files);
      setSelectedFiles((prev) => (multiple ? [...prev, ...filesArray] : filesArray));
      onFilesSelected?.(filesArray);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => {
      const updated = prev.filter((_, i) => i !== index);
      onFilesSelected?.(updated);
      return updated;
    });
  };

  return (
    <div className={cn("d-flex flex-column gap-2", className)}>
      <div
        className={cn(
          "border border-2 border-dashed rounded-3 p-4 text-center user-select-none",
          isDragging ? "border-primary bg-primary bg-opacity-10" : "border-secondary-subtle bg-light bg-opacity-50"
        )}
        style={{ cursor: "pointer", transition: "all 0.15s ease" }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          className="d-none"
          onChange={handleChange}
        />
        <UploadCloud size={36} className="text-muted mb-2 mx-auto" />
        <div className="fw-semibold small text-dark">{label}</div>
        <div className="text-muted small mt-1">
          {description || `Archivos hasta ${maxSizeMb}MB`}
        </div>
      </div>

      {selectedFiles.length > 0 && (
        <ul className="list-group list-group-flush border rounded">
          {selectedFiles.map((file, idx) => (
            <li
              key={`${file.name}-${idx}`}
              className="list-group-item d-flex align-items-center justify-content-between py-2 px-3 small"
            >
              <div className="d-flex align-items-center gap-2 text-truncate">
                <FileIcon size={16} className="text-primary flex-shrink-0" />
                <span className="text-truncate">{file.name}</span>
                <span className="text-muted" style={{ fontSize: "0.75rem" }}>
                  ({(file.size / 1024).toFixed(1)} KB)
                </span>
              </div>
              <button
                type="button"
                className="btn btn-sm btn-link text-danger p-0 ms-2"
                onClick={(e) => {
                  e.stopPropagation();
                  removeFile(idx);
                }}
              >
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
