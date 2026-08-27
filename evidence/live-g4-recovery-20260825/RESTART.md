# A5 development-service restart — 2026-08-25

**PASS.** The campaign ran on the reviewed production patch, through the same development
service command, repository cwd, model, endpoint, identity configuration, TLS material, and
10/10 policy as the adopted service.

- Pre-service: PID `37488`, started `2026-08-25 11:28:31 EDT`.
- Deployed service: PID `57283`, started `2026-08-25 18:57:58 EDT`, tmux session
  `moss-g4-runtime`.
- Production patch SHA-256:
  `b006de9b04c73315c4c6e323d77fe112739fcd33f0d0110e13794133a5278e85`.
- Runtime descriptor, model `OpenMOSS-Team/MOSS-Transcribe-Diarize`, production patch, and four
  production-file hashes are identical in `restart-post.json` and `campaign-post.json`.
- vLLM running/waiting queues were `0/0` before restart, after restart, and after the campaign.

Exact machine records: `restart-pre.json`, `restart-post.json`, `campaign-post.json`, and
`production.patch` in this directory. A first detached launch attempt, PID `56733`, exited before
opening a listener and accepted no traffic; its empty log is
`/Users/gao/.local/share/moss-transcribe-diarize/g3/web_cli-g4-recovery-20260825.log`. The measured
service is only PID `57283`.
