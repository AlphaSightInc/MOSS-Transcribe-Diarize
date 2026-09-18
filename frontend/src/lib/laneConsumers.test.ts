import { describe, expect, it } from "vitest";
import fixtures from "../../../evidence/mvpfix/wp2/fixtures.json";
import { openMeeting, type Meeting, type MeetingSegment } from "../api/meetings";
import type { TranscriptItem } from "../api/types";
import { buildTranscriptIdentity, groupSegmentsIntoTurns, upsertTranscriptItems } from "./mergeTranscript";
import { buildTranscriptTargetKey } from "./transcriptKeys";
import { buildTranscriptSearchResults } from "./transcriptSearch";
import { defaultSettings, providerBody } from "./finalSummary";
import { filterMeetings, meetingTitle } from "./meetingHistory";
import { serializeTranscriptExport } from "./transcriptExport";
const item = (overrides: Partial<TranscriptItem> = {}): TranscriptItem => ({start:0,end:2,text:"Same words",speaker:"S01",speaker_entity_id:"speaker-0001",display_name:"Alex",state:"final",...overrides});
const meeting = (segments: unknown[]): Meeting => ({id:"fixture",mode:"live",title:"Fixture title",title_source:"manual",created_at_ms:1,status:"completed",transcript_version:1,audio:null,transcript:{segments:segments as MeetingSegment[]}});
const identity = {sessionId:"fixture",exportedAt:new Date(0)};

describe("lane consumers", () => {
 it.each(["overlap","legacy"] as const)("preserves the %s corpus across meeting parse, history, turns, search, exports and summary", async key => {
  const expected = fixtures[key].segments;
  const parsed = await openMeeting("fixture", async()=>Response.json(meeting([...expected].reverse())));
  expect(parsed.transcript!.segments).toEqual([...expected].reverse());
  expect(filterMeetings([parsed],"speculation")).toEqual([parsed]);
  expect(meetingTitle(parsed)).toBe("Fixture title");
  const rows = upsertTranscriptItems([],parsed.transcript!.segments.map(s=>({...s,segment_id:s.id,speaker:s.speaker_entity_id!,speaker_entity_id:s.speaker_entity_id!,display_name:s.speaker,state:"final"})));
  expect(rows.map(s=>s.segment_id)).toEqual(expected.map(s=>s.id));
  expect(new Set(rows.map(s=>s.speaker_entity_id)).size).toBe(key==="overlap"?4:2);
  const turns=groupSegmentsIntoTurns(rows);
  expect(turns).toHaveLength(expected.length);
  expect(turns.map(t=>t.text)).toEqual(expected.map(s=>s.text));
  const search=buildTranscriptSearchResults([...turns].reverse(),"speculation",t=>t.display_name);
  expect(search.matchCount).toBe(3);
  expect(search.turns.map(t=>t.turn)).toEqual(turns);
  for(const format of ["md","txt","json","srt","vtt"] as const){
   const output=serializeTranscriptExport(format,[...turns].reverse(),t=>t.display_name,identity).content;
   for(const s of expected) expect(output).toContain(s.text);
   if(format==="json") {
    const exported=JSON.parse(output).turns;
    expect(exported.map((t: {source_lane?: string})=>t.source_lane)).toEqual(turns.map(t=>t.source_lane));
    expect(exported.map((t: {speaker_label: string})=>t.speaker_label)).toEqual(turns.map(t=>t.display_name));
   } else {
    expect(output).not.toContain('[System]');
    expect(output).not.toContain('[Microphone]');
   }
  }
  const payload: {segments: MeetingSegment[]}=JSON.parse(JSON.parse(providerBody(parsed,defaultSettings())).messages[1].content);
  expect(payload.segments.map(s=>s.text)).toEqual(expected.map(s=>s.text));
  expect(payload.segments.map(s=>s.speaker)).toEqual(expected.map(s=>s.speaker));
  expect(payload.segments.map(s=>s.source_lane)).toEqual(expected.map(s=>('source_lane' in s?s.source_lane:undefined)));
 });
 it("does not merge lanes or independent speakers sharing a display name",()=>{
  const rows=[item({source_lane:"microphone",end:1}),item({source_lane:"system",end:3}),item({source_lane:"system",speaker_entity_id:"speaker-0002",end:4})];
  const normalized=upsertTranscriptItems([],rows);
  expect(normalized).toHaveLength(3);
  expect(new Set(rows.map(buildTranscriptIdentity)).size).toBe(3);
  expect(new Set(rows.map(buildTranscriptTargetKey)).size).toBe(3);
  expect(groupSegmentsIntoTurns(rows).map(t=>[t.source_lane,t.speaker_entity_id,t.end])).toEqual([
   ["system","speaker-0001",3],["system","speaker-0002",4],["microphone","speaker-0001",1]
  ]);
 });
 it("preserves simultaneous identical no-id speech in incremental updates",()=>{
  const system=item({source_lane:"system",state:"provisional"});
  const microphone=item({source_lane:"microphone",speaker_entity_id:"speaker-0002",state:"provisional"});
  expect(upsertTranscriptItems(upsertTranscriptItems([], [system]), [microphone])).toHaveLength(2);
 });
 it("a commit cannot retire the other lane's provisional tail",()=>{
  const pending=item({source_lane:"microphone",state:"provisional",segment_id:"live-provisional"});
  const committed=item({source_lane:"system",segment_id:"system-final"});
  expect(upsertTranscriptItems([pending],[committed]).map(s=>s.source_lane)).toEqual(["system","microphone"]);
 });
 it.each(["srt","vtt"] as const)("retains overlapping %s cue intervals and speaker-only labels exactly",format=>{
  const turns=groupSegmentsIntoTurns([item({source_lane:"microphone",end:1,text:"Mic"}),item({source_lane:"system",end:3,text:"System"})]);
  const sep=format==="srt"?",":".";
  expect(serializeTranscriptExport(format,turns,t=>t.display_name,identity).content).toBe(
   (format==="vtt"?"WEBVTT\n\n":"")+`1\n00:00:00${sep}000 --> 00:00:03${sep}000\nAlex: System\n\n2\n00:00:00${sep}000 --> 00:00:01${sep}000\nAlex: Mic\n`);
 });
});
