/**
 * The assistant panel's integration surface.
 *
 * The page bridge itself (public/fleet-assist.js) and its two React adapters
 * (components/shell/AssistBridge*.tsx) are vendored from the fleet's assistant
 * kit and kept in step with the hub's copy, so what a paired session may read,
 * click or type is decided there, once, for every repo that vendors it. What
 * this file covers is the half that is ours: that the root layout mounts the
 * element exactly once, with this repo's name, that a production build mounts
 * nothing at all, and that the router handed over for navigation is the App
 * Router.
 */
import { render } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RootLayout from '@/app/layout'
import AssistBridgeNext from '@/components/shell/AssistBridgeNext'

// One router object for the whole file, as `useRouter` returns in the app: the
// adapter memoises its `navigate` on it.
const { router } = vi.hoisted(() => ({ router: { push: vi.fn() } }))

vi.mock('next/navigation', () => ({
  usePathname: () => '/analysis',
  useRouter: () => router,
}))

const PAYLOAD = 'script[src="/fleet-assist.js"]'

describe('AssistBridgeNext', () => {
  beforeEach(() => {
    router.push.mockClear()
    document.head.querySelectorAll(PAYLOAD).forEach((s) => s.remove())
    delete (window as unknown as Record<string, unknown>).FleetAssist
  })

  it('renders nothing and loads nothing when it is not enabled', () => {
    const { container } = render(
      <AssistBridgeNext enabled={false} repo="bamr87/law-ai" />,
    )

    expect(container).toBeEmptyDOMElement()
    expect(document.querySelector('fleet-assist')).toBeNull()
    // The payload is 67 kB of developer tooling: off means not even requested.
    expect(document.head.querySelector(PAYLOAD)).toBeNull()
  })

  it('renders the element once when enabled, with the repo and the route', () => {
    const { container } = render(
      <AssistBridgeNext enabled repo="bamr87/law-ai" />,
    )
    const tags = container.querySelectorAll('fleet-assist')

    expect(tags).toHaveLength(1)
    // The repo is what tells a session where "fix this heading" has to go.
    expect(tags[0].getAttribute('repo')).toBe('bamr87/law-ai')
    expect(tags[0].getAttribute('branch')).toBe('main')
    expect(tags[0].getAttribute('route')).toBe('/analysis')
    expect(tags[0].getAttribute('framework')).toBe('nextjs')
    // This app has no `basePath`; a `base` here would make the payload strip a
    // prefix that no address carries.
    expect(tags[0].hasAttribute('base')).toBe(false)
  })

  it('loads the vendored payload from the root, once, across remounts', () => {
    const first = render(<AssistBridgeNext enabled repo="bamr87/law-ai" />)
    first.unmount()
    render(<AssistBridgeNext enabled repo="bamr87/law-ai" />)

    expect(document.head.querySelectorAll(PAYLOAD)).toHaveLength(1)
  })

  it('hands the App Router over, so a session changes route without a page load', () => {
    const configure = vi.fn()
    ;(window as unknown as Record<string, unknown>).FleetAssist = { configure }

    render(<AssistBridgeNext enabled repo="bamr87/law-ai" />)

    expect(configure).toHaveBeenCalledTimes(1)
    const { navigate } = configure.mock.calls[0][0] as {
      navigate: (path: string) => void
    }
    navigate('/graph')
    expect(router.push).toHaveBeenCalledWith('/graph')
    // Already loaded, so nothing is fetched a second time.
    expect(document.head.querySelector(PAYLOAD)).toBeNull()
  })
})

/**
 * The mount itself. `renderToString` over the real root layout, the way
 * `AppShellServerLayout.test.tsx` asserts the shell's first paint: it is the
 * markup the server sends, before any effect has run.
 */
describe('the root layout', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  function serverHtml(): string {
    return renderToString(
      <RootLayout>
        <p>PAGE</p>
      </RootLayout>,
    )
  }

  it('mounts the assistant panel exactly once outside production', () => {
    const html = serverHtml()

    expect(html.match(/<fleet-assist\b/g) ?? []).toHaveLength(1)
    expect(html).toMatch(/<fleet-assist\b[^>]*\brepo="bamr87\/law-ai"/)
  })

  it('mounts nothing in a production build', () => {
    vi.stubEnv('NODE_ENV', 'production')
    const html = serverHtml()

    expect(html).not.toContain('fleet-assist')
    // The feedback widget is for visitors, and stays.
    expect(html).toContain('<fleet-feedback')
  })
})
