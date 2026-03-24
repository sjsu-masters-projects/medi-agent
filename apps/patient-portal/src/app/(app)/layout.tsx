"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

function NavItem({
  href,
  icon,
  label,
  active,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className="flex flex-col items-center gap-0.5 py-2 px-3 min-w-[52px]"
    >
      <span
        className="text-xl leading-none"
        style={{ color: active ? "var(--primary)" : "var(--text-muted)" }}
      >
        {icon}
      </span>
      <span
        className="text-[10px] font-medium"
        style={{ color: active ? "var(--primary)" : "var(--text-muted)" }}
      >
        {label}
      </span>
    </Link>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-shell flex flex-col min-h-dvh">
      {/* Page content */}
      <main className="flex-1 overflow-y-auto pb-20">{children}</main>

      {/* Bottom navigation */}
      <nav
        className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-[448px] flex items-center justify-around bg-white border-t z-50"
        style={{ borderColor: "#e2e8f0" }}
      >
        <NavItem href="/today" icon="🏠" label="Today" active={pathname === "/today"} />
        <NavItem href="/records" icon="📁" label="Records" active={pathname === "/records"} />

        {/* Center Chat FAB */}
        <Link
          href="/chat"
          className="flex items-center justify-center w-14 h-14 rounded-full shadow-lg -mt-5 text-2xl"
          style={{ background: "var(--primary)", color: "white" }}
        >
          💬
        </Link>

        <NavItem href="/visits" icon="📅" label="Visits" active={pathname === "/visits"} />
        <NavItem href="/profile" icon="👤" label="Profile" active={pathname === "/profile"} />
      </nav>
    </div>
  );
}
