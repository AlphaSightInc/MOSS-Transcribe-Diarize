# Round 5 — one-click Start flow and trusted certificate (2026-10-01)

Base: `gemini/r4-ui` @ `19e0e48e`. Built and tested on the MacStudio pilot first; `ga0-rog-laptop` is updated only after
the user approves.

## Decisions (user, grilling 2026-10-01)

| Code | Decision |
|---|---|
| Q14 / Q14b / Q19 | Browser-trusted certificate via Let's Encrypt DNS-01 on Netlify DNS (repo tooling `ops/manage-certificate.sh` pattern, `lego`), **laptop only**, one certificate with two names: `ga0-rog-laptop.tailnet.aisight.us` (tailnet) and `ga0-rog-laptop.lan.aisight.us` → A record to the LAN address. The user places one restricted Netlify token file on the host. IP and `.local` addresses keep warning (no public CA signs them). Done with the laptop update, not before. |
| Q15 | Controls show two **source checkboxes**, "System Sound Output" (first "System sound"; renamed 2026-10-01) and "Microphone", default ON, remembered per browser. They choose sources at Start and are **locked during a recording**. "Mute mic" stays a separate button, shown only when the microphone is a source ("enabled" and "temporarily muted" are different states). |
| Start | Live is the default mode. **Start recording is always enabled unless both boxes are unticked.** One click: Chrome's share picker (if System Sound Output) → microphone (if ticked). The "Enable microphone" and "Share audio" buttons are removed. |
| Q16 | Source failures at Start: (a) no microphone / permission denied → record system sound only, Microphone unticks, line "Microphone unavailable"; (b) share picker cancelled → nothing starts, no message; (c) a surface shared without audio → record microphone only with line "System sound output not shared"; if there is no microphone either, nothing starts and one line says how to share audio. |
| Q17 | Microphone device dropdown directly under the Microphone checkbox (when ticked and names are known). **Echo cancellation always on**; the "Listening with" control is removed everywhere. Headphone voice-quality cost of always-on echo cancellation is UNMEASURED. |
| Design | An unticked or unavailable source is a **silent lane** fed by the browser (same frame timing as Mute): no server change, no provider cost (lanes open provider sessions on voiced audio only). |
| Q18 | Long-meeting speaker split: verify rule V (count an alternation veto only when its turns match their own labels) with one paid raw-label pass (~$0.40); adopt only if the precommitted gates pass (`prototypes/gemini-live/aba-veto/NOTES.md`). |

## Gates

1. Frontend + backend suites green; real Chromium (fake devices) checks for: both sources, system-only, mic-only, each
   failure (a)/(b)/(c), locked boxes during recording, Mute only with a mic source, remembered choices.
2. Real Gemini sessions on the MacStudio (cap $1.50): both sources, system-only, mic-only — complete, clean-up done,
   silent lane costs $0, no "No microphone sound" warning for an unticked microphone.
3. MacStudio pilot updated; user tests; then laptop update + certificate.
