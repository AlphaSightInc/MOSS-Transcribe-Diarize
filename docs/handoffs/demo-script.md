# MOSS — 10-minute client demo

**Before guests arrive:** On the MacBook, open Chrome over the tailnet: **https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861**. Have the release owner confirm the host serves the **admitted candidate**. Use your rehearsed profile and headphones/AirPods. Prepare a **30–50-second MP3** and a paused, ad-free YouTube interview passage.

Run **`MOSS_DEMO_OPENROUTER_API_KEY=<key> scripts/demo-precheck.sh EXPECTED_FULL_SHA`** from the repository on the MacBook. Use the release owner’s 40-character SHA and the operator’s OpenRouter key; the script never prints the key. Require its final **GO**: trusted host, served identity, the configured relay models, and 16-token answers from macstudio and from OpenRouter (`google/gemini-2.5-flash`), each within 30 seconds. rtx4090 is probed only when `MOSS_DEMO_RTX4090_BASE` is set. **NO-GO** names failures; stop and resolve them. The check creates its own empty workspace, not a meeting.

Check **Voiceprints** contains your enrolled name. On a completed rehearsal meeting, open **Optional AI summaries · configured** (or **· off**) and set **Provider → External HTTPS provider**, **Provider HTTPS URL** `https://openrouter.ai/api/v1`, **Model** `google/gemini-2.5-flash`, and **API key (optional)** to the OpenRouter key. Then click **Save on this browser**, **Generate summary** / **Regenerate summary**, and confirm **Summary ready. · google/gemini-2.5-flash**. Do not use **Server relay** for the demo: its qwen model fails about a third of summaries on meetings of three minutes or more. **Recovery:** fix failed pre-checks before guests arrive; retain the rehearsal meeting as backup.

| Clock | Presenter: do and say | Audience sees / expected timing | One-line recovery |
|---|---|---|---|
| **0:00–1:00** | “Watch speech become a meeting record.” Click **Live / Transcript & export**; **Reset capture** if shown. Set **Listening setup → Headphones**; **Enable microphone**, then **Share audio**. Choose the YouTube **tab**, enable its audio-sharing checkbox; return to MOSS. | **Microphone connected**; responsive meters. Setup: 20–40 seconds. | No meter: check microphone or re-share with audio enabled. |
| **1:00–3:00** | **Start capture**. Say: “Welcome. Today we’ll agree the launch date, choose the owner, and record our next steps.” Play **10–15 seconds** of interview; speak a short known sentence during playback, then return to MOSS. Both sources should remain in the transcript. | Live text appears in speaker cards. The single **Identity settling** notice means labels can change; with L-a, unsettled system/microphone speech reads **Remote/You**. Settled identities get consecutive Speaker numbers. Auto-scroll follows new text until switched off or Find opens. Rehearsal text timing was **2–4 seconds**, not a freeze-5 guarantee. | Unnamed speaker: give at least 2 seconds of finished, clear speech; provisional speech cannot save a voiceprint. Network blip: keep talking; allow reconnection. |
| **3:00–4:00** | Pause YouTube. Click the interview speaker’s **confirmed label**. Enter **Display name**; uncheck **Save voiceprint** for this guest; click **Save name**. “The name follows the speaker.” | Transcript/legend update, usually within a second. Multiple nearby turns by one speaker may share a card; the source passages remain individually correctable after finalization. | Unclickable label: wait for confirmation. |
| **4:00–5:00** | Click **Stop and finalize once**. Open **Meeting history**, click **Refresh** if needed, then the new meeting’s title card. | **Live · closed**, finished transcript. Budget 5–30 seconds; longer under load. | Stop remains in progress: wait; do not press it again. |
| **5:00–6:00** | Click **Export transcript → SubRip (.srt)**; then **Download audio** on that meeting’s history card. | Subtitles and MP3 download: seconds once ready. | Download unavailable: wait for completion, then **Refresh** history. |
| **6:00–7:30** | **Files & URLs**; choose the MP3 in the file picker, then **Transcribe files and URLs**. Open its new history card. | **File / URL**, labelled transcript. Budget 10–60 seconds. | Still processing: show the completed live record meanwhile. |
| **7:30–9:00** | On the completed file meeting, click **Generate summary**. “The browser sends the finished transcript straight to the model; MOSS keeps only the summary. Today’s model is…” Read the model beside **Summary ready.** (`google/gemini-2.5-flash`). | **Generating summary…**, then the summary, topics and supporting details: about 5–15 seconds for a short file; budget up to 60. Keep tab open. | Failed: click **Retry summary**. Delivery failures also retry on their own after 60, 120 and 240 seconds. |
| **9:00–10:00** | Narrow the browser to phone width (about 400 pixels). Click **Meeting history**, then **Files & URLs**. Close: “One record: live speech, speakers, files, subtitles, audio and a summary.” | Stacked sections, usable navigation; immediate. | Layout awkward: widen slightly and keep the selected meeting visible. |

**Per-lane expectation, attended proof pending:** the old “never overlap sources”
workaround is obsolete for the per-lane build. Rehearse overlapping microphone/system
speech with two known references; require both in live text and after Stop → save →
reopen/export, with correct lane attribution. If words disappear, report a failure;
do not silently restore the workaround or claim acceptance. Same-lane overlapping
speakers and speakers-mode echo need their own measurement. Headphones remain the
demo setup; they are not evidence of speakers-mode performance.

**TLS prerequisite:** use the [renewal runbook](tls-renewal-runbook.md). WP13's read-only
probe found 7861 self-signed and 7862 trusted; neither a browser exception nor switching
ports establishes that the admitted demo candidate is ready.

**Do not do:** leave the capture tab in the background for long—supported now, unnecessary in this demo; press Stop twice quickly; upload anything except **MP3**; close the summary’s creating tab while it is working.

*Timing budgets, not guarantees. Labels: E2E harness and UI source; summary labels re-verified in a real browser on `566024287cdd` (2026-09-15); rehearsal: `evidence/same-tab-repeat-capture-20260911/candidate/`.*
