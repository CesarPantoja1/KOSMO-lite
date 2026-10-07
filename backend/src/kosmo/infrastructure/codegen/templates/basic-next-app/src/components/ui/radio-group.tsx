import { cn } from "@/lib/utils";

export interface RadioOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

export interface RadioGroupProps {
  name: string;
  options: RadioOption[];
  value?: string;
  onChange?: (value: string) => void;
  label?: string;
  inline?: boolean;
  className?: string;
}

export function RadioGroup({
  name,
  options,
  value,
  onChange,
  label,
  inline = false,
  className,
}: RadioGroupProps) {
  return (
    <div className={cn("d-flex flex-column gap-2", className)}>
      {label && <label className="form-label fw-semibold small mb-1">{label}</label>}
      <div className={cn("d-flex", inline ? "flex-row gap-3 flex-wrap" : "flex-column gap-2")}>
        {options.map((opt) => {
          const optId = `${name}-${opt.value}`;
          const isChecked = value === opt.value;

          return (
            <div key={opt.value} className="form-check">
              <input
                type="radio"
                id={optId}
                name={name}
                value={opt.value}
                checked={isChecked}
                disabled={opt.disabled}
                onChange={() => onChange?.(opt.value)}
                className="form-check-input"
              />
              <label htmlFor={optId} className="form-check-label user-select-none small fw-medium">
                {opt.label}
              </label>
              {opt.description && (
                <div className="form-text text-muted small mt-0">{opt.description}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
