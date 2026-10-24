# Enterprise App Shell + Scoped Settings — Next.js Architecture

> A generic Next.js design for an enterprise app shell over hierarchical, inheritable settings scopes — the essay spec 040 adapted, not a plan to implement as written.

> **Law AI adaptation:** [specs/040-app-shell](../specs/040-app-shell/spec.md) is what
> shipped. This essay stays the generic design. 040 maps it onto the locked
> stack (Django later, no Drizzle/shadcn/Radix; instance-only live scope per
> spec 036 NG3). Do not implement §6's stack table as written.

A plan for a Next.js (App Router) implementation of an enterprise application shell — nav rail, contextual sidebar, inspector panel — sitting on top of a hierarchical scope model where settings inherit down the tree and can be overridden or locked at each level.

---

## 1. The core idea

Two systems that are usually conflated, and shouldn't be:

| System | Owns | Fails when |
|---|---|---|
| **App shell** | Layout, navigation, panel orchestration, URL ↔ context | It knows about business modules |
| **Scope + settings engine** | Hierarchy, inheritance, overrides, locks, effective values, authz | It knows about React |

Everything else is a **module** that registers itself with both. Build the shell so a module can be added by dropping in one file that declares its nav entry, its routes, and its settings schema — nothing in the shell should ever be edited to add a feature.

---

## 2. Scope model

### 2.1 Hierarchy

Pick your levels and freeze them early; this is the decision everything else inherits.

```
Instance (global defaults, shipped + admin-editable)
└── Organization / Tenant
    └── Workspace / Team
        └── Project / Environment
            └── User (personal preferences, only for user-scoped keys)
```

Two viable modelling strategies:

- **Fixed depth** (recommended if levels are named and finite). Explicit FK columns, explicit routes, simplest queries, best type safety.
- **Arbitrary depth** (folder-like nesting, as in GCP resource hierarchy). Use a materialized path (`ltree` in Postgres) or a closure table. More flexible, more work.

Model the scope as a **single polymorphic table** either way. A settings resolver that has to branch on scope type is a resolver you'll rewrite.

```sql
create table scope (
  id           uuid primary key,
  type         scope_type not null,       -- 'instance'|'org'|'team'|'project'|'user'
  parent_id    uuid references scope(id),
  slug         text not null,
  name         text not null,
  path         ltree not null,            -- e.g. root.acme.platform.api
  depth        int  not null,
  unique (parent_id, slug)
);
create index on scope using gist (path);
```

### 2.2 Setting definitions (the registry)

Definitions live in code, not the database. The database stores *values only*. This gives you typed access, compile-time safety, migrations that are just code changes, and a UI that can be generated rather than hand-built.

```ts
// modules/security/settings.ts
export const mfaRequired = defineSetting({
  key: 'security.mfa.required',
  label: 'Require multi-factor authentication',
  help: 'Members must complete a second factor at sign-in.',
  schema: z.boolean(),
  default: false,
  settableAt: ['instance', 'org', 'team'],   // levels allowed to hold a value
  lockable: true,                            // may an ancestor prevent overrides?
  permission: 'settings.security.write',
  audit: true,
});
```

```sql
create table setting_value (
  scope_id   uuid not null references scope(id) on delete cascade,
  key        text not null,
  value      jsonb not null,
  locked     boolean not null default false,   -- descendants may not override
  updated_by uuid not null,
  updated_at timestamptz not null default now(),
  primary key (scope_id, key)
);
```

### 2.3 Resolution — the part that matters

The resolved value is the **effective setting**. The rule:

1. Walk the ancestor chain from root to the target scope.
2. The deepest scope holding a value wins…
3. …unless a **shallower** scope holds a value with `locked = true`, in which case the nearest locked ancestor wins and every descendant is read-only.
4. If nothing is set, fall back to the definition's `default`.

Return provenance, never a bare value:

```ts
type Effective<T> = {
  value: T;
  source: { scopeId: string; scopeName: string; type: ScopeType } | 'default';
  isInherited: boolean;
  locked: boolean;
  lockedBy?: { scopeId: string; scopeName: string };
  canOverride: boolean;     // combines lock state + caller's permissions
};
```

One query for the whole ancestor chain, resolved in SQL:

```sql
with chain as (
  select id, depth from scope
  where path @> (select path from scope where id = $1)
)
select distinct on (sv.key)
       sv.key, sv.value, sv.locked, sv.scope_id, c.depth
from   setting_value sv
join   chain c on c.id = sv.scope_id
where  sv.key = any($2)
order  by sv.key,
          -- locked ancestors outrank deeper values
          sv.locked desc, c.depth desc;
```

Write this resolver once, unit-test it hard (inheritance, override, lock above override, lock below lock, missing default, type drift), and treat it as the load-bearing wall of the whole system. Everything else is presentation.

### 2.4 Caching and invalidation

Read settings on the server, cache per scope, and invalidate by ancestor:

