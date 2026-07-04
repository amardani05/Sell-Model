import { ReactNode } from "react";
import { GLOSSARY } from "../lib/glossary";

// Inline hoverable definition. <Term id="ic" /> renders the glossary label with
// a dotted underline and shows the definition on hover; pass children to change
// the visible text while keeping the same definition.
export function Term({ id, children }: { id: keyof typeof GLOSSARY | string; children?: ReactNode }) {
  const entry = GLOSSARY[id as string];
  if (!entry) return <>{children ?? id}</>;
  return (
    <span className="term" tabIndex={0}>
      {children ?? entry.label}
      <span className="term-tip" role="tooltip">
        <strong>{entry.label}</strong>
        {entry.def}
      </span>
    </span>
  );
}
