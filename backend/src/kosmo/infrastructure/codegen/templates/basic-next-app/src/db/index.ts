import Database from "better-sqlite3";
import { getTableColumns, getTableName, is } from "drizzle-orm";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { SQLiteTable } from "drizzle-orm/sqlite-core";
import fs from "node:fs";
import path from "node:path";
import * as schema from "./schema";

function openSqliteDatabase(): Database.Database {
  const rawPath =
    process.env.DATABASE_URL ||
    process.env.DATABASE_PATH ||
    path.join(process.cwd(), ".data", "sqlite.db");
  const cleanPath = rawPath.replace(/^file:\/\//, "").replace(/^file:/, "");

  try {
    const dir = path.dirname(cleanPath);
    if (dir && dir !== "." && !fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    return new Database(cleanPath);
  } catch (err) {
    console.warn(`[db] No se pudo abrir base de datos en '${cleanPath}':`, err);
    try {
      return new Database(":memory:");
    } catch (fallbackErr) {
      console.warn("[db] No se pudo abrir base de datos en memoria:", fallbackErr);
      throw err;
    }
  }
}

export function syncSchema(
  sqliteDb: Database.Database,
  schemaObject: Record<string, unknown>
): void {
  try {
    sqliteDb.pragma("journal_mode = WAL");
    sqliteDb.pragma("foreign_keys = ON");
  } catch (pragmaErr) {
    console.warn("[db] No se pudieron aplicar pragmas de SQLite:", pragmaErr);
  }

  for (const exported of Object.values(schemaObject)) {
    if (!exported || typeof exported !== "object") continue;
    try {
      if (is(exported, SQLiteTable) || (exported as { _?: { name?: string } })._?.name) {
        const table = exported as SQLiteTable;
        const tableName = getTableName(table);
        if (!tableName) continue;
        const columns = getTableColumns(table);

        const colDefs: string[] = [];
        for (const col of Object.values(columns)) {
          const sqlType = typeof col.getSQLType === "function" ? col.getSQLType() : "text";
          let def = `"${col.name}" ${sqlType}`;
          if (col.primary) {
            def += " PRIMARY KEY";
          } else if (col.notNull) {
            def += " NOT NULL";
          }
          colDefs.push(def);
        }

        if (colDefs.length > 0) {
          sqliteDb.exec(`CREATE TABLE IF NOT EXISTS "${tableName}" (${colDefs.join(", ")});`);

          try {
            const existingRows = sqliteDb.pragma(`table_info("${tableName}")`) as Array<{ name: string }>;
            const existingColNames = new Set(existingRows.map((r) => r.name));
            for (const col of Object.values(columns)) {
              if (!existingColNames.has(col.name)) {
                const sqlType = typeof col.getSQLType === "function" ? col.getSQLType() : "text";
                let def = `"${col.name}" ${sqlType}`;
                if (col.notNull) {
                  def += " DEFAULT ''";
                }
                sqliteDb.exec(`ALTER TABLE "${tableName}" ADD COLUMN ${def};`);
              }
            }
          } catch (migErr) {
            console.warn(`[db] No se pudo verificar table_info para '${tableName}':`, migErr);
          }
        }
      }
    } catch (tblErr) {
      console.warn("[db] Error al sincronizar tabla de schema:", tblErr);
    }
  }
}

export const sqlite = openSqliteDatabase();
syncSchema(sqlite, schema);
export const db = drizzle(sqlite, { schema });