```ts
const getEffectiveSettings = (scopeId: string, keys: string[]) =>
  unstable_cache(
    () => resolver.resolve(scopeId, keys),
    ['settings', scopeId, keys.join(',')],
    // tag with every ancestor id so a write at any level busts descendants
    { tags: ancestorIds.map((id) => `settings:${id}`) },
  )();
```

On write: `revalidateTag('settings:' + writtenScopeId)`. Because each descendant's cache entry is tagged with all its ancestors, a change at the org level correctly invalidates every project beneath it without you enumerating them.

---

## 3. Authorization

Same shape as settings — this is not a coincidence, and you should reuse the traversal code.

- Roles are granted **at a scope** and inherit downward (`role_assignment(scope_id, principal_id, role)`).
- **Effective permissions** = union of all roles granted on the ancestor chain.
- Guard in three places, not one: middleware (cheap redirect for unauthenticated),
a server-side `requirePermission(scopeId, perm)` in every server action and route handler (the real boundary), and the UI (disable + explain, never merely hide).

Never trust the scope in the URL. Resolve `scopeSlug → scopeId` and check membership on every request; a scope switcher is an IDOR vector wearing a nice dropdown.

---

## 4. Next.js structure

### 4.1 Routes: scope belongs in the URL

The URL is the single source of truth for "where am I". Deep links, back button, and server-side data loading all fall out of this for free.

```
app/
  (app)/
    layout.tsx                    # AppShell: masthead + nav rail + slots
    @sidebar/
      default.tsx                 # contextual/secondary nav
    @inspector/
      default.tsx                 # right panel — renders null when unused
    o/[orgSlug]/
      layout.tsx                  # loads org scope, seeds ScopeContext
      page.tsx
      settings/
        layout.tsx                # settings tree in @sidebar
        [section]/page.tsx
      p/[projectSlug]/
        layout.tsx
        settings/[section]/page.tsx
```

Use **parallel routes** (`@sidebar`, `@inspector`) so each region resolves its own data and streams independently — the main content doesn't wait on the nav tree, and vice versa. Use **intercepting routes** for panels that should be deep-linkable but open as an overlay (e.g. `/(.)members/[id]` renders in the inspector, direct navigation renders a full page).

For arbitrary-depth hierarchies, swap the explicit segments for `s/[...scopePath]/` and resolve the path server-side. You lose a little type safety; you gain unbounded nesting.

### 4.2 Server/client boundary

- Layouts, settings pages, resolvers: **Server Components**. Settings data never needs to ship a client-side store.
- Interactive shell pieces (rail collapse, panel toggle, command palette, form fields): small client components, leaf-level.
- Mutations: **server actions** wrapped in a single `defineSettingAction` helper that does
permission check → Zod parse against the definition schema → lock check → write → audit → `revalidateTag`. Every setting write goes through this one door.
- Panel open/closed state lives in `searchParams`, not React state, so the shell is linkable and survives refresh.

### 4.3 Module registration

```ts
// modules/billing/index.ts
export default defineModule({
  id: 'billing',
  nav: {
    label: 'Billing',
    icon: CreditCard,
    href: (s) => `/o/${s.orgSlug}/billing`,
    visibleAt: ['org'],
    permission: 'billing.read',
  },
  settingsSections: [billingGeneral, billingLimits],
  settings: [invoiceEmail, seatLimit, ...],
});
```

The rail, the settings tree, the command palette, and the settings registry are all built by folding over the module list at boot. Adding a module never touches shell code.

---

## 5. Component inventory

| Component | Role | Notes |
|---|---|---|
| `AppShell` | Grid owner: masthead / rail / sidebar / content / inspector | CSS grid with named areas; the only place layout math lives |
| `Masthead` | Brand, `ScopeSwitcher`, search, account menu | |
| `ScopeSwitcher` | Changes context → changes URL | Searchable, recent scopes, shows full path breadcrumb |
| `NavRail` | Icon-only primary nav, collapsible | Tooltip on collapse; `aria-current="page"` |
| `ContextSidebar` | Secondary nav / settings tree | Renders in `@sidebar`; module-driven |
| `InspectorPanel` | Properties / help / activity, tabbed | `@inspector` slot; renders `null` when empty so the grid collapses |
| `SettingField` | **The important one** — see below | Generated from the definition |
| `InheritanceBadge` | "Inherited from Acme Corp" / "Locked by Acme Corp" | Clickable → navigates to the source scope |
| `OverrideControl` | Explicit "Override for this project" / "Reset to inherited" | Override is a deliberate act, never implicit |
| `ScopeBreadcrumb` | Full ancestor path, each segment navigable | |
| `AuditTrail` | Who changed what, where, when | Feeds the inspector's Activity tab |

### `SettingField` contract

This component is where scoped settings live or die. Given a definition and an `Effective<T>`, it renders the control plus its provenance, and it never shows a value without saying where that value came from:

