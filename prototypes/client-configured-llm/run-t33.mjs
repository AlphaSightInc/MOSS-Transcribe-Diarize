#!/usr/bin/env node
// PROTOTYPE — focused prompt/output-contract measurement; not production code.

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  INSIGHT_SUMMARY_SYSTEM_PROMPT,
  REVISED_SUMMARY_SYSTEM_PROMPT,
  contractFeedbackMessage,
  insightStructureFeedbackMessage,
  insightSummaryMessages,
  parseSummaryOutput,
  summaryMessages,
  validateInsightSummaryStructure,
  validateSummaryContract,
} from "./summary-contract.mjs";
import {
  DEFAULT_POLICY,
  createSummaryState,
  estimatedTokens,
  reduceSummaryState,
} from "./state-machine.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const SPLIT_PATH = path.join(REPO, "prototypes/streaming-diarization/l15/split-manifest.json");
const BASELINE_PATH = path.join(HERE, "latest-result.json");
const RUN_LABEL = process.env.T33_RUN_LABEL ?? "";
const RUN_SUFFIX = RUN_LABEL ? `-${RUN_LABEL}` : "";
const RESULT_PATH = path.join(HERE, `latest-t33${RUN_SUFFIX}-result.json`);
const REVIEW_PATH = path.join(HERE, `t33${RUN_SUFFIX}-before-after.md`);
const CONTRACT_VERSION = process.env.T33_CONTRACT_VERSION ?? "quantity-v1";

const config = Object.freeze({
  endpoint: (process.env.T33_LLM_ENDPOINT ?? "http://127.0.0.1:1234/v1").replace(/\/$/, ""),
  model: process.env.T33_LLM_MODEL ?? "qwen/qwen3.6-35b-a3b",
  token: process.env.T33_LLM_TOKEN ?? "",
  timeoutSec: DEFAULT_POLICY.timeoutSec,
  temperature: DEFAULT_POLICY.temperature,
  maxAttempts: DEFAULT_POLICY.maxJsonAttempts,
  targetLanguage: "English",
});

if (!["quantity-v1", "insight-v2"].includes(CONTRACT_VERSION)) {
  throw new Error(`unsupported T33_CONTRACT_VERSION: ${CONTRACT_VERSION}`);
}

const contractProfile =
  CONTRACT_VERSION === "insight-v2"
    ? Object.freeze({
        schema: "moss-insight-summary-prompt-prototype.v2",
        question:
          "Can an explicit insight-first goal and JSON shape produce usable structured briefings without treating metric extraction as acceptance?",
        systemPrompt: INSIGHT_SUMMARY_SYSTEM_PROMPT,
        messages: insightSummaryMessages,
        validate: validateInsightSummaryStructure,
        feedback: insightStructureFeedbackMessage,
        promptCandidate: "insight_v2_prompt_alone",
        feedbackCandidate: "insight_v2_prompt_plus_structural_feedback",
        arms: [
          "insight-first V2 prompt with schema-only repair",
          "same V2 prompt with structural feedback; metrics excluded from acceptance",
        ],
        rule:
          "Use structural pass rates only as machine-usability evidence; operator review of unmodified outputs decides insight quality.",
        semanticLimit:
          "Insight importance, reasoning quality, and broader factuality require operator review; metric extraction is diagnostic and never an acceptance criterion",
      })
    : Object.freeze({
        schema: "moss-revised-summary-contract-prototype.v1",
        question:
          "Can one revised summary prompt satisfy the deterministic output contract alone, or does exact contract feedback earn the default within three attempts?",
        systemPrompt: REVISED_SUMMARY_SYSTEM_PROMPT,
        messages: summaryMessages,
        validate: validateSummaryContract,
        feedback: contractFeedbackMessage,
        promptCandidate: "revised_prompt_alone",
        feedbackCandidate: "revised_prompt_plus_contract_feedback",
        arms: [
          "revised prompt with schema-only repair",
          "same revised prompt with exact deterministic contract feedback",
        ],
        rule:
          "Prefer prompt alone only if all cases pass; otherwise prefer contract feedback only if all cases pass; otherwise reject automatic summary as a Phase-2 default.",
        semanticLimit:
          "Broader semantic factuality beyond the deterministic schema, word, topic, timestamp, and digit-bearing quantity contract",
      });

