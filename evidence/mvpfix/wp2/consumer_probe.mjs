// Repeatable consumer evidence probe, absorbed after prototype verdict.
import { createServer } from '../../../frontend/node_modules/vite/dist/node/index.js';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const server = await createServer({configFile:false, root:process.cwd()+'/frontend', cacheDir:process.cwd()+'/evidence/mvpfix/wp2/.vite', server:{middlewareMode:true}, appType:'custom'});
try {
 const load = p => server.ssrLoadModule('/src/'+p+'.ts');
 const {openMeeting} = await load('api/meetings');
 const {upsertTranscriptItems,groupSegmentsIntoTurns} = await load('lib/mergeTranscript');
 const {buildTranscriptSearchResults} = await load('lib/transcriptSearch');
 const {serializeTranscriptExport} = await load('lib/transcriptExport');
 const {providerBody,defaultSettings} = await load('lib/finalSummary');
 const {filterMeetings,meetingTitle} = await load('lib/meetingHistory');
 for (const [key, original] of Object.entries(JSON.parse(fs.readFileSync('evidence/mvpfix/wp2/meetings.json','utf8')))) {
   const meeting = await openMeeting(original.id, async()=>Response.json(original));
   console.log('PARSED',key,JSON.stringify(meeting));
   console.log('HISTORY FILTER',key,filterMeetings([meeting],'the').length,meetingTitle(meeting));
   const items=meeting.transcript.segments.map(s=>({...s,segment_id:s.id,speaker:s.speaker_entity_id,display_name:s.speaker,state:'final'}));
   const normalized=upsertTranscriptItems([],items);
   console.log('NORMALIZED',key,JSON.stringify(normalized));
   const renamed=normalized.map(s=>s.speaker_entity_id===items[0].speaker_entity_id?{...s,display_name:'Renamed'}:s);
   const turns=groupSegmentsIntoTurns(renamed);
   console.log('RENAME TURNS',key,JSON.stringify(turns));
   console.log('SEARCH',key,JSON.stringify(buildTranscriptSearchResults(turns,'the',t=>t.display_name)));
   for(const format of ['md','txt','json','srt','vtt']) console.log('EXPORT',key,format,serializeTranscriptExport(format,turns,t=>t.display_name,{sessionId:key,exportedAt:new Date(0)}).content);
   console.log('SUMMARY',key,providerBody(meeting,defaultSettings()));
   assert.equal(normalized.length,original.transcript.segments.length);
   assert.deepEqual(normalized.map(s=>s.source_lane),original.transcript.segments.map(s=>s.source_lane));
   assert.deepEqual(normalized.map(s=>s.text),original.transcript.segments.map(s=>s.text));
   console.log('COUNTS',key,JSON.stringify({input:items.length,normalized:normalized.length,turns:turns.length,lanes:normalized.filter(s=>s.source_lane).length,speakers:new Set(normalized.map(s=>s.speaker_entity_id)).size}));
   const candidate=original.transcript.segments.slice().sort((a,b)=>a.start-b.start||Number(a.source_lane==='microphone')-Number(b.source_lane==='microphone')||a.end-b.end);
   console.log('CANDIDATE',key,JSON.stringify({segments:candidate.length,speakers:new Set(candidate.map(s=>s.speaker_entity_id)).size,lanes:candidate.filter(s=>s.source_lane).length,order:candidate.map(s=>s.id)}));
 }
} finally {await server.close();}
