#!/usr/bin/env node
/**
 * Phase 64B — static import guard (catches missing React hooks / router imports).
 * Complements ESLint critical lint; runs without fixing whole-repo lint debt.
 */
import { readFileSync, readdirSync, statSync } from "fs";
import { join, relative } from "path";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";

const ROOT = join(fileURLToPath(import.meta.url), "..", "..");
const FRONTEND = join(ROOT, "base44-d");

const REACT_HOOKS = [
  "useEffect",
  "useState",
  "useMemo",
  "useCallback",
  "useRef",
  "useContext",
  "useReducer",
  "useLayoutEffect",
  "useId",
];

const ROUTER_SYMBOLS = [
  "Link",
  "NavLink",
  "Navigate",
  "Outlet",
  "useNavigate",
  "useLocation",
  "useParams",
  "useSearchParams",
  "useNavigationType",
];

const CRITICAL_PATHS = [
  "src/main.jsx",
  "src/App.jsx",
  "src/components/ScrollToTop.jsx",
  "src/components/CookieConsent.jsx",
  "src/components/dashboard/DashboardLayout.jsx",
  "src/lib/AuthContext.jsx",
];

function collectTopLevelComponentFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isFile() && /\.(jsx|js)$/.test(name)) out.push(p);
  }
  return out;
}

function parseNamedImports(source, moduleSpec) {
  const names = new Set();
  const re = new RegExp(
    `import\\s+(?:type\\s+)?(?:\\{([^}]+)\\}|([A-Za-z_$][\\w$]*)\\s*,\\s*\\{([^}]+)\\})\\s+from\\s+['"]${moduleSpec.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}['"]`,
    "g",
  );
  let m;
  while ((m = re.exec(source)) !== null) {
    const block = m[1] || m[3] || "";
    const defaultName = m[2];
    if (defaultName) names.add(defaultName);
    for (const part of block.split(",")) {
      const token = part.trim().split(/\s+as\s+/)[0].trim();
      if (token) names.add(token);
    }
  }
  const ns = new RegExp(
    `import\\s+\\*\\s+as\\s+([A-Za-z_$][\\w$]*)\\s+from\\s+['"]${moduleSpec.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}['"]`,
  );
  const nsMatch = source.match(ns);
  if (nsMatch) names.add(`*as:${nsMatch[1]}`);
  return names;
}

function usesIdentifier(source, name) {
  if (name === "Link") {
    return /<Link[\s/>]/.test(source) || /\bLink\s*\(/.test(source);
  }
  if (name.startsWith("use")) {
    return new RegExp(`\\b${name}\\s*\\(`).test(source);
  }
  return new RegExp(`\\b${name}\\b`).test(source);
}

function checkFile(absPath) {
  const rel = relative(FRONTEND, absPath).replace(/\\/g, "/");
  const source = readFileSync(absPath, "utf8");
  const issues = [];

  const reactImports = parseNamedImports(source, "react");
  const routerImports = parseNamedImports(source, "react-router-dom");

  for (const hook of REACT_HOOKS) {
    if (usesIdentifier(source, hook) && !reactImports.has(hook)) {
      issues.push(`missing React import for ${hook}()`);
    }
  }

  for (const sym of ROUTER_SYMBOLS) {
    if (!usesIdentifier(source, sym)) continue;
    if (routerImports.has(sym)) continue;
    if (routerImports.has(`*as:${sym}`)) continue;
    issues.push(`missing react-router-dom import for ${sym}`);
  }

  return { rel, issues };
}

function runEslintCritical() {
  const r = spawnSync("npm", ["run", "lint:critical"], {
    cwd: FRONTEND,
    shell: true,
    encoding: "utf8",
  });
  return { ok: r.status === 0, output: (r.stdout || "") + (r.stderr || "") };
}

function main() {
  const files = new Set();
  for (const rel of CRITICAL_PATHS) {
    files.add(join(FRONTEND, rel));
  }
  for (const p of collectTopLevelComponentFiles(join(FRONTEND, "src/components"))) {
    files.add(p);
  }

  const failures = [];
  for (const f of files) {
    try {
      const { rel, issues } = checkFile(f);
      if (issues.length) {
        failures.push({ rel, issues });
      }
    } catch (e) {
      failures.push({ rel: relative(FRONTEND, f), issues: [String(e.message || e)] });
    }
  }

  console.log("=== Phase 64B static import scan ===");
  console.log(`Scanned ${files.size} files`);

  const eslint = runEslintCritical();
  console.log("\n--- ESLint critical ---");
  if (eslint.ok) {
    console.log("PASS lint:critical");
  } else {
    console.log("FAIL lint:critical");
    console.log(eslint.output.trim());
  }

  if (failures.length) {
    console.log("\n--- Custom import guard FAIL ---");
    for (const f of failures) {
      console.log(`  ${f.rel}`);
      for (const i of f.issues) console.log(`    - ${i}`);
    }
  } else {
    console.log("\n--- Custom import guard PASS ---");
  }

  const ok = eslint.ok && failures.length === 0;
  console.log(`\nSTATIC_IMPORT_GUARD: ${ok ? "PASS" : "FAIL"}`);
  process.exit(ok ? 0 : 1);
}

main();
