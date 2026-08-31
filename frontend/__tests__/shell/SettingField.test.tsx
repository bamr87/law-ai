import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SettingField from '@/components/shell/SettingField'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { showCitationCounts } from '@/lib/settings/catalog'
import { resolveEffective } from '@/lib/scope/resolver'
import SettingsForm from '@/components/shell/SettingsForm'

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
    fireEvent.click(
      screen.getByRole('button', { name: /Override for Law AI/ }),
    )
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
    const field = heading.parentElement?.parentElement?.parentElement as HTMLElement
    const citation = within(field).getByRole('switch')
    expect(citation).toBeDisabled()
    fireEvent.click(within(field).getByRole('button', { name: /Override for Law AI/ }))
    expect(citation).not.toBeDisabled()
    fireEvent.click(within(field).getByRole('button', { name: /Reset to inherited/ }))
    expect(citation).toBeDisabled()
  })
})
