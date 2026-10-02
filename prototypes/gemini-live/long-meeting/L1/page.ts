// Test-only entry. Delivery/serialization/error handling are the actual bundled CaptureClient.
import { observeUi } from './ui';
import { CaptureClient } from '../../../../frontend/src/capture/captureClient';
const w = window as any;
w.observeUi=()=>observeUi(w.client.session.id);
w.traffic = {frames:0,heartbeat:0,failed:0,status:{},sent:0,firstFailed:null,firstResponses:[]};
const networkFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const route = String(args[0]).split('/').at(-1);
  const capture = route === 'frames' || route === 'heartbeat';
  const index = capture ? ++w.traffic.sent : 0;
  try {
    const response = await networkFetch(...args);
    if(capture){w.traffic[route!]++;w.traffic.status[response.status]=(w.traffic.status[response.status]||0)+1;
      if(w.traffic.firstResponses.length<2)w.traffic.firstResponses.push({route,status:response.status,headers:Object.fromEntries(response.headers)});}
    return response;
  } catch(error) {if(capture){w.traffic.failed++;w.traffic.firstFailed??={index,route,error:String(error)};} throw error;}
};
w.run = async (total: number, warm: boolean = false) => {
  let c = w.client;
  if (!c) {
    let firstFailure: any = null;
    c = new CaptureClient({helperVersion:'p74-scripted', workletUrl:'unused',
      onTransportError:(route, error) => { if (!firstFailure) firstFailure = {route, name:error.name, message:error.message, completed:w.completed}; },
    }) as any;
    const d = await (await fetch('/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2')).json();
    c.descriptor = {sampleRate:d.descriptor.sample_rate, frameSamples:d.descriptor.frame_samples, preflightStatusLines:{microphoneSilent:'synthetic'}};
    c.context = {sampleRate:d.descriptor.sample_rate};
    for (const lane of ['system','microphone']) c.lanes.set(lane, {silent:true, sequence:0, deviceEpoch:1,
      pendingDiscontinuityEpochs:new Set(), discontinuities:0, droppedFrames:0, health:'capturing', degradedCode:null,
      clippedFrameRun:0,silentFrameRun:0,frameQueue:[],postInFlight:false,postFlush:null,tracks:[],trackEndedListeners:[]});
    await c.createSession();
    w.client=c; w.completed=0; w.firstFailure=()=>firstFailure;
  }
  const started=performance.now();
  for (let i=0;i<total/3 && !w.firstFailure();i++) {
    const startFrame=c.lanes.get('system').sequence*c.descriptor.frameSamples;
    for(const lane of ['system','microphone']) c.onWorkletFrame(lane, {type:'frame',lane,startFrame,samples:new Float32Array(c.descriptor.frameSamples)});
    await Promise.all([...c.lanes.values()].map((s:any)=>s.postFlush).concat([c.heartbeatFlush]));
    if (!w.firstFailure()) w.completed+=3;
  }
  const result={completed:w.completed,firstFailure:w.firstFailure(),seconds:(performance.now()-started)/1000,
    sequence:Object.fromEntries([...c.lanes].map(([lane,s]:any)=>[lane,s.sequence])), heartbeatSequence:c.heartbeatSequence};
  document.querySelector('pre')!.textContent=JSON.stringify(result);
  return result;
};
w.probe=async()=>{const result:any={}; for(const [key,path,method] of [['get','/api/live/descriptor','GET'],['post','/api/live/sessions','POST']]) {
  try {const r=await fetch(path,{method});await r.arrayBuffer();result[key]=r.status;}catch(e){result[key]=String(e);}
}return result;};
