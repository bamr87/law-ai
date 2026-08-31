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
}

export interface AppModule {
  id: string
  nav: ModuleNav
  sidebar?: ModuleSidebarLink[]
  inspectorTitle: string
  inspectorBody: string
  /** When true, inspector always includes the UPL banner. */
  upl: boolean
}

export function defineModule(mod: AppModule): AppModule {
  return mod
}
