import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    // Build output and dependencies are never linted.
    ignores: ['dist', 'node_modules', 'coverage'],
  },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // Tracked debt, deliberately warnings rather than errors.
      //
      // These two React Compiler rules were surfaced the first time this codebase
      // was ever linted (no eslint config existed before). The remaining hits are
      // legitimate-but-dated patterns spread across auth, onboarding, preferences
      // and media state (resetting state when a prop changes, initialising auth,
      // deriving a displayed value). Fixing them means reworking state management
      // in code that is already deployed, so it belongs in its own reviewed change
      // with functional testing behind authentication - not in a lint sweep.
      // Keep them visible as warnings; do not add blanket file-level disables.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
    },
  },
  {
    // Test files rely on globals injected by Vitest.
    files: ['**/*.test.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
);
