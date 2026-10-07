---
name: kosmo-nextjs
description: Convenciones de Next.js 16 App Router, React 19, Server Components y manejo de APIs tipadas. Trigger: nextjs, next, react, component, page, layout, api route, server component.
---

# Next.js 16 App Router & React 19 en KOSMO

Esta skill define las directrices para el desarrollo de páginas, layouts, componentes interactivos y rutas de API en Next.js 16.

---

## 1. Server Components por Defecto

En Next.js 16 App Router, todos los componentes en `src/app/` son **Server Components** por defecto.

```tsx
// src/app/expenses/page.tsx (Server Component)
import { getExpensesByUser } from "@/db/queries/expenses";
import { ExpenseList } from "@/components/ExpenseList";

export default async function ExpensesPage() {
  // Obtención directa de datos en el servidor
  const expenses = await getExpensesByUser("usr_01");

  return (
    <main className="container mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Registro de Gastos</h1>
      <ExpenseList initialExpenses={expenses} />
    </main>
  );
}
```

---

## 2. Uso Restrictivo de `'use client'`

Solo se agrega la directiva `'use client'` en componentes de hoja pequeños ubicados en `src/components/` que requieran:
- Manejo de estado de cliente (`useState`, `useReducer`).
- Efectos y ciclo de vida del navegador (`useEffect`).
- Eventos de interacción del DOM (`onClick`, `onChange`, `onSubmit`).

```tsx
// src/components/ExpenseFilter.tsx (Client Component)
"use client";

import { useState } from "react";

interface ExpenseFilterProps {
  onFilterChange: (category: string) => void;
}

export function ExpenseFilter({ onFilterChange }: ExpenseFilterProps) {
  const [selected, setSelected] = useState("all");

  const handleChange = (cat: string) => {
    setSelected(cat);
    onFilterChange(cat);
  };

  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => handleChange("all")}
        className={selected === "all" ? "bg-primary text-white px-3 py-1 rounded" : "px-3 py-1"}
      >
        Todos
      </button>
    </div>
  );
}
```

---

---

## 3. Mutaciones con Server Actions (`"use server"`) y Revalidación (`revalidatePath`)

Para mutaciones de datos en formularios y acciones de usuario, usa **Server Actions**:
1. Declara la función en `src/features/<slug>/actions.ts` con la directiva `"use server"` al inicio.
2. La Server Action interactúa directamente con `db` de `@/db` para insertar o actualizar en SQLite.
3. Al terminar la mutación exitosamente, llama a `revalidatePath('/<slug>')` para refrescar los datos de la vista.
4. El componente interactivo de cliente (`'use client'`) importa e invoca la Server Action, manejando estados de carga y feedback de éxito/error.

```tsx
// src/features/ventas/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { db } from "@/db";
import { sales } from "@/db/schema";

export async function registerSaleAction(payload: {
  itemId: string;
  quantity: number;
  totalPrice: number;
}) {
  try {
    await db.insert(sales).values({
      id: crypto.randomUUID(),
      itemId: payload.itemId,
      quantity: payload.quantity,
      totalPrice: payload.totalPrice,
      createdAt: new Date(),
    });

    revalidatePath("/ventas");
    return { success: true };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
}
```

```tsx
// src/features/ventas/components/SaleForm.tsx
"use client";

import { useState, useTransition } from "react";
import { registerSaleAction } from "../actions";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";

export function SaleForm({ items }: { items: Array<{ id: string; name: string; price: number }> }) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await registerSaleAction({ itemId: items[0]?.id ?? "", quantity: 1, totalPrice: 25 });
      if (!res.success) {
        setError(res.error ?? "Error al registrar la venta.");
      }
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      {error && <Alert variant="danger">{error}</Alert>}
      <Button type="submit" disabled={isPending}>
        {isPending ? "Registrando..." : "Confirmar Venta"}
      </Button>
    </form>
  );
}
```

---

## 4. Rutas de API Estructuradas (`src/app/api/.../route.ts`)

Las rutas de API deben retornar `NextResponse.json` con códigos HTTP estándar y formato de respuesta estructurado:

```typescript
// src/app/api/expenses/route.ts
import { NextResponse } from "next/server";
import { getExpensesByUser } from "@/db/queries/expenses";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get("userId");

  if (!userId) {
    return NextResponse.json(
      { error: "Bad Request", detail: "El parámetro userId es obligatorio." },
      { status: 400 }
    );
  }

  const items = await getExpensesByUser(userId);
  return NextResponse.json({ data: items }, { status: 200 });
}
```

---

## 5. Estilos y Utilidades Bootstrap 5

1. Usa clases utilitarias y componentes de Bootstrap 5.
2. Para composición condicional de clases, usa `cn()` desde `@/lib/utils` (respaldado por `clsx`):
   ```tsx
   import { cn } from "@/lib/utils";

   export function Badge({ variant, className, children }: BadgeProps) {
     return (
       <span
         className={cn(
           "badge rounded-pill",
           variant === "success" && "bg-success-subtle text-success-emphasis border border-success-subtle",
           variant === "error" && "bg-danger-subtle text-danger-emphasis border border-danger-subtle",
           className
         )}
       >
         {children}
       </span>
     );
   }
   ```

---

## 6. Anti-patrones de Next.js Prohibidos

| Anti-patrón | Consecuencia | Corrección |
|-------------|--------------|------------|
| **Poner `'use client'` en `page.tsx` o `layout.tsx`** | Deshabilita Server-Side Rendering y optimizaciones | Mantener la página como Server Component y extraer componentes interactivos |
| **Importar `@/db` en componentes `'use client'`** | Falla de empaquetado en Turbopack/Webpack por módulo nativo `better-sqlite3` | Encapsular mutaciones en Server Actions (`"use server"`) en `actions.ts` |
| **Persistencia simulada en memoria o `useState`** | Datos se pierden al recargar; 0 registros reales guardados | Escribir en SQLite con Drizzle ORM a través de Server Actions |
| **`fetch()` a tus propias rutas API dentro de Server Components** | Overhead innecesario de red HTTP | Llamar directamente a la función de base de datos o servicio |
| **Respuestas de error con strings planos en APIs** | Dificulta parseo en frontend | Retornar JSON `{ error: string, detail?: string }` con status HTTP |
