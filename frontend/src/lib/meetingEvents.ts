export const LIVE_MEETING_OBSERVE_EVENT = "moss:observe-live-meeting";
export const OPEN_MEETING_EVENT = "moss:open-meeting";
export const MEETING_HISTORY_REFRESH_EVENT = "moss:refresh-meeting-history";

export function requestMeetingHistoryRefresh(): void {
  document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT));
}

export const SPEAKER_NAMED_EVENT = "moss:speaker-named";
