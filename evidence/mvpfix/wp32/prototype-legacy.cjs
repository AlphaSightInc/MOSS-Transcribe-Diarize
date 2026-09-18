// THROWAWAY REVIEW PROTOTYPE, retained as the reproducible audit bench.
// Question: are no-source_lane legacy exports byte-identical to base?
// Hypothesis: all five formats are identical. Falsifier: any differing bytes.
// One command: node evidence/mvpfix/wp32/prototype-legacy.cjs
// Synthetic public-free text only; modules run directly from each Git revision.
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const ts = require('../../../frontend/node_modules/typescript');
const root = process.cwd();
function modules(revision) {
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const source = revision === 'HEAD' ? fs.readFileSync(file, 'utf8')
      : cp.execFileSync('git', ['show', `${revision}:${file}`], {encoding:'utf8'});
    const output = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
    const mod = {exports:{}}; cache.set(file,mod);
    new Function('require','module','exports',output)(name => {
      const relative = path.posix.normalize(path.posix.join(path.posix.dirname(file), name));
      return load(relative.endsWith('.ts') ? relative : relative+'.ts');
    },mod,mod.exports);
    return mod.exports;
  }
  return {merge:load('frontend/src/lib/mergeTranscript.ts'),exp:load('frontend/src/lib/transcriptExport.ts')};
}
const legacy = [{start:0,end:1,text:'Synthetic first sentence.',speaker:'S01',speaker_entity_id:'speaker-0001',display_name:'Alex',state:'final'},
  {start:1,end:2,text:'Synthetic second sentence.',speaker:'S01',speaker_entity_id:'speaker-0001',display_name:'Alex',state:'final'}];
const base=modules('37979e53'),head=modules('HEAD');
const before=base.merge.groupSegmentsIntoTurns(legacy),after=head.merge.groupSegmentsIntoTurns(legacy);
console.log(JSON.stringify({step:'input',segments:legacy}));
console.log(JSON.stringify({step:'grouped',before,after}));
let identical=0;
for (const format of ['md','txt','json','srt','vtt']) {
  const args=[t=>t.display_name,{sessionId:'synthetic-legacy',exportedAt:new Date(0)}];
  const old=base.exp.serializeTranscriptExport(format,before,...args).content;
  const current=head.exp.serializeTranscriptExport(format,after,...args).content;
  const equal=old===current; identical+=Number(equal);
  console.log(JSON.stringify({step:'export',format,equal,baseBytes:Buffer.byteLength(old),headBytes:Buffer.byteLength(current),...(equal?{}:{before:old,after:current})}));
}
console.log(JSON.stringify({step:'verdict',identical,total:5,hypothesis:identical===5?'supported':'falsified'}));
