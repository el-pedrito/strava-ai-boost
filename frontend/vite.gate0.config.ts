/**
 * Gate 0 test page build (see docs/design/apple-watch-workouts.md, step 2).
 *
 * NOT part of `npm run build`: run `GATE0_DIR=/path/to/workouts npm run build:gate0`.
 * Every `*.workout` file in GATE0_DIR is embedded as base64 through the virtual
 * module `virtual:gate0-workouts`; `gate0/inline.mjs` then folds the JS bundle
 * into the HTML so the output is one self-contained file.
 */
import { defineConfig, type Plugin } from 'vite';
import fs from 'node:fs';
import path from 'node:path';

const VIRTUAL_ID = 'virtual:gate0-workouts';
const RESOLVED_ID = `\0${VIRTUAL_ID}`;

function gate0Workouts(): Plugin {
  return {
    name: 'gate0-workouts',
    resolveId(id) {
      return id === VIRTUAL_ID ? RESOLVED_ID : null;
    },
    load(id) {
      if (id !== RESOLVED_ID) return null;
      const dir = process.env.GATE0_DIR;
      if (!dir) {
        throw new Error('GATE0_DIR is not set: point it at a directory of .workout files');
      }
      const absDir = path.resolve(dir);
      const files = fs
        .readdirSync(absDir)
        .filter((name) => name.endsWith('.workout'))
        .sort();
      if (files.length === 0) {
        throw new Error(`GATE0_DIR ${absDir} holds no .workout file`);
      }
      const workouts = files.map((name) => ({
        name,
        b64: fs.readFileSync(path.join(absDir, name)).toString('base64'),
      }));
      return `export default ${JSON.stringify(workouts)};`;
    },
  };
}

export default defineConfig({
  root: path.resolve(__dirname, 'gate0'),
  base: './',
  plugins: [gate0Workouts()],
  build: {
    outDir: path.resolve(__dirname, 'dist-gate0'),
    emptyOutDir: true,
    sourcemap: false,
    modulePreload: false,
    cssCodeSplit: false,
    assetsInlineLimit: Number.MAX_SAFE_INTEGER,
    rollupOptions: {
      output: { inlineDynamicImports: true },
    },
  },
});
