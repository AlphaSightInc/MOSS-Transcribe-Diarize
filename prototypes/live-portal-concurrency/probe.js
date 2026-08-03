(async () => {
  const base = `/api/live/sessions/${encodeURIComponent(window.__mossBenchmarkSessionID)}`;
  const headers = { Authorization: window.__mossAuth, Accept: "application/json" };
  const reconnectCycles = new Set([10, 20]);
  const states = {
    serial: { snapshotVersion: 0, eventSequence: 0 },
    concurrent: { snapshotVersion: 0, eventSequence: 0 },
  };
  const errors = [];

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

  function require(condition, message) {
    if (!condition) errors.push(message);
  }

  function applyResponse(mode, cycle, reset, requested, snapshot, events) {
    const state = states[mode];
    const snapshotVersion = snapshot.payload.snapshot?.session?.version ?? null;
    const rawSequences = (events.payload.events || [])
      .map((event) => event.seq)
      .filter(Number.isInteger)
      .sort((left, right) => left - right);
    const newSequences = rawSequences.filter((sequence) => sequence > requested.eventSequence);

    require(snapshot.status === 200, `${mode} cycle ${cycle}: snapshot HTTP ${snapshot.status}`);
    require(events.status === 200, `${mode} cycle ${cycle}: events HTTP ${events.status}`);
    require(
      snapshotVersion === null || snapshotVersion >= requested.snapshotVersion,
      `${mode} cycle ${cycle}: snapshot version regressed`,
    );
    require(
      newSequences.every((sequence, index) => (
        index === 0
          ? sequence === requested.eventSequence + 1
          : sequence === newSequences[index - 1] + 1
      )),
      `${mode} cycle ${cycle}: event sequence gap after ${requested.eventSequence}`,
    );

    if (reset) {
      require(snapshotVersion !== null, `${mode} cycle ${cycle}: reset did not replay snapshot`);
      require(
        snapshotVersion === null || snapshotVersion >= state.snapshotVersion,
        `${mode} cycle ${cycle}: reset snapshot missed known revision ${state.snapshotVersion}`,
      );
      require(
        state.eventSequence === 0 || rawSequences.includes(state.eventSequence),
        `${mode} cycle ${cycle}: reset events missed known sequence ${state.eventSequence}`,
      );
    }

    if (snapshotVersion !== null) state.snapshotVersion = snapshotVersion;
    if (newSequences.length) state.eventSequence = newSequences[newSequences.length - 1];

    return {
      snapshotVersion,
      eventSequences: rawSequences,
      snapshotAdvanced: snapshotVersion !== null && snapshotVersion > requested.snapshotVersion,
      eventsAdvanced: state.eventSequence > requested.eventSequence,
      cursorAfter: { ...state },
    };
  }

  async function cycle(mode, cycleIndex, reset) {
    const state = states[mode];
    const requested = reset
      ? { snapshotVersion: 0, eventSequence: 0 }
      : { ...state };
    const snapshotPath = `/snapshot?since_version=${requested.snapshotVersion}`;
    const eventsPath = `/events?since_seq=${requested.eventSequence}`;
    const started = performance.now();
    let snapshot;
    let events;
    if (mode === "serial") {
      snapshot = await one(snapshotPath);
      events = await one(eventsPath);
    } else {
      [snapshot, events] = await Promise.all([one(snapshotPath), one(eventsPath)]);
    }
    const applied = applyResponse(
      mode, cycleIndex, reset, requested, snapshot, events,
    );
    return {
      mode,
      cycle: cycleIndex,
      reset,
      requested,
      cycleMS: performance.now() - started,
      snapshotMS: snapshot.ms,
      eventsMS: events.ms,
      snapshotStatus: snapshot.status,
      eventsStatus: events.status,
      ...applied,
    };
  }

  const pairs = [];
  for (let index = 0; index < 30; index += 1) {
    const reset = reconnectCycles.has(index);
    pairs.push(index % 2 === 0
      ? [await cycle("serial", index, reset), await cycle("concurrent", index, reset)]
      : [await cycle("concurrent", index, reset), await cycle("serial", index, reset)]);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const rows = pairs.flat();

  function percentile(mode, key, fraction) {
    const values = rows
      .filter((row) => row.mode === mode)
      .map((row) => row[key])
      .sort((left, right) => left - right);
    return values[Math.ceil(values.length * fraction) - 1];
  }

  const advancedAfterInitial = (mode, key) => rows.some(
    (row) => row.mode === mode && row.cycle > 0 && !row.reset && row[key],
  );
  for (const mode of ["serial", "concurrent"]) {
    require(advancedAfterInitial(mode, "snapshotAdvanced"), `${mode}: no incremental snapshot advance`);
    require(advancedAfterInitial(mode, "eventsAdvanced"), `${mode}: no incremental event advance`);
  }

  return {
    schema: "moss-browser-fetch-concurrency-prototype.v2",
    chromium: navigator.userAgent,
    pairs: pairs.length,
    payloadMode: "advancing per-mode cursors with reset/replay at cycles 10 and 20",
    serial: {
      p50CycleMS: percentile("serial", "cycleMS", 0.50),
      p95CycleMS: percentile("serial", "cycleMS", 0.95),
      maxCycleMS: percentile("serial", "cycleMS", 1.00),
      finalCursor: { ...states.serial },
    },
    concurrent: {
      p50CycleMS: percentile("concurrent", "cycleMS", 0.50),
      p95CycleMS: percentile("concurrent", "cycleMS", 0.95),
      maxCycleMS: percentile("concurrent", "cycleMS", 1.00),
      finalCursor: { ...states.concurrent },
    },
    resetCycles: [...reconnectCycles],
    all200: rows.every((row) => row.snapshotStatus === 200 && row.eventsStatus === 200),
    incrementalAdvanceObserved: {
      serial: {
        snapshot: advancedAfterInitial("serial", "snapshotAdvanced"),
        events: advancedAfterInitial("serial", "eventsAdvanced"),
      },
      concurrent: {
        snapshot: advancedAfterInitial("concurrent", "snapshotAdvanced"),
        events: advancedAfterInitial("concurrent", "eventsAdvanced"),
      },
    },
    cursorAndReplayErrors: errors,
    passed: errors.length === 0,
    rows,
  };
})()