function timestamp(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = String(Math.floor(value / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((value % 3600) / 60)).padStart(2, "0");
  const secs = String(value % 60).padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
}

function formatTranscript(rows) {
  return rows
    .map((row) => `[${timestamp(row.start)}] ${row.speaker || "Speaker"}: ${row.text}`)
    .join("\n");
}

async function loadCases() {
  const split = JSON.parse(await readFile(SPLIT_PATH, "utf8"));
  const cases = [];
  const unavailable = [];
  for (const splitName of ["development", "validation"]) {
    for (const item of split.groups[splitName]) {
      const referencePath = path.join(REPO, item.reference_path);
      let source;
      try {
        source = await readFile(referencePath, "utf8");
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
        unavailable.push({
          caseId: item.case_id,
          split: splitName,
          referencePath: item.reference_path,
          reason: "pinned_reference_absent",
        });
        continue;
      }
      const rows = source
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line))
        .sort((left, right) => left.start - right.start);
      cases.push({ ...item, split: splitName, rows });
    }
  }
  return {
    cases,
    denominator: {
      developmentManifest: split.groups.development.length,
      validationManifest: split.groups.validation.length,
      manifestEligibleNonHoldout:
        split.groups.development.length + split.groups.validation.length,
      availableEligibleNonHoldout: cases.length,
      unavailableEligibleNonHoldout: unavailable,
      blindHoldoutCount: split.groups.blind_holdout.length,
      blindHoldoutContentFilesOpened: 0,
    },
  };
}

