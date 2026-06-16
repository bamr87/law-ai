import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { useId } from 'react'
import { cn } from '@/lib/cn'

const FIELD =
  'w-full rounded-lg border border-border bg-canvas-soft px-3 py-2 text-sm text-ink placeholder:text-subtle transition focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30 disabled:opacity-50'

/** Labelled wrapper for any control. */
export function Field({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label?: ReactNode
  hint?: ReactNode
  htmlFor?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      {label && (
        <label
          htmlFor={htmlFor}
          className="block text-xs font-medium text-muted"
        >
          {label}
        </label>
      )}
      {children}
      {hint && <p className="text-[11px] text-subtle">{hint}</p>}
    </div>
  )
}

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(FIELD, className)} />
}

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn(FIELD, 'resize-y', className)} />
}

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cn(FIELD, 'pr-8', className)}>
      {children}
    </select>
  )
}

/** Small inline search/filter input. */
export function SearchInput({
  label = 'Search',
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  const id = useId()
  return (
    <>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <input
        id={id}
        type="search"
        {...props}
        className={cn(
          'h-8 rounded-md border border-border bg-canvas-soft px-2.5 text-xs text-ink placeholder:text-subtle focus:border-brand focus:outline-none',
          className,
        )}
      />
    </>
  )
}
