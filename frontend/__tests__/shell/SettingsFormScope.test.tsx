/**
 * The scope chooser tells the truth about who may write (BL-20260906-73).
 *
 * `/settings` grew an "Instance defaults" option in BL-20260905-10, and the
 * server refuses that write for a non-staff caller — the row then stays local
 * to that browser and nothing on screen says so. The GET payload now names the
 * writable scopes, so the option can be an honest affordance rather than a
 * caveat in the help text.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import SettingsForm from '@/components/shell/SettingsForm'
import { server } from '@/mocks/server'
import { disableServerSync, hydrateSettingValues } from '@/lib/scope/store'

const VALUES_URL = 'http://localhost:8000/api/settings/values'

function instanceRadio(): HTMLInputElement {
  return screen.getByRole('radio', { name: /Instance defaults/ })
}

async function hydrateWith(writableScopes?: string[]): Promise<void> {
  server.use(
    http.get(VALUES_URL, () =>
      HttpResponse.json({
        scopes: ['instance:local', 'user:7'],
        ...(writableScopes ? { writableScopes } : {}),
        values: [],
      }),
    ),
  )
  await hydrateSettingValues()
}

beforeEach(() => {
  window.localStorage.clear()
  disableServerSync()
})

afterEach(() => {
  disableServerSync()
})

describe('the settings scope chooser', () => {
  it('disables the instance option when the server will not accept it', async () => {
    await hydrateWith(['user:7'])
    render(<SettingsForm />)

    await waitFor(() => expect(instanceRadio()).toBeDisabled())
    expect(instanceRadio()).not.toBeChecked()
    expect(screen.getByRole('radio', { name: /Your preferences/ })).toBeChecked()
    // The help text stops hedging and states the caller's own position.
    expect(screen.getByText(/Your account cannot set it/)).toBeInTheDocument()
  })

  it('leaves the instance option usable for a caller who may write it', async () => {
    await hydrateWith(['instance:local', 'user:7'])
    render(<SettingsForm />)

    await waitFor(() => expect(instanceRadio()).toBeEnabled())
    expect(screen.queryByText(/Your account cannot set it/)).toBeNull()
  })

  it('stays usable when the backend never answers the question', async () => {
    await hydrateWith()
    render(<SettingsForm />)

    await waitFor(() => expect(instanceRadio()).toBeEnabled())
  })
})
