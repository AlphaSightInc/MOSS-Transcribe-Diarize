(async () => {
  const base = `/api/live/sessions/${encodeURIComponent(window.__mossBenchmarkSessionID)}`;
  const headers = { Authorization: window.__mossAuth, Accept: "application/json" };

  async function one(path) {
    const started = performance.now();
    const response = await window.__mossOriginalFetch(base + path, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    const payload = await response.json();
    return { ms: performance.now() - started, status: response.status, payload };
  }

  function observation(mode, started, snapshot, events) {
    return {
      mode,
      cycleMS: performance.now() - started,
      snapshotMS: snapshot.ms,
      eventsMS: events.ms,
      snapshotStatus: snapshot.status,
      eventsStatus: events.status,
      version: snapshot.payload.snapshot?.session?.version ?? null,
      maxSeq: Math.max(0, ...(events.payload.events || []).map((event) => event.seq)),
    };
  }

  async function serial() {
    const started = performance.now();
    const snapshot = await one("/snapshot?since_version=0");
    const events = await one("/events?since_seq=0");
    return observation("serial", started, snapshot, events);
  }

  async function concurrent() {
    const started = performance.now();
    const [snapshot, events] = await Promise.all([
      one("/snapshot?since_version=0"),
      one("/events?since_seq=0"),
    ]);
    return observation("concurrent", started, snapshot, events);
  }

  const pairs = [];
  for (let index = 0; index < 30; index += 1) {
    pairs.push(index % 2 === 0
      ? [await serial(), await concurrent()]
      : [await concurrent(), await serial()]);
  }
  const rows = pairs.flat();
  function percentile(mode, key, fraction) {
    const values = rows
      .filter((row) => row.mode === mode)
      .map((row) => row[key])
      .sort((left, right) => left - right);
    return values[Math.ceil(values.length * fraction) - 1];
  }
  function monotonic(mode, key) {
    const values = rows.filter((row) => row.mode === mode).map((row) => row[key]);
    return values.every((value, index) => index === 0 || value >= values[index - 1]);
  }

  return {
    schema: "moss-browser-fetch-concurrency-prototype.v1",
    chromium: navigator.userAgent,
    pairs: pairs.length,
    payloadMode: "full snapshot since_version=0 plus full retained events since_seq=0",
    serial: {
      p50CycleMS: percentile("serial", "cycleMS", 0.50),
      p95CycleMS: percentile("serial", "cycleMS", 0.95),
      maxCycleMS: percentile("serial", "cycleMS", 1.00),
    },
    concurrent: {
      p50CycleMS: percentile("concurrent", "cycleMS", 0.50),
      p95CycleMS: percentile("concurrent", "cycleMS", 0.95),
      maxCycleMS: percentile("concurrent", "cycleMS", 1.00),
    },
    all200: rows.every((row) => row.snapshotStatus === 200 && row.eventsStatus === 200),
    snapshotVersionsMonotonic: {
      serial: monotonic("serial", "version"),
      concurrent: monotonic("concurrent", "version"),
    },
    eventSequencesMonotonic: {
      serial: monotonic("serial", "maxSeq"),
      concurrent: monotonic("concurrent", "maxSeq"),
    },
    rows,
  };
})()