async function rawChat(messages) {
  const headers = { "Content-Type": "application/json" };
  if (config.token) headers.Authorization = `Bearer ${config.token}`;
  const response = await fetch(`${config.endpoint}/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      model: config.model,
      messages,
      temperature: config.temperature,
      stream: false,
    }),
    signal: AbortSignal.timeout(config.timeoutSec * 1000),
  });
  const responseText = await response.text();
  let body;
  try {
    body = JSON.parse(responseText);
  } catch {
    throw Object.assign(new Error(`http_${response.status}_non_json`), {
      status: response.status,
      responseText,
    });
  }
  if (!response.ok) {
    const error = new Error(body?.error?.message ?? `http_${response.status}`);
    error.status = response.status;
    error.code = body?.error?.code ?? null;
    throw error;
  }
  const content = body?.choices?.[0]?.message?.content;
  if (typeof content !== "string" || content.trim() === "") {
    throw new Error("empty_completion_content");
  }
  return content;
}

function schemaRepairMessage(violations) {
  return (
    "Repair the same response. Return only one complete JSON object with exactly the five " +
    "required keys and exact value types. Schema failures: " +
    JSON.stringify(violations)
  );
}

async function callArm({ arm, baseMessages, sourceText, durationSeconds }) {
  const started = performance.now();
  const attempts = [];
  let workingMessages = baseMessages;
  let lastParsedSummary = null;
  let lastContract = null;

  for (let attempt = 1; attempt <= config.maxAttempts; attempt += 1) {
    const attemptStarted = performance.now();
    const promptChars = JSON.stringify(workingMessages).length;
    const promptEstimatedTokens = estimatedTokens(workingMessages);
    let rawOutput = null;
    let schemaViolations = [];
    let contract = null;
    let transportError = null;

    try {
      rawOutput = await rawChat(workingMessages);
      const parsed = parseSummaryOutput(rawOutput);
      schemaViolations = parsed.schemaViolations;
      if (schemaViolations.length === 0) {
        lastParsedSummary = parsed.summary;
        contract = contractProfile.validate(parsed.summary, { sourceText, durationSeconds });
        lastContract = contract;
      }
    } catch (error) {
      transportError = {
        message: error.message,
        status: error.status ?? null,
        code: error.code ?? null,
      };
    }

    const schemaValid = transportError === null && schemaViolations.length === 0;
    const contractPassed = schemaValid && contract.passed;
    const accepted =
      schemaValid && (arm === "prompt-alone" || contractPassed);
    const latencyMs = Math.round(performance.now() - attemptStarted);
    attempts.push({
      attempt,
      latencyMs,
      promptChars,
      promptEstimatedTokens,
      schemaValid,
      schemaViolations,
      contract,
      transportError,
      rawOutput,
      accepted,
    });

    if (accepted) {
      return {
        arm,
        accepted: true,
        emittedSummary: lastParsedSummary,
        finalParsedSummary: lastParsedSummary,
        finalContract: lastContract,
        attemptCount: attempts.length,
        totalLatencyMs: Math.round(performance.now() - started),
        initialPromptChars: JSON.stringify(baseMessages).length,
        attempts,
      };
    }
    if (attempt === config.maxAttempts) break;
    if (transportError !== null) {
      break;
    }

    const violations = schemaValid ? contract.violations : schemaViolations;
    const feedback =
      arm === "contract-feedback"
        ? contractProfile.feedback(violations)
        : schemaRepairMessage(schemaViolations);
    workingMessages = [
      ...workingMessages,
      { role: "assistant", content: rawOutput },
      { role: "user", content: feedback },
    ];
  }

  return {
    arm,
    accepted: false,
    emittedSummary: null,
    finalParsedSummary: lastParsedSummary,
    finalContract: lastContract,
    attemptCount: attempts.length,
    totalLatencyMs: Math.round(performance.now() - started),
    initialPromptChars: JSON.stringify(baseMessages).length,
    attempts,
  };
}

function controllerPreservationTrace() {
  let state = createSummaryState({ role: "capture", cadenceSec: 60 });
  state.lastSummarySeq = 4;
  state.pendingSeq = 5;
  state.lastGoodSummary = { summary: "prior accepted summary" };
  state.nextDueSec = 60;

  const started = reduceSummaryState(state, {
    type: "tick",
    nowSec: 60,
    requestId: "contract-1",
  });
  const coalesced = reduceSummaryState(started.state, { type: "commit", seq: 9 });
  const duringInternalAttempts = structuredClone(coalesced.state);
  const succeeded = reduceSummaryState(duringInternalAttempts, {
    type: "success",
    requestId: "contract-1",
    nowSec: 65,
    summary: { summary: "new accepted summary" },
  });
  const nextDue = reduceSummaryState(succeeded.state, {
    type: "tick",
    nowSec: 125,
    requestId: "contract-2",
  });

  return {
    premise:
      "Contract attempts remain inside one chat_completion effect; no controller action is dispatched until terminal success or failure.",
    started: started.state,
    coalescedWhileInFlight: coalesced.state,
    duringInternalAttempts,
    succeeded: succeeded.state,
    nextDue: nextDue.state,
    checks: {
      oneInFlightAcrossContractAttempts:
        duringInternalAttempts.inFlight?.requestId === "contract-1",
      highWatermarkCoalesced:
        duringInternalAttempts.pendingSeq === 9 &&
        duringInternalAttempts.inFlight?.targetSeq === 5,
      lastGoodPreservedUntilContractSuccess:
        duringInternalAttempts.lastGoodSummary?.summary === "prior accepted summary",
      nextCallStartsAtCoalescedHighWatermark:
        nextDue.state.inFlight?.targetSeq === 9,
    },
  };
}

function countBy(values) {
  const counts = {};
  for (const value of values) counts[value] = (counts[value] ?? 0) + 1;
  return counts;
}

function aggregate(cases, arm) {
  const calls = cases.map((item) => item[arm]);
  const terminalFailureCodes = calls.flatMap((call) =>
    call.finalContract?.violations.map((item) => item.code) ?? ["no_schema_valid_output"],
  );
  const everyAttemptFailureCodes = calls.flatMap((call) =>
    call.attempts.flatMap((attempt) => [
      ...attempt.schemaViolations.map((item) => item.code),
      ...(attempt.contract?.violations.map((item) => item.code) ?? []),
      ...(attempt.transportError ? ["transport_error"] : []),
    ]),
  );
  const latencies = calls.map((call) => call.totalLatencyMs).sort((a, b) => a - b);
  const percentile = (fraction) =>
    latencies[Math.min(latencies.length - 1, Math.ceil(latencies.length * fraction) - 1)];
  return {
    cases: calls.length,
    acceptedCases: calls.filter((call) => call.accepted).length,
    finalContractPassCases: calls.filter((call) => call.finalContract?.passed).length,
    casesUsingFeedbackAttempt: calls.filter((call) => call.attemptCount > 1).length,
    totalAttempts: calls.reduce((sum, call) => sum + call.attemptCount, 0),
    totalLatencyMs: calls.reduce((sum, call) => sum + call.totalLatencyMs, 0),
    medianLatencyMs: percentile(0.5),
    p95LatencyMs: percentile(0.95),
    maxLatencyMs: latencies.at(-1),
    totalInitialPromptChars: calls.reduce((sum, call) => sum + call.initialPromptChars, 0),
    terminalFailureCodes: countBy(terminalFailureCodes),
    everyAttemptFailureCodes: countBy(everyAttemptFailureCodes),
    metricAppendix: {
      acceptanceCriterion: false,
      casesWithItems: calls.filter(
        (call) => (call.finalContract?.metricAppendix?.itemCount ?? 0) > 0,
      ).length,
      totalItems: calls.reduce(
        (sum, call) => sum + (call.finalContract?.metricAppendix?.itemCount ?? 0),
        0,
      ),
    },
  };
}

function baselineFailed(caseResult) {
  const audit = caseResult.alwaysFull.audit;
  return (
    !audit.summaryAtMost25Words ||
    audit.missingSourceDigitTokens.length > 0 ||
    audit.unsupportedOutputDigitTokens.length > 0
  );
}

function renderJson(value) {
  return `\`\`\`json\n${JSON.stringify(value, null, 2)}\n\`\`\``;
}

function renderBeforeAfter(rows, denominator) {
  const sections = rows.map((item) => `## ${item.caseId}

**Prior failures:** ${JSON.stringify(item.before.audit)}

### Before — unchanged reference prompt

${renderJson(item.before.summary)}

### After — revised prompt alone

Attempts: ${item.promptAlone.attemptCount}; latency: ${item.promptAlone.totalLatencyMs} ms; deterministic contract passed: ${item.promptAlone.finalContract?.passed ?? false}.

${renderJson(item.promptAlone.finalParsedSummary)}

### After — revised prompt with exact contract feedback

Attempts: ${item.contractFeedback.attemptCount}; latency: ${item.contractFeedback.totalLatencyMs} ms; deterministic contract passed: ${item.contractFeedback.finalContract?.passed ?? false}.

${renderJson(item.contractFeedback.finalParsedSummary)}
`);
  return `# Revised summary prompt and deterministic output contract — before/after review

**PROTOTYPE — model text is shown untruncated and unmodified.**

Measured ${denominator.availableEligibleNonHoldout}/${denominator.manifestEligibleNonHoldout} available non-holdout references. This review shows every case that failed the prior prompt's measured quantity or 25-word checks.

${sections.join("\n")}`;
}

async function measureCases(cases) {
  const results = [];
  for (const [index, item] of cases.entries()) {
    const transcript = formatTranscript(item.rows);
    const sourceText = item.rows.map((row) => row.text).join(" ");
    const baseMessages = contractProfile.messages(transcript);
    const arms = index % 2 === 0
      ? ["prompt-alone", "contract-feedback"]
      : ["contract-feedback", "prompt-alone"];
    const measured = {};
    for (const arm of arms) {
      process.stderr.write(
        `[summary-contract ${index + 1}/${cases.length}] ${item.case_id} ${arm}\n`,
      );
      measured[arm] = await callArm({
        arm,
        baseMessages,
        sourceText,
        durationSeconds: item.duration_seconds,
      });
    }
    results.push({
      caseId: item.case_id,
      split: item.split,
      durationSec: item.duration_seconds,
      sourceRows: item.rows.length,
      armOrder: arms,
      promptAlone: measured["prompt-alone"],
      contractFeedback: measured["contract-feedback"],
      broaderSemanticQuality: "unmeasured pending operator review of unmodified outputs",
    });
  }
  return results;
}

async function main() {
  const loaded = await loadCases();
  const baseline = JSON.parse(await readFile(BASELINE_PATH, "utf8"));
  if (baseline.schema !== "moss-client-configured-llm-prototype.v1") {
    throw new Error("T-31 baseline result is absent or not the accepted measurement schema");
  }

  const cases = await measureCases(loaded.cases);
  const priorFailingIds = baseline.corpus.cases.filter(baselineFailed).map((item) => item.caseId);
  const beforeAfter = priorFailingIds.map((caseId) => {
    const before = baseline.corpus.cases.find((item) => item.caseId === caseId).alwaysFull;
    const after = cases.find((item) => item.caseId === caseId);
    return {
      caseId,
      before: { summary: before.summary, audit: before.audit },
      promptAlone: after.promptAlone,
      contractFeedback: after.contractFeedback,
    };
  });
  const aggregates = {
    promptAlone: aggregate(cases, "promptAlone"),
    contractFeedback: aggregate(cases, "contractFeedback"),
  };
  const controller = controllerPreservationTrace();
  const measurementValid =
    loaded.denominator.manifestEligibleNonHoldout === 16 &&
    loaded.denominator.availableEligibleNonHoldout === 15 &&
    loaded.denominator.blindHoldoutContentFilesOpened === 0 &&
    cases.length === loaded.denominator.availableEligibleNonHoldout &&
    Object.values(controller.checks).every(Boolean);
  const candidate = !measurementValid
    ? "measurement_invalid"
    : aggregates.promptAlone.finalContractPassCases === cases.length
      ? contractProfile.promptCandidate
      : aggregates.contractFeedback.finalContractPassCases === cases.length
        ? contractProfile.feedbackCandidate
        : "reject_automatic_summary_default";

  const result = {
    schema: contractProfile.schema,
    measuredAt: new Date().toISOString(),
    question: contractProfile.question,
    configuration: {
      runLabel: RUN_LABEL || "default",
      contractVersion: CONTRACT_VERSION,
      endpoint: config.endpoint,
      model: config.model,
      token: config.token ? "present-not-recorded" : "absent",
      timeoutSecPerAttempt: config.timeoutSec,
      temperature: config.temperature,
      maxAttempts: config.maxAttempts,
      targetLanguage: config.targetLanguage,
      systemPrompt: contractProfile.systemPrompt,
      systemPromptChars: contractProfile.systemPrompt.length,
      tokenEstimator: "ceil(JSON message characters / 4)",
      arms: contractProfile.arms,
    },
    corpusDenominator: loaded.denominator,
    controllerPreservation: controller,
    aggregates,
    cases,
    priorFailingCaseCount: beforeAfter.length,
    priorFailingBeforeAfter: beforeAfter,
    checks: {
      measurementValid,
      everyAvailableEligibleReferenceMeasuredInBothArms:
        cases.length === loaded.denominator.availableEligibleNonHoldout &&
        cases.every((item) => item.promptAlone.attemptCount > 0 && item.contractFeedback.attemptCount > 0),
      blindHoldoutContentFilesOpened: loaded.denominator.blindHoldoutContentFilesOpened,
      modelTextStoredUntruncated: cases.every((item) =>
        [...item.promptAlone.attempts, ...item.contractFeedback.attempts].every(
          (attempt) => attempt.transportError !== null || typeof attempt.rawOutput === "string",
        ),
      ),
      noPostInferenceTruncationOrSynthesis: true,
      exactSameInitialPromptBothArms: cases.every(
        (item) => item.promptAlone.initialPromptChars === item.contractFeedback.initialPromptChars,
      ),
    },
    recommendation: {
      candidate,
      status: "pending operator semantic and latency verdict",
      rule: contractProfile.rule,
    },
    unmeasured: [
      ...loaded.denominator.unavailableEligibleNonHoldout.map(
        (item) => `${item.caseId}: ${item.reason} at ${item.referencePath}`,
      ),
      contractProfile.semanticLimit,
      "Languages other than English",
      "Meetings longer than the available 30-minute reference",
      "Contention beside 2-4 simultaneous speech-recognition sessions",
    ],
  };

  await writeFile(RESULT_PATH, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  await writeFile(REVIEW_PATH, renderBeforeAfter(beforeAfter, loaded.denominator), "utf8");
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch(async (error) => {
  const failure = {
    schema: "moss-revised-summary-contract-prototype.failure.v1",
    measuredAt: new Date().toISOString(),
    error: error.stack ?? String(error),
  };
  await writeFile(RESULT_PATH, `${JSON.stringify(failure, null, 2)}\n`, "utf8");
  process.stderr.write(`${JSON.stringify(failure, null, 2)}\n`);
  process.exitCode = 1;
});
