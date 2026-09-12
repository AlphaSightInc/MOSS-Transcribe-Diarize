(() => {
  const rows = [], audio = [];
  rows.push({kind:'clock',t:performance.now(),timeOrigin:performance.timeOrigin});
  window.__mossTimings = rows;
  window.__mossCalibration = audio;
  window.__mossTiming = (kind, detail = {}, samples) => {
    rows.push({kind, t: performance.now(), ...detail});
    if (kind === 'worklet' && detail.session && audio.filter(r => r.lane === detail.lane).length < 24) {
      audio.push({lane: detail.lane, startFrame: detail.startFrame, samples: Array.from(samples)});
    }
  };
  const mark = window.__mossTiming;
  const original = window.fetch;
  window.fetch = async (...args) => {
    const path = new URL(String(args[0]), location.href).pathname;
    const data = args[1]?.body;
    let frame;
    if (path.endsWith('/frames') && typeof data === 'string') {
      const f = JSON.parse(data);
      frame = {lane: f.lane, sequence: f.sequence, samples: f.sample_count, timestamp_ns:f.capture_timestamp_ns};
    }
    const start = performance.now();
    mark('request', {path, frame});
    const response = await original(...args);
    mark('response', {path, elapsed: performance.now()-start, status:response.status, frame});
    const json = response.json.bind(response);
    response.json = async (...options) => {
      const body = await json(...options);
      const snapshot = body.snapshot, session = snapshot?.session;
      mark('json', {path, frame, unchanged:body.unchanged, version:session?.version,
        accepted:session?.accepted_samples, committed:session?.committed_samples,
        provisional: session?.provisional ? {start:session.provisional.start_sample,end:session.provisional.end_sample,words:!!session.provisional.transcript}:null,
        draft:!!snapshot?.draft, pending:snapshot?.pending_work_items,
        effective:session?.effective_transcript?.length,
        events:body.events?.filter(e => ['canonical_started','canonical_processed','canonical_preview','span_frozen'].includes(e.kind))
          .map(e=>({kind:e.kind,seq:e.seq,payload:e.payload}))});
      return body;
    };
    return response;
  };
  addEventListener('click', e => {
    if (e.target.closest('button')?.textContent?.trim() === 'Start capture') mark('start_click');
  }, true);
  addEventListener('DOMContentLoaded', () => {
    let shown=false, speechShown=false;
    new MutationObserver(() => {
      const visibleText = [...document.querySelectorAll('.utt-text')].map(e=>e.textContent).join(' ');
      if (!speechShown && /the following/i.test(visibleText)) { speechShown=true;mark('known_speech_dom'); }
      if (!shown && [...document.querySelectorAll('.utt-text')].some(e=>e.textContent.trim())) {
        shown=true;mark('dom', {known_speech_prefix: /the following/i.test([...document.querySelectorAll('.utt-text')].map(e=>e.textContent).join(' '))});requestAnimationFrame(()=>mark('paint_opportunity'));
      }
    }).observe(document.body,{subtree:true,childList:true,characterData:true});
  });
})();
