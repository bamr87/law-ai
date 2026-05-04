import nextConfig from 'eslint-config-next'

const config = [
    ...nextConfig,
    {
        ignores: ['.next/**', 'node_modules/**', 'coverage/**', 'next-env.d.ts'],
    },
    {
        rules: {
            // React 19 best-practice rule (new in eslint-plugin-react-hooks 7);
            // demoted to a warning for legacy components that legitimately
            // call setState in effects (route-change, async load).
            'react-hooks/set-state-in-effect': 'warn',
        },
    },
]

export default config
