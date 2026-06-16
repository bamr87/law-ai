export type ClassValue = string | number | false | null | undefined

/** Join truthy class fragments into a single className string. */
export function cn(...parts: ClassValue[]): string {
  return parts.filter(Boolean).join(' ')
}
