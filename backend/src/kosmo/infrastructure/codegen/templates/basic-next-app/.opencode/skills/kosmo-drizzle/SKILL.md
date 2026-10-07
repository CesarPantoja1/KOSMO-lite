---
name: kosmo-drizzle
description: Modelado y persistencia con Drizzle ORM sobre SQLite (better-sqlite3), tipado estricto y consultas seguras. Trigger: drizzle, db, database, schema, sqlite, query, orm.
---

# Drizzle ORM & Persistencia SQLite en KOSMO

Esta skill define las directrices y patrones para modelar esquemas y ejecutar consultas tipadas con Drizzle ORM y SQLite (`better-sqlite3`).

---

## 1. Definición de Esquemas Tipados (`src/db/schema.ts`)

Todos los esquemas de base de datos se declaran en `src/db/schema.ts` usando las funciones de `drizzle-orm/sqlite-core`:

```typescript
import { sqliteTable, text, integer, real } from "drizzle-orm/sqlite-core";

export const expenses = sqliteTable("expenses", {
  id: text("id").primaryKey(),
  description: text("description").notNull(),
  amount: real("amount").notNull(),
  category: text("category").notNull().default("general"),
  userId: text("user_id").notNull(),
  createdAt: integer("created_at", { mode: "timestamp" })
    .notNull()
    .$defaultFn(() => new Date()),
});

// Tipos inferidos automáticos para inserción y lectura
export type Expense = typeof expenses.$inferSelect;
export type NewExpense = typeof expenses.$inferInsert;
```

---

## 2. Consultas Tipadas con el Query Builder

Toda operación de lectura o escritura debe usar la instancia `db` tipada de `src/db/index.ts`.

### Inserción
```typescript
import { db } from "@/db";
import { expenses, type NewExpense, type Expense } from "@/db/schema";

export async function createExpense(data: NewExpense): Promise<Expense> {
  const [created] = await db.insert(expenses).values(data).returning();
  return created;
}
```

### Consultas con Filtros (`eq`, `and`, `gte`, etc.)
```typescript
import { eq, desc } from "drizzle-orm";
import { db } from "@/db";
import { expenses, type Expense } from "@/db/schema";

export async function getExpensesByUser(userId: string): Promise<Expense[]> {
  return db
    .select()
    .from(expenses)
    .where(eq(expenses.userId, userId))
    .orderBy(desc(expenses.createdAt));
}
```

### Actualización y Eliminación
```typescript
export async function updateExpenseAmount(id: string, newAmount: number): Promise<void> {
  await db
    .update(expenses)
    .set({ amount: newAmount })
    .where(eq(expenses.id, id));
}

export async function deleteExpense(id: string): Promise<void> {
  await db.delete(expenses).where(eq(expenses.id, id));
}
```

### Mutaciones con Server Actions y Revalidación de Rutas
Para interactuar con la UI de Next.js, las mutaciones se encapsulan en Server Actions (`"use server"`):

```typescript
// src/features/expenses/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { db } from "@/db";
import { expenses, type NewExpense } from "@/db/schema";

export async function createExpenseAction(data: NewExpense) {
  try {
    const [created] = await db.insert(expenses).values(data).returning();
    revalidatePath("/expenses");
    return { success: true, data: created };
  } catch (error) {
    return { success: false, error: (error as Error).message };
  }
}
```

### Semillas Automáticas para Catálogos Maestros (`ensureSeedData`)
Si la característica necesita datos maestros para operar (ej. catálogo de productos, categorías, tipos), auto-inserta datos si la tabla está vacía:

```typescript
export async function ensureSeedCatalog(): Promise<void> {
  const existing = await db.select().from(catalogTable).limit(1);
  if (existing.length === 0) {
    await db.insert(catalogTable).values([
      { id: "cat-1", name: "Recuerdos Marina", price: 25 },
      { id: "cat-2", name: "Tiburón de Peluche", price: 40 },
    ]);
  }
}
```

---

## 3. Reglas Innegociables de Persistencia

1. **Cero SQL Crudo (Raw SQL):** Prohibido el uso de `db.run(sql"...")` o consultas de texto concatenadas. Todas las consultas deben estar 100% tipadas mediante el query builder de Drizzle.
2. **Tipos Exportados:** Siempre exporta los tipos inferidos `$inferSelect` y `$inferInsert` junto a la definición de la tabla.
3. **Claves Primarias y Fechas:** Usa identificadores unívocos (`text("id").primaryKey()`) y marcas de tiempo estándar (`integer(..., { mode: "timestamp" })`).
4. **Relaciones Explícitas:** Cuando existan referencias entre tablas, utiliza `references(() => otherTable.id)`.
5. **Cero Mocks en Memoria:** Prohibido guardar datos de negocio en arrays (`let sales = []`) o estados simulados. Todo registro DEBE insertarse en SQLite.
6. **Límite de Importación de `@/db`:** `@/db` utiliza `better-sqlite3` (módulo nativo Node C++). NUNCA lo importes en componentes con directiva `'use client'` para evitar errores de compilación. Úsalo exclusivamente en Server Components, Server Actions (`"use server"`), y API Routes.

---

## 4. Anti-patrones de Base de Datos

| Anti-patrón | Riesgo | Solución |
|-------------|--------|----------|
| **Tipos manuales desincronizados** | Errores de sincronización esquema-código | Usar `typeof table.$inferSelect` y `$inferInsert` |
| **SQL sin tipar** | Inyecciones SQL y bugs en runtime | Usar operadores `eq`, `like`, `and` de Drizzle |
| **Conexiones directas a archivos SQLite en cada función** | Bloqueos y memory leaks | Importar el singleton `db` desde `@/db` |
| **Importar `@/db` en componentes de cliente (`'use client'`)** | Falla de empaquetado por módulos nativos C++ | Usar Server Actions (`"use server"`) en `actions.ts` |
| **Guardar en arrays en memoria o `useState` simulado** | Pérdida de datos al recargar o reiniciar app | Insertar y actualizar directamente en SQLite con Drizzle |
