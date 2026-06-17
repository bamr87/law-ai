import { Button } from './Button'
import { Select } from './form'

/**
 * EDGAR `TablePager` — shared prev/next pagination + optional rows-per-page
 * select for any data list/table.
 */
export function Pager({
  page,
  totalPages,
  totalCount,
  onPageChange,
  pageSize,
  pageSizeOptions = [25, 50, 100, 200],
  onPageSizeChange,
  disabled = false,
}: {
  page: number
  totalPages: number
  totalCount?: number
  onPageChange: (page: number) => void
  pageSize?: number
  pageSizeOptions?: number[]
  onPageSizeChange?: (size: number) => void
  disabled?: boolean
}) {
  const safeTotal = Math.max(1, totalPages)
  return (
    <div
      role="navigation"
      aria-label="Table pagination"
      className="flex flex-wrap items-center gap-2.5"
    >
      <Button
        variant="secondary"
        size="sm"
        disabled={disabled || page <= 1}
        onClick={() => onPageChange(Math.max(1, page - 1))}
      >
        Previous
      </Button>
      <span className="text-xs text-muted">
        Page {page} / {safeTotal}
        {totalCount != null ? ` · ${totalCount.toLocaleString()} total` : ''}
      </span>
      <Button
        variant="secondary"
        size="sm"
        disabled={disabled || page >= safeTotal}
        onClick={() => onPageChange(page + 1)}
      >
        Next
      </Button>
      {onPageSizeChange != null && pageSize != null && (
        <label className="ml-auto flex items-center gap-2 text-xs text-muted">
          Rows
          <Select
            value={pageSize}
            disabled={disabled}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            aria-label="Rows per page"
            className="h-8 w-20 py-1"
          >
            {pageSizeOptions.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </label>
      )}
    </div>
  )
}
