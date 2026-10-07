"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard } from "lucide-react";

import { featureGroups, features } from "@/lib/feature-registry";
import { siteConfig } from "@/lib/site";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="app-sidebar d-none d-md-flex flex-column p-3">
      <Link
        href="/"
        className="d-flex align-items-center gap-2 mb-4 text-dark text-decoration-none px-2"
      >
        <span className="fw-bold fs-6 text-truncate">{siteConfig.name}</span>
      </Link>
      <hr className="my-2 border-secondary-subtle" />
      <nav className="nav flex-column gap-1 flex-grow-1" aria-label="Navegación lateral">
        <Link
          href="/"
          className={cn("app-sidebar-link", pathname === "/" && "active")}
          aria-current={pathname === "/" ? "page" : undefined}
        >
          <LayoutDashboard size={18} />
          <span>Inicio</span>
        </Link>

        {featureGroups.length > 0 ? (
          featureGroups.map((group) => (
            <div key={group.label} className="mt-3">
              <div className="small text-uppercase fw-semibold text-secondary px-2 mb-1" style={{ fontSize: "0.75rem" }}>
                {group.label}
              </div>
              <div className="nav flex-column gap-1">
                {group.features.map((feature) => {
                  const active = pathname === feature.route;
                  const Icon = feature.icon;
                  return (
                    <Link
                      key={feature.slug}
                      href={feature.route}
                      className={cn("app-sidebar-link", active && "active")}
                      aria-current={active ? "page" : undefined}
                    >
                      {Icon ? <Icon size={18} /> : null}
                      <span className="text-truncate">{feature.title}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))
        ) : (
          <>
            <div className="small text-uppercase fw-semibold text-secondary px-2 my-2" style={{ fontSize: "0.75rem" }}>
              Navegación
            </div>
            {features.map((feature) => {
              const active = pathname === feature.route;
              const Icon = feature.icon;
              return (
                <Link
                  key={feature.slug}
                  href={feature.route}
                  className={cn("app-sidebar-link", active && "active")}
                  aria-current={active ? "page" : undefined}
                >
                  {Icon ? <Icon size={18} /> : null}
                  <span className="text-truncate">{feature.title}</span>
                </Link>
              );
            })}
          </>
        )}
      </nav>
      <div className="pt-3 border-top border-secondary-subtle px-2">
        <p className="small text-muted mb-0" style={{ fontSize: "0.75rem" }}>
          {siteConfig.name}
        </p>
      </div>
    </aside>
  );
}
