import nextConfig from 'eslint-config-next'

/**
 * Flat config for the static site, mirroring `frontend/eslint.config.mjs`
 * (BL-20260905-15).
 *
 * Until this file existed, `npm run lint` was an unconfigured `next lint` and
 * `npx eslint` refused to start, so the CI job for this package gated on
 * `tsc --noEmit` and vitest alone — nothing checked the React rules the
 * platform app is held to, even though the two share components by hand.
 */
const config = [
    ...nextConfig,
    {
        ignores: ['.next/**', 'node_modules/**', 'out/**', 'next-env.d.ts'],
    },
    {
        rules: {
            // Same demotion as the platform app: some components legitimately
            // set state from an effect (route change, measured layout).
            'react-hooks/set-state-in-effect': 'warn',
        },
    },
]

export default config
