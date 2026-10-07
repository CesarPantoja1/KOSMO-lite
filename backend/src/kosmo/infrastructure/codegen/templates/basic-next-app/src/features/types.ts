import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";

/**
 * Contrato de una feature implementada.
 *
 * Cada feature vive en `src/features/<slug>/` como un slice autocontenido:
 * `manifest.ts`, `logic.ts`, `components/` y su ruta en `src/app/<slug>/page.tsx`.
 *
 * Si la feature comparte entidades de negocio con otras características, estas
 * se ubican en `src/domain/<entidad>/`, permitiendo su reutilización sin acoplamiento inter-slice.
 */
export interface FeatureManifest {
  slug: string;
  title: string;
  description: string;
  route: string;
  icon?: LucideIcon | ComponentType<{ size?: number; className?: string }>;
  group?: string;
  actor?: string;
}

/**
 * Agrupación lógica de navegación por actor o dominio funcional.
 */
export interface FeatureGroup {
  label: string;
  features: FeatureManifest[];
}
