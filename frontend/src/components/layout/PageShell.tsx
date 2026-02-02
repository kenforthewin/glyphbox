import type { ReactNode } from "react";

interface PageShellProps {
  children: ReactNode;
}

export function PageShell({ children }: PageShellProps) {
  return (
    <div className="min-h-screen bg-bg-primary font-sans">
      <div className="mx-auto max-w-[1600px] px-4 py-4">{children}</div>
    </div>
  );
}
