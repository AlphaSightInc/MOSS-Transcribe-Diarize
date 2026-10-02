// Observe actual UI with its last known active state and its real poller on the exhausted page.
import { h, render } from 'preact';
import { App } from '../../../../frontend/src/App';
import { sessionId, sessionStatus, sessionMode, sessionStartedAt } from '../../../../frontend/src/state/session';
import { LIVE_MEETING_OBSERVE_EVENT } from '../../../../frontend/src/lib/meetingEvents';
export async function observeUi(id: string) {
  const root=document.createElement('div');document.body.append(root);render(h(App,{}),root);
  await new Promise(r=>setTimeout(r,100));
  document.dispatchEvent(new CustomEvent(LIVE_MEETING_OBSERVE_EVENT,{detail:{meetingId:id}}));
  sessionId.value=id;sessionStatus.value='active';sessionMode.value='live';
  sessionStartedAt.value={sessionId:id,ms:Date.now()-2731000};
  await new Promise(r=>setTimeout(r,1100));
  return {pill:root.querySelector('.top-status')?.textContent?.trim(),
    status:[...root.querySelectorAll('[role="status"]')].map(x=>x.textContent),
    phase:root.querySelector('[data-capture-phase]')?.getAttribute('data-capture-phase'),text:root.textContent};
}
