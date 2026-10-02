import {build} from '../../../../frontend/node_modules/vite/dist/node/index.js';
import {fileURLToPath} from 'node:url';
await build({configFile: false, root: fileURLToPath(new URL('../../../../frontend/', import.meta.url)),
  build: {outDir: '/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume/browser-bundle',
    emptyOutDir: false, minify: false,
    lib: {entry: fileURLToPath(new URL('./browser.js', import.meta.url)), formats: ['iife'], name: 'P74Resume', fileName: () => 'resume.js'}}});
