"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface AccordionContextType {
  activeItem: string | null;
  toggleItem: (value: string) => void;
}

const AccordionContext = createContext<AccordionContextType>({
  activeItem: null,
  toggleItem: () => {},
});

export interface AccordionProps {
  children: ReactNode;
  defaultValue?: string | null;
  className?: string;
}

export function Accordion({ children, defaultValue = null, className }: AccordionProps) {
  const [activeItem, setActiveItem] = useState<string | null>(defaultValue ?? null);

  const toggleItem = (value: string) => {
    setActiveItem((prev) => (prev === value ? null : value));
  };

  return (
    <AccordionContext.Provider value={{ activeItem, toggleItem }}>
      <div className={cn("accordion", className)}>{children}</div>
    </AccordionContext.Provider>
  );
}

export interface AccordionItemProps {
  value: string;
  children: ReactNode;
  className?: string;
}

export function AccordionItem({ value, children, className }: AccordionItemProps) {
  return (
    <div className={cn("accordion-item", className)} data-value={value}>
      {children}
    </div>
  );
}

export interface AccordionTriggerProps {
  value: string;
  children: ReactNode;
  className?: string;
}

export function AccordionTrigger({ value, children, className }: AccordionTriggerProps) {
  const { activeItem, toggleItem } = useContext(AccordionContext);
  const isOpen = activeItem === value;

  return (
    <h2 className="accordion-header">
      <button
        type="button"
        className={cn("accordion-button", !isOpen && "collapsed", className)}
        aria-expanded={isOpen}
        onClick={() => toggleItem(value)}
      >
        {children}
      </button>
    </h2>
  );
}

export interface AccordionContentProps {
  value: string;
  children: ReactNode;
  className?: string;
}

export function AccordionContent({ value, children, className }: AccordionContentProps) {
  const { activeItem } = useContext(AccordionContext);
  const isOpen = activeItem === value;

  if (!isOpen) return null;

  return (
    <div className={cn("accordion-collapse collapse show", className)}>
      <div className="accordion-body">{children}</div>
    </div>
  );
}
