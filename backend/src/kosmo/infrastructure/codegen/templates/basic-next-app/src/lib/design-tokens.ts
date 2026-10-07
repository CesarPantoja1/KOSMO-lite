export interface BrandTokens {
  personality: string;
  domain: string;
}

export interface ColorTokens {
  primary: string;
  primaryRgb: string;
  secondary: string;
  secondaryRgb: string;
  success: string;
  successRgb: string;
  warning: string;
  warningRgb: string;
  danger: string;
  dangerRgb: string;
  accent: string;
  accentRgb: string;
  bodyBg: string;
  cardBg: string;
  mutedBg: string;
  mutedText: string;
  border: string;
  text: string;
  textSecondary: string;
}

export interface TypographyTokens {
  fontFamily: string;
  fontHeading: string;
}

export interface ShapeTokens {
  radius: string;
  radiusSm: string;
  radiusLg: string;
  shadowSm: string;
  shadow: string;
  shadowLg: string;
}

export interface LayoutTokens {
  shell: "sidebar" | "top_nav" | "minimal";
  density: "compact" | "comfortable" | "spacious";
}

export interface DesignTokens {
  brand: BrandTokens;
  colors: ColorTokens;
  typography: TypographyTokens;
  shape: ShapeTokens;
  layout: LayoutTokens;
}

export const designTokens: DesignTokens = {
  brand: {
    personality: "profesional, confiable, moderno",
    domain: "general",
  },
  colors: {
    primary: "#0f766e",
    primaryRgb: "15, 118, 110",
    secondary: "#64748b",
    secondaryRgb: "100, 116, 139",
    success: "#16a34a",
    successRgb: "22, 163, 74",
    warning: "#d97706",
    warningRgb: "217, 119, 6",
    danger: "#dc2626",
    dangerRgb: "220, 38, 38",
    accent: "#0ea5e9",
    accentRgb: "14, 165, 233",
    bodyBg: "#f8fafc",
    cardBg: "#ffffff",
    mutedBg: "#f1f5f9",
    mutedText: "#64748b",
    border: "#e2e8f0",
    text: "#1e293b",
    textSecondary: "#475569",
  },
  typography: {
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
    fontHeading: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
  },
  shape: {
    radius: "0.5rem",
    radiusSm: "0.25rem",
    radiusLg: "0.75rem",
    shadowSm: "0 1px 2px rgba(0, 0, 0, 0.05)",
    shadow: "0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)",
    shadowLg: "0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04)",
  },
  layout: {
    shell: "sidebar",
    density: "comfortable",
  },
};
