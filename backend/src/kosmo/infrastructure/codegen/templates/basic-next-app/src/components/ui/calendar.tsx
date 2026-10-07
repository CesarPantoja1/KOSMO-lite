"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CalendarEvent {
  id: string;
  date: string; // YYYY-MM-DD
  title: string;
  variant?: "primary" | "success" | "warning" | "danger" | "secondary";
}

export interface CalendarProps {
  events?: CalendarEvent[];
  selectedDate?: string;
  onSelectDate?: (date: string) => void;
  className?: string;
}

const DAYS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const MONTHS_ES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

export function Calendar({
  events = [],
  selectedDate,
  onSelectDate,
  className,
}: CalendarProps) {
  const [currentMonth, setCurrentMonth] = useState(() => new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(() => new Date().getFullYear());

  const prevMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear((y) => y - 1);
    } else {
      setCurrentMonth((m) => m - 1);
    }
  };

  const nextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear((y) => y + 1);
    } else {
      setCurrentMonth((m) => m + 1);
    }
  };

  const firstDayIndex = (new Date(currentYear, currentMonth, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

  const days: (number | null)[] = [];
  for (let i = 0; i < firstDayIndex; i++) {
    days.push(null);
  }
  for (let d = 1; d <= daysInMonth; d++) {
    days.push(d);
  }

  const formatDayKey = (day: number) => {
    const m = String(currentMonth + 1).padStart(2, "0");
    const d = String(day).padStart(2, "0");
    return `${currentYear}-${m}-${d}`;
  };

  const getEventsForDay = (day: number) => {
    const key = formatDayKey(day);
    return events.filter((e) => e.date === key);
  };

  const badgeVariants = {
    primary: "bg-primary text-white",
    success: "bg-success text-white",
    warning: "bg-warning text-dark",
    danger: "bg-danger text-white",
    secondary: "bg-secondary text-white",
  };

  return (
    <div className={cn("card p-3 shadow-sm", className)}>
      <div className="d-flex align-items-center justify-content-between mb-3">
        <h6 className="mb-0 fw-bold">
          {MONTHS_ES[currentMonth]} {currentYear}
        </h6>
        <div className="d-flex gap-1">
          <button
            type="button"
            onClick={prevMonth}
            className="btn btn-sm btn-light border p-1 d-flex align-items-center justify-content-center"
            aria-label="Mes anterior"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            onClick={nextMonth}
            className="btn btn-sm btn-light border p-1 d-flex align-items-center justify-content-center"
            aria-label="Mes siguiente"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <div className="table-responsive">
        <table className="table table-bordered text-center align-middle mb-0">
          <thead className="table-light">
            <tr>
              {DAYS_ES.map((d) => (
                <th key={d} className="small py-2 text-muted fw-semibold">
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: Math.ceil(days.length / 7) }).map((_, weekIndex) => (
              <tr key={weekIndex}>
                {days.slice(weekIndex * 7, weekIndex * 7 + 7).map((day, dIndex) => {
                  if (day === null) {
                    return <td key={`empty-${dIndex}`} className="bg-light bg-opacity-50" />;
                  }

                  const dayKey = formatDayKey(day);
                  const isSelected = selectedDate === dayKey;
                  const dayEvents = getEventsForDay(day);

                  return (
                    <td
                      key={dayKey}
                      className={cn(
                        "p-2 position-relative",
                        isSelected && "table-primary fw-bold"
                      )}
                      style={{ height: "60px", minWidth: "40px", cursor: onSelectDate ? "pointer" : "default" }}
                      onClick={() => onSelectDate?.(dayKey)}
                    >
                      <span className="small">{day}</span>
                      {dayEvents.length > 0 && (
                        <div className="d-flex flex-column gap-1 mt-1">
                          {dayEvents.slice(0, 2).map((ev) => (
                            <span
                              key={ev.id}
                              className={cn(
                                "badge text-truncate p-1 text-start",
                                badgeVariants[ev.variant || "primary"]
                              )}
                              style={{ fontSize: "0.65rem" }}
                              title={ev.title}
                            >
                              {ev.title}
                            </span>
                          ))}
                          {dayEvents.length > 2 && (
                            <span className="badge bg-light text-muted p-0" style={{ fontSize: "0.65rem" }}>
                              +{dayEvents.length - 2} más
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
