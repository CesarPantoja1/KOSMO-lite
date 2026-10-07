import { type InputHTMLAttributes, forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  description?: string;
  isInvalid?: boolean;
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, label, description, isInvalid, id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id || generatedId;

    return (
      <div className={cn("form-check form-switch", className)}>
        <input
          ref={ref}
          type="checkbox"
          role="switch"
          id={inputId}
          className={cn("form-check-input", isInvalid && "is-invalid")}
          style={{ cursor: "pointer" }}
          {...props}
        />
        {label && (
          <label htmlFor={inputId} className="form-check-label user-select-none small fw-medium">
            {label}
          </label>
        )}
        {description && <div className="form-text text-muted small mt-0">{description}</div>}
      </div>
    );
  }
);

Switch.displayName = "Switch";
