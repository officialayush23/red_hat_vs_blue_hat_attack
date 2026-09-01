import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // src/components/ui/** is VENDORED shadcn/ui output, not code we author.
    // Regenerating a primitive with the shadcn CLI reintroduces both of these
    // every time, so fixing them by hand is churn that reverts itself:
    //   - `import * as React` is unused under the React 19 JSX transform, but
    //     it is what the generator emits.
    //   - the primitives deliberately co-export a cva `*Variants` helper
    //     beside the component, which react-refresh flags.
    // Scoped off here rather than globally, so the same mistakes in OUR code
    // still fail the lint.
    files: ['src/components/ui/**/*.{js,jsx}'],
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^React$' }],
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    // Context modules: a Provider component and its useX() hook belong in one
    // file -- that is the standard React pattern and splitting them to satisfy
    // Fast Refresh would make the API worse. Fast Refresh degrades to a full
    // reload for these two files; that is the deliberate trade.
    files: ['src/lib/onboarding.jsx', 'src/lib/theme.jsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
])
