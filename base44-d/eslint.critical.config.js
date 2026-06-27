/**
 * Phase 64B — ESLint scope for bootstrap / shell files that can blank the whole app.
 * Run via: npm run lint:critical
 */
import globals from "globals";
import pluginJs from "@eslint/js";
import pluginReact from "eslint-plugin-react";
import pluginReactHooks from "eslint-plugin-react-hooks";

const criticalFiles = [
  "src/main.jsx",
  "src/App.jsx",
  "src/components/ScrollToTop.jsx",
  "src/components/CookieConsent.jsx",
  "src/components/ProtectedRoute.jsx",
  "src/components/AdminRoute.jsx",
  "src/components/SuperAdminRoute.jsx",
  "src/components/OwnerRoute.jsx",
  "src/components/dashboard/DashboardLayout.jsx",
  "src/lib/AuthContext.jsx",
];

export default [
  {
    files: criticalFiles,
    ...pluginJs.configs.recommended,
    ...pluginReact.configs.flat.recommended,
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    settings: { react: { version: "detect" } },
    plugins: {
      react: pluginReact,
      "react-hooks": pluginReactHooks,
    },
    rules: {
      "no-undef": "error",
      "react/jsx-no-undef": "error",
      "react/jsx-uses-vars": "error",
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",
      "react-hooks/rules-of-hooks": "error",
    },
  },
];
