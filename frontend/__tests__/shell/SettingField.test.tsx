import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import SettingField from '@/components/shell/SettingField'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { railVisible, showCitationCounts } from '@/lib/settings/catalog'
import { resolveEffective } from '@/lib/scope/resolver'
import SettingsForm from '@/components/shell/SettingsForm'
import {
  disableServerSync,
  hydrateSettingValues,
  listSettingValues,
} from '@/lib/scope/store'
import { server } from '@/mocks/server'

/** The card a setting's heading sits in. */
function fieldFor(label: string): HTMLElement {
  const heading = screen.getByRole('heading', { name: label })
  return heading.parentElement?.parentElement?.parentElement as HTMLElement
}

describe('SettingField', () => {
  it('disables an inherited/default control until Override', () => {
    const effective = resolveEffective(
      showCitationCounts,
      [INSTANCE_SCOPE],
      [],
      true,
    )
    const onOverride = vi.fn()
    render(
      <SettingField
        def={showCitationCounts}
        effective={effective}
        target={INSTANCE_SCOPE}
        onOverride={onOverride}
        onReset={vi.fn()}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByRole('switch')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Override for Law AI/ }))
    expect(onOverride).toHaveBeenCalledTimes(1)
  })
})

describe('SettingsForm', () => {
  it('overrides then resets a boolean setting', () => {
    window.localStorage.clear()
    render(<SettingsForm />)
    const heading = screen.getByRole('heading', {
      name: 'Show citation counts on the graph',
    })
    const field = heading.parentElement?.parentElement
      ?.parentElement as HTMLElement
    const citation = within(field).getByRole('switch')
    expect(citation).toBeDisabled()
    fireEvent.click(
      within(field).getByRole('button', { name: /Override for Law AI/ }),
    )
    expect(citation).not.toBeDisabled()
    fireEvent.click(
      within(field).getByRole('button', { name: /Reset to inherited/ }),
    )
    expect(citation).toBeDisabled()
  })
})

describe('SettingsForm signed in (BL-20260905-10)', () => {
  async function signIn(userScopeId = 'user:7') {
    server.use(
      http.get('*/api/settings/values', () =>
        HttpResponse.json({
          scopes: [INSTANCE_SCOPE.id, userScopeId],
          values: [],
        }),
      ),
      http.put('*/api/settings/values/:scope/:key', () =>
        HttpResponse.json({ ok: true }),
      ),
      http.delete('*/api/settings/values/:scope/:key', () =>
        HttpResponse.json({ ok: true }),
      ),
    )
    await hydrateSettingValues()
  }

  beforeEach(() => {
    disableServerSync()
    window.localStorage.clear()
  })
  afterEach(() => {
    disableServerSync()
    window.localStorage.clear()
  })

  it('keeps an instance-only policy setting editable', async () => {
    // The user chain must not make a setting a user may not hold read-only:
    // `canOverride` follows the deepest *settable* scope, which for a policy
    // value is still the instance.
    await signIn()
    render(<SettingsForm />)
    const field = fieldFor('Show citation counts on the graph')
    expect(within(field).getByRole('switch')).toBeDisabled()
    fireEvent.click(
      within(field).getByRole('button', { name: /Override for Law AI/ }),
    )
    expect(within(field).getByRole('switch')).not.toBeDisabled()
    expect(
      listSettingValues().find((r) => r.key === showCitationCounts.key)
        ?.scopeId,
    ).toBe(INSTANCE_SCOPE.id)
  })

  it('writes a layout preference to the user, or to the instance on request', async () => {
    await signIn()
    render(<SettingsForm />)
    // Default: your own preferences.
    fireEvent.click(
      within(fieldFor(railVisible.label)).getByRole('button', {
        name: /Override for You/,
      }),
    )
    expect(
      listSettingValues().find((r) => r.key === railVisible.key)?.scopeId,
    ).toBe('user:7')

    // …and the instance default an admin seeds is still reachable, which is
    // the half of this item the user-scope move otherwise took away.
    fireEvent.click(screen.getByRole('radio', { name: /Instance defaults/ }))
    fireEvent.click(
      within(fieldFor(railVisible.label)).getByRole('button', {
        name: /Override for Law AI/,
      }),
    )
    expect(
      listSettingValues()
        .filter((r) => r.key === railVisible.key)
        .map((r) => r.scopeId)
        .sort(),
    ).toEqual([INSTANCE_SCOPE.id, 'user:7'])
  })

  it('offers no scope chooser when nobody is signed in', () => {
    render(<SettingsForm />)
    expect(
      screen.queryByRole('radio', { name: /Instance defaults/ }),
    ).toBeNull()
  })
})
