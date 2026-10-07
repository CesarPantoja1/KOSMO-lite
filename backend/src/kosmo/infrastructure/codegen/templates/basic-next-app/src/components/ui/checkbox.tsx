import { type InputHTMLAttributes, forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  description?: string;
  isInvalid?: boolean;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, description, isInvalid, id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id || generatedId;

    return (
      <div className={cn("form-check", className)}>
        <input
          ref={ref}
          type="checkbox"
          id={inputId}
          className={cn("form-check-input", isInvalid && "is-invalid")}
          {...props}
        />
        {label && (
          <label htmlFor={inputId} className="form-check-label user-select-none fw-medium small">
            {label}
          </label>
        )}
        {description && <div className="form-text text-muted small mt-0">{description}</div>}
      </div>
    );
  }
);

Checkbox.displayName = "Checkbox";
