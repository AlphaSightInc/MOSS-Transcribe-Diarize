# Round-3 scheduling full-suite gate

- Candidate before receipt commit: `ad5099c3` on `round3/scheduling`.
- Import: `/private/tmp/moss-round3-20260919/scheduling/moss_transcribe_diarize/__init__.py`.
- Backend command: `python -m pytest -q -p no:cacheprovider tests`.
- Backend result: **2,067 passed, 5 skipped, 37 subtests passed**;
  21 warnings; 179.80 s; zero failures.
- Frontend command: `npm --prefix frontend test -- --run`.
- Frontend result: **28 files passed; 288/288 tests passed**; 2.62 s.
- Typecheck: `npm --prefix frontend run typecheck`; exit 0.
- Build: `npm --prefix frontend run build`; exit 0; 34 modules;
  61 ms; generated assets identical to tracked files.