```
┌─────────────────────────────────────────────────────────┐
│ Require multi-factor authentication            [ ●  ]   │
│ Members must complete a second factor at sign-in.       │
│ ⤷ Inherited from Acme Corp · Override for this project  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Require multi-factor authentication            [ ●  ]   │  ← control disabled
│ Members must complete a second factor at sign-in.       │
│ 🔒 Locked by Acme Corp · Contact an org admin to change │
└─────────────────────────────────────────────────────────┘
```

Three states, three distinct treatments: **set here** (plain, with a "reset to inherited" affordance), **inherited** (muted value + source link + override action), **locked** (disabled + lock source + who to ask). A silently-resolved value with no provenance is the single most common failure of scoped-settings UIs — the user cannot tell why a toggle is off, and support tickets follow.

---

## 6. Stack

| Concern | Choice | Why |
|---|---|---|
| Framework | Next.js App Router | Parallel/intercepting routes map onto shell regions directly |
| Primitives | Radix UI or Base UI (via shadcn/ui) | Unstyled, accessible, ownable source |
| Styling | Tailwind + CSS variables for theming | Per-tenant theming needs runtime vars, not build-time |
| DB access | Drizzle (or Prisma) + Postgres | Recursive CTEs and `ltree` are the reason for Postgres here |
| Validation | Zod, shared between definition, form, and server action | One schema, three consumers |
| Forms | react-hook-form + `zodResolver` | Field-level dirty state matters for override UX |
| Actions | next-safe-action or a thin custom wrapper | Typed errors, consistent permission gate |
| Testing | Vitest for the resolver, Playwright for shell + inheritance flows | Resolver tests are the highest-value tests you will write |

---

## 7. Delivery plan

**Phase 0 — Decide (½ day).** Fixed vs arbitrary depth. Which levels. Which settings are lockable. Write these down; they're expensive to change later.

**Phase 1 — Scope engine (3–5 days).** Schema, seed data, ancestor queries, resolver, `Effective<T>`, exhaustive unit tests. No UI at all. Ship when the test suite covers inherit / override / lock-above / lock-below / default-fallback / type-drift.

**Phase 2 — Shell (3–5 days).** `AppShell` grid, masthead, rail, `@sidebar`/`@inspector` slots, `ScopeSwitcher`, breadcrumb. Hardcoded nav. Keyboard nav and focus management now, not later — retrofitting focus order into a four-region shell is miserable.

**Phase 3 — Module registry (2–3 days).** `defineModule`, `defineSetting`, fold modules into rail + settings tree. Port the hardcoded nav to registry-driven.

**Phase 4 — Generated settings UI (3–5 days).** `SettingField` and friends, forms generated from definitions, server actions with the single write path, optimistic update + revalidate.

**Phase 5 — Authz + locks (2–4 days).** Role assignment, effective permissions, lock UI, disabled-with-explanation states everywhere.

**Phase 6 — Audit + inspector (2–3 days).** Change log, diff view, activity tab, "inherited from" links that navigate to the source scope.

**Phase 7 — Hardening.** Cache tags and invalidation under load, prefetching on rail hover, command palette (⌘K over modules + settings + scopes), reduced-motion, mobile: rail becomes a drawer, inspector becomes a sheet.

---

## 8. Traps worth naming in advance

1. **Resolving on the client.** Ship effective values from the server. A client-side settings store will drift, and it leaks the shape of scopes the user can't see.
2. **Hiding instead of disabling.** A control that vanishes teaches nothing. Disable it and say who can change it.
3. **Overrides that happen by typing.** Focusing an inherited field must not silently create an override row. Require an explicit action, and offer "reset to inherited" as its inverse.
4. **Unbounded ancestor queries.** One recursive CTE per request, not one query per level.
5. **Cache keyed only by the current scope.** If descendants aren't tagged with their ancestors, an org-level change goes unnoticed by every project below it.
6. **A settings table with a column per setting.** Every new setting becomes a migration. Key/value + a code registry keeps the schema stable.
7. **Deleting a scope.** Decide now: cascade values, or orphan and archive? Audit history usually needs to survive the scope it describes.
8. **Type drift.** A stored `jsonb` value may no longer parse against a changed schema. Parse on read, fall back to the default, and log — never crash the settings page.

---

## 9. Working with AI on this build

- **Generate the resolver's test table before the resolver.** Inheritance rules are a truth table; hand the model the table and ask for the implementation, not the reverse.
- **Give the model the definition file as the contract.** Once `defineSetting` exists, "add a
data-retention setting at org and project level, lockable" is a one-shot prompt with a predictable diff.
- **Ask for the failure states first.** Locked, inherited, no-permission, and parse-failure renderings are the ones that get skipped when you prompt for the happy path.
- **Keep the shell out of feature prompts.** If a prompt about billing requires editing `AppShell`, the registry abstraction has leaked and it's worth fixing before continuing.
