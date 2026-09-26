import type { ReactNode } from "react";

export interface StubPageProps {
  title: string;
  /** The backlog item that builds this screen, e.g. "CQ-025". */
  item: string;
  children?: ReactNode;
}

/** Placeholder for a route the foundation reserves for a later item. */
export function StubPage({ title, item, children }: StubPageProps) {
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-2 px-6 py-8">
      <h1 className="text-2xl font-semibold text-navy-900">{title}</h1>
      <p className="text-neutral-600">Built in {item}</p>
      {children}
    </main>
  );
}
