import { useMemo, useState } from 'react'
import { sortRows } from '../lib/format'

export interface Column<T> {
  key: keyof T & string
  label: string
  numeric?: boolean
  render?: (row: T) => React.ReactNode
}

interface Props<T extends object> {
  rows: T[]
  columns: Column<T>[]
  pageSize?: number
  emptyMessage?: string
  caption?: string
}

/** Sortable, paginated, accessible data table. */
export default function DataTable<T extends object>({
  rows,
  columns,
  pageSize = 15,
  emptyMessage = 'No rows to display.',
  caption,
}: Props<T>) {
  const [sortKey, setSortKey] = useState<keyof T & string | null>(null)
  const [dir, setDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(0)

  const sorted = useMemo(() => {
    if (!sortKey) return rows
    return sortRows(
      rows as unknown as Record<string, unknown>[],
      sortKey,
      dir,
    ) as unknown as T[]
  }, [rows, sortKey, dir])
  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize))
  const current = Math.min(page, pageCount - 1)
  const visible = sorted.slice(current * pageSize, (current + 1) * pageSize)

  function toggleSort(key: keyof T & string) {
    if (sortKey === key) {
      setDir(dir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setDir('asc')
    }
    setPage(0)
  }

  if (rows.length === 0) {
    return <p className="empty-note">{emptyMessage}</p>
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        {caption && <caption className="visually-hidden">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                aria-sort={
                  sortKey === col.key
                    ? dir === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                className={col.numeric ? 'numeric' : undefined}
              >
                <button
                  type="button"
                  className="th-sort"
                  onClick={() => toggleSort(col.key)}
                >
                  {col.label}
                  <span aria-hidden="true">
                    {sortKey === col.key ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col.key} className={col.numeric ? 'numeric' : undefined}>
                  {col.render
                    ? col.render(row)
                    : String(
                        (row as Record<string, unknown>)[col.key] ?? '—',
                      )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pageCount > 1 && (
        <nav className="pagination" aria-label="Table pagination">
          <button
            type="button"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            ← Prev
          </button>
          <span>
            Page {current + 1} of {pageCount}
          </span>
          <button
            type="button"
            disabled={current >= pageCount - 1}
            onClick={() => setPage(current + 1)}
          >
            Next →
          </button>
        </nav>
      )}
    </div>
  )
}