// Feed actual HTTP snapshots through the shipped TypeScript poller and signal reducer.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
require.extensions['.ts'] = (mod, filename) => mod._compile(ts.transpileModule(
  fs.readFileSync(filename, 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }
).outputText, filename);
const { createMossSessionPoller } = require(path.join(root, 'frontend/src/api/mossPoller.ts'));
const { resetSessionState, transcript } = require(path.join(root, 'frontend/src/state/session.ts'));
const snapshots = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  resetSessionState();
  let index = 0;
  const errors = [], rows = [];
  const poller = createMossSessionPoller({
    sessionId: snapshots[0].snapshot.session_id,
    onError: message => errors.push(message),
    fetch: async input => new Response(JSON.stringify(String(input).includes('/snapshot')
      ? snapshots[index++] : { events: [] })),
  });
  for (const snapshot of snapshots) {
    await poller.poll();
    rows.push(JSON.parse(JSON.stringify(transcript.value)));
  }
  poller.stop();
  process.stdout.write(JSON.stringify({ rows, errors }));
})();
