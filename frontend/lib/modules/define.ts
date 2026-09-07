import type { SettingDefinition } from '@/lib/scope/types'

export interface ModuleNav {
  label: string
  short: string
  href: string
  /** Shown in the rail; keep to a short glyph or two letters. */
  glyph: string
}

export interface ModuleSidebarLink {
  href: string
  label: string
  /**
   * Layout rows contributed only while the user is on this sub-route. The
   * catalog already names the route, so scoping a row to it costs the shell
   * no new knowledge.
   */
  layout?: ModuleLayoutRow[]
}

/**
 * One row a module contributes to the masthead's Layout menu.
 *
 * A module owns parts of the screen the shell knows nothing about — the LSAT
 * section timer, the library's contents rail — and they need somewhere to be
 * shown and hidden. Declaring them here keeps the route names in the catalog,
 * which is the module registry, instead of in `LayoutMenu` (spec 040 kept
 * route names out of the shell; BL-20260905-07).
 */
export interface ModuleLayoutRow {
  /** Row id, unique within the menu. */
  id: string
  /** Menu label, in the imperative the rest of the menu uses. */
  label: string
  /** The persisted preference the row flips. */
  setting: SettingDefinition<boolean>
}

export interface AppModule {
  id: string
  nav: ModuleNav
  sidebar?: ModuleSidebarLink[]
  /** Layout rows shown anywhere in this module. */
  layout?: ModuleLayoutRow[]
  /**
   * Ids of the widgets this module docks into the shell's panels, resolved
   * through `components/shell/dockRegistry.ts`. Ids, not components: the
   * catalog is plain data a server component can import, and a `ComponentType`
   * would drag every module's client code in with it (BL-20260831-14).
   */
  dockWidgets?: string[]
  inspectorTitle: string
  inspectorBody: string
  /** When true, inspector always includes the UPL banner. */
  upl: boolean
}

export function defineModule(mod: AppModule): AppModule {
  return mod
}
