// PROTOTYPE — pure browser-owned rolling-summary state; not production code.

export const DEFAULT_POLICY = Object.freeze({
  cadenceSec: 60,
  timeoutSec: 240,
  temperature: 0,
  tokenBudget: 12_000,
  maxJsonAttempts: 3,
  maxBackoffSec: 480,
});

export function createSummaryState({ role = "capture", cadenceSec = 60 } = {}) {
  return {
    role,
    cadenceSec,
    pendingSeq: 0,
    lastSummarySeq: 0,
    nextDueSec: cadenceSec,
    inFlight: null,
    failureCount: 0,
    stickyDelta: false,
    llmStatus: "idle",
    lastGoodSummary: null,
    events: [],
  };
}

function copy(state) {
  return structuredClone(state);
}

function statusEvent(status) {
  return { type: "llm_status", status, finalizing: false };
}

export function reduceSummaryState(state, action) {
  const next = copy(state);
  const effects = [];

  if (action.type === "commit") {
    next.pendingSeq = Math.max(next.pendingSeq, action.seq);
  } else if (action.type === "tick") {
    const due = action.nowSec >= next.nextDueSec;
    const hasNewTranscript = next.pendingSeq > next.lastSummarySeq;
    if (next.role === "capture" && due && hasNewTranscript && next.inFlight === null) {
      const mode = action.mode ?? (next.stickyDelta ? "delta" : "full");
      next.inFlight = {
        requestId: action.requestId,
        targetSeq: next.pendingSeq,
        mode,
        contextRetryUsed: false,
      };
      next.llmStatus = "processing";
      next.events.push(statusEvent("processing"));
      effects.push({
        type: "chat_completion",
        requestId: action.requestId,
        targetSeq: next.pendingSeq,
        mode,
      });
    }
  } else if (action.type === "success" && next.inFlight?.requestId === action.requestId) {
    next.lastSummarySeq = next.inFlight.targetSeq;
    next.lastGoodSummary = action.summary;
    next.inFlight = null;
    next.failureCount = 0;
    next.nextDueSec = action.nowSec + next.cadenceSec;
    next.llmStatus = "idle";
    next.events.push({ type: "llm_summary_update", summary: action.summary });
    next.events.push(statusEvent("idle"));
  } else if (action.type === "context_rejected" && next.inFlight?.requestId === action.requestId) {
    if (next.inFlight.mode === "full" && next.lastGoodSummary !== null && !next.inFlight.contextRetryUsed) {
      next.stickyDelta = true;
      next.inFlight.mode = "delta";
      next.inFlight.contextRetryUsed = true;
      effects.push({
        type: "chat_completion",
        requestId: action.requestId,
        targetSeq: next.inFlight.targetSeq,
        mode: "delta",
        contextRetry: true,
      });
    } else {
      return reduceSummaryState(next, {
        type: "failure",
        requestId: action.requestId,
        nowSec: action.nowSec,
        reason: "context_rejected_after_retry",
      });
    }
  } else if (action.type === "failure" && next.inFlight?.requestId === action.requestId) {
    const backoffSec = Math.min(
      next.cadenceSec * 2 ** next.failureCount,
      DEFAULT_POLICY.maxBackoffSec,
    );
    next.inFlight = null;
    next.failureCount += 1;
    next.nextDueSec = action.nowSec + backoffSec;
    next.llmStatus = "error";
    next.events.push({ ...statusEvent("error"), reason: action.reason });
    effects.push({ type: "schedule", dueSec: next.nextDueSec, backoffSec });
  } else if (action.type === "cancel" && next.inFlight !== null) {
    effects.push({ type: "abort", requestId: next.inFlight.requestId });
    next.inFlight = null;
    next.llmStatus = "idle";
    next.events.push(statusEvent("idle"));
  }

  return { state: next, effects };
}

export function estimatedTokens(messages) {
  return Math.ceil(JSON.stringify(messages).length / 4);
}

export function chooseSummaryMode({
  strategy,
  fullMessages,
  hasPreviousSummary,
  previousLatencySec = 0,
  stickyDelta = false,
  tokenBudget = DEFAULT_POLICY.tokenBudget,
}) {
  const fullEstimatedTokens = estimatedTokens(fullMessages);
  if (!hasPreviousSummary) {
    return { mode: "full", reason: "first_summary", fullEstimatedTokens };
  }
  if (strategy === "always-full") {
    return { mode: "full", reason: "strategy", fullEstimatedTokens };
  }
  if (strategy === "always-delta") {
    return { mode: "delta", reason: "strategy", fullEstimatedTokens };
  }
  if (stickyDelta) {
    return { mode: "delta", reason: "sticky_context_rejection", fullEstimatedTokens };
  }
  if (fullEstimatedTokens > tokenBudget) {
    return { mode: "delta", reason: "request_token_budget", fullEstimatedTokens };
  }
  if (previousLatencySec > 60) {
    return { mode: "delta", reason: "previous_call_over_60s", fullEstimatedTokens };
  }
  return { mode: "full", reason: "within_budget", fullEstimatedTokens };
}
