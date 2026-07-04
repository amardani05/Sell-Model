import { ReactNode } from "react";

export interface Column<T> {
  key: string;
  label: ReactNode;
  render?: (row: T) => ReactNode;
  align?: "left" | "right";
}

export function DataTable<T>({ columns, rows, rowKey }: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, i: number) => string;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>{columns.map((c) => (
            <th key={c.key} style={{ textAlign: c.align ?? "left" }}>{c.label}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)}>
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align ?? "left" }}>
                  {c.render ? c.render(row) : String((row as any)[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
