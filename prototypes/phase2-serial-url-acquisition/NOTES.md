# Phase-2 serial URL acquisition probe

## Structural contract

- **Question:** can one bounded acquisition seam accept direct HTTP(S) media and YouTube while
  never turning a submission group into authority or allowing one source failure to affect peers?
- **Minimum primitives:** one validated URL, one transient source directory, one byte/time/redirect
  bound, and one acquired media path. Meeting ownership and inference remain outside this seam.
- **Invariants:** HTTP(S) only; YouTube uses yt-dlp; direct HTML is not media; declared and streamed
  bytes share one strict 2 GiB ceiling; one item produces at most one media path; timeout/cancel/
  oversize kills the entire downloader process group and removes partial output.
- **Unknowns:** real-site/provider availability is unmeasured here and remains a deployed #22 gate.
- **Falsifier:** any oversize/HTML/redirect/timeout case yields a usable path, known YouTube goes
  through direct HTTP, an emitted byte beyond the ceiling reaches disk, or a downloader descendant
  survives termination.
- **Tool decision:** a loopback HTTP fixture plus fake yt-dlp output and descendant processes
  exercise the production acquirer deterministically; no external provider is needed to decide the
  local policy.

## One command

```bash
uv run --frozen --extra dev python prototypes/phase2-serial-url-acquisition/prototype.py
```

## Verdict

Accepted on 2026-08-27. Full printed state showed 1/1 direct media and 1/1 known-YouTube
acquisitions accepted. Direct declared-size, direct streamed-size, HTML, redirect-overflow,
YouTube-streamed-size, and process-timeout cases rejected 6/6. Both rejected YouTube paths left
zero files; timeout killed the fake downloader descendant (`descendant_survived_parent_kill=false`).
Explicit cancellation propagated 2/2 across direct HTTP and YouTube, left zero partial files, and
killed the YouTube downloader descendant.
The accepted paths contained exactly the fixture bytes. Production may use the same seam with
2 GiB, 30 s network-inactivity, 3,900 s total-time, and five-redirect bounds.

The official yt-dlp interface supports programmatic invocation, `--no-playlist`, `--max-filesize`,
and `--socket-timeout`; its current YouTube guidance requires the `default` Python dependency group
plus a supported JavaScript runtime. Real YouTube availability remains a deployed #22 canary.

An initial candidate also supplied `--max-downloads 1`. A real `--simulate` probe on yt-dlp
2026.03.17 returned exit 101 after reaching that limit, which this integration correctly treats as
failure. The flag is measured-rejected: `--no-playlist` already supplies the required one-item
semantics, and the deterministic yt-dlp fixture now exits 101 if the rejected flag returns.

An initial file-output candidate also relied on yt-dlp `--max-filesize` plus a post-exit check and
killed only the parent process. Adversarial production probes falsified both: manifest downloads can
exceed `--max-filesize`, and a spawned descendant survived parent kill. The accepted seam keeps
`--max-filesize` only as an early advisory rejection, streams explicit `bestaudio/best` through
stdout to an exact Python byte counter, and runs yt-dlp in a new process session so the whole group
is terminated on oversize, timeout, or cancellation.
