import type { ReactNode } from "react";

export function generateStaticParams() {
  return [{ id: "shell" }];
}

export default function JobIdLayout({ children }: { children: ReactNode }) {
  return children;
}
