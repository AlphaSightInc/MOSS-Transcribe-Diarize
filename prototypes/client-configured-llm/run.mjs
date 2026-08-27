#!/usr/bin/env node
// PROTOTYPE — one-command browser/state/prompt measurement; not production code.

import { spawn } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { startFakeEndpoint } from "./fake-endpoint.mjs";
import {
  DEFAULT_POLICY,
  chooseSummaryMode,
  createSummaryState,
  estimatedTokens,
  reduceSummaryState,
} from "./state-machine.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const SPLIT_PATH = path.join(REPO, "prototypes/streaming-diarization/l15/split-manifest.json");
const RESULT_PATH = path.join(HERE, "latest-result.json");
const MOSS_ORIGIN = "https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861";
const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const config = Object.freeze({
  endpoint: (process.env.T31_LLM_ENDPOINT ?? "http://127.0.0.1:1234/v1").replace(/\/$/, ""),
  model: process.env.T31_LLM_MODEL ?? "qwen/qwen3.6-35b-a3b",
  token: process.env.T31_LLM_TOKEN ?? "",
  cadenceSec: DEFAULT_POLICY.cadenceSec,
  timeoutSec: DEFAULT_POLICY.timeoutSec,
  temperature: DEFAULT_POLICY.temperature,
  hybridBudgetEstimatedTokens: DEFAULT_POLICY.tokenBudget,
  targetLanguage: "English",
});

const SUMMARY_SYSTEM_PROMPT = `You maintain a stabilized rolling summary of a conversation. The content may be a webinar, podcast interview, team meeting, or monologue.
Return only valid JSON.
Return an object with keys \`summary\`, \`topics\`, \`details\`, \`data_references\`, \`speaker_background\`.

Use only facts that are directly supported by the transcript. Do not invent roles, motives, labels, or outside context.

For \`summary\`: a single concise sentence (1-2 sentences max) that captures the overall theme of the conversation.

For \`topics\`: an array of objects, each with \`title\` (string, short descriptive heading) and \`description\` (string, a compact paragraph summarizing one major thread of discussion). Group related content into 1-4 high-level topics. Each topic title should be descriptive and specific, not generic.

For \`details\`: an array of objects, each with \`title\` (string, short heading), \`description\` (string, a factual paragraph describing the specific claim, argument, or event), and \`timestamp\` (string, the approximate start time in HH:MM:SS format based on transcript timestamps, or '' if not available). Details should be chronological and cover the substantive discussion points without repeating the same fact many times.

For \`data_references\`: an array of objects extracting every explicit number, date, year, percentage, money amount, or other quantitative claim mentioned in the conversation. This field is high priority: missing a concrete quantity is a serious error. Each object has: \`item\` (string, a short local description grounded in the transcript), \`value\` (string, copy the quantity verbatim), and \`context\` (string, brief local context from the transcript). Return an empty array if no quantitative data was mentioned.

For \`speaker_background\`: an array of strings. Include an entry only when the transcript explicitly states a speaker's role, title, or background, or when a speaker clearly self-identifies. Each entry MUST use \`Name: role/background\` format. If the transcript does not explicitly identify speakers or roles, return an empty array.

Do not drop supported facts when you condense. Preserve specific names, numbers, claims, dates, and arguments made by speakers.
Do not create company-specific or industry-specific metric taxonomies. Keep labels generic and local to the transcript.
Use descriptive, content-specific section titles — not generic labels like 'Discussion' or 'Topic 1'.

CRITICAL: Write every string value in the summary JSON entirely in English.
CUSTOM USER DIRECTIVE: obey the user's custom prompt unless it conflicts with the required JSON schema or factual preservation.
Apply the custom directive inside the JSON field values, never outside the required JSON object.`;

const DEFAULT_SUMMARY_DIRECTIVE = `Produce a structured executive-style summary that a busy reader can scan in 30 seconds:
- summary: ONE short sentence (≤25 words, ≈2 lines) naming the central thesis or claim. Lead with the subject and the single most important point — do NOT enumerate sub-topics, names, dates, or quantities here (those belong in topics/details/data_references). Hard limit: 25 words; if you exceed it, rewrite shorter.
- topics: 2-4 entries. Each title must be a noun-phrase headline (no generic words like 'Discussion'). Each description must be 2-3 short sentences that name the speaker, the claim, and the supporting fact.
- details: chronological timeline of substantive moments (not every line). Each title is a 4-8 word headline. Each description is 1-2 sentences with the speaker name and the explicit claim. Include timestamp in HH:MM:SS for every detail when transcript timestamps exist.
- data_references: extract EVERY number, percentage, date, money amount, year, and duration mentioned in the spoken content. Be exhaustive - missing one is a serious error. Each entry: item (what is measured), value (the figure verbatim with unit), context (1 short clause from the transcript). Do not list transcript timestamps as data references.
- speaker_background: include only when the transcript explicitly states a role/title/background. Use 'Name: role and background details' format. Empty array if not stated.
- Stay grounded in the transcript - do not infer beyond what is said.`;

function summaryMessages(transcript, previousSummary = null) {
  const directive = `\n\n${DEFAULT_SUMMARY_DIRECTIVE}`;
  if (previousSummary === null) {
    return [
      { role: "system", content: SUMMARY_SYSTEM_PROMPT },
      {
        role: "user",
        content: `Create the first rolling summary from the full authoritative transcript.\nReturn only the required JSON object.\n\nTRANSCRIPT:\n${transcript}${directive}`,
      },
    ];
  }
  return [
    { role: "system", content: SUMMARY_SYSTEM_PROMPT },
    {
      role: "user",
      content: `Update the rolling summary using the previous summary and transcript input.\nRewrite every retained or updated summary item in English.\nReturn only JSON with keys \`summary\`, \`topics\`, \`details\`, \`data_references\`, \`speaker_background\`.\n\nPREVIOUS_SUMMARY:\n${JSON.stringify(previousSummary)}\n\nTRANSCRIPT_INPUT:\n${transcript}${directive}`,
    },
  ];
}

function parseSummary(content) {
  let candidate = content.trim();
  if (candidate.startsWith("```")) {
    candidate = candidate.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  }
  const first = candidate.indexOf("{");
  const last = candidate.lastIndexOf("}");
  if (first >= 0 && last > first) candidate = candidate.slice(first, last + 1);
  const parsed = JSON.parse(candidate);
  const valid =
    parsed !== null &&
    typeof parsed === "object" &&
    typeof parsed.summary === "string" &&
    Array.isArray(parsed.topics) &&
    parsed.topics.every((item) => typeof item?.title === "string" && typeof item?.description === "string") &&
    Array.isArray(parsed.details) &&
    parsed.details.every(
      (item) =>
        typeof item?.title === "string" &&
        typeof item?.description === "string" &&
        typeof item?.timestamp === "string",
    ) &&
    Array.isArray(parsed.data_references) &&
    parsed.data_references.every(
      (item) =>
        typeof item?.item === "string" &&
        typeof item?.value === "string" &&
        typeof item?.context === "string",
    ) &&
    Array.isArray(parsed.speaker_background) &&
    parsed.speaker_background.every((item) => typeof item === "string");
  if (!valid) throw new Error("summary_schema_invalid");
  return parsed;
}

async function rawChat({ endpoint, model, token, messages, scenario = null, timeoutSec }) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (scenario) headers["X-Prototype-Scenario"] = scenario;
  const response = await fetch(`${endpoint}/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify({ model, messages, temperature: 0, stream: false }),
    signal: AbortSignal.timeout(timeoutSec * 1000),
  });
  const text = await response.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    throw Object.assign(new Error(`http_${response.status}_non_json`), { status: response.status, text });
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

async function callSummary({ messages, endpoint = config.endpoint, model = config.model, token = config.token, scenario = null }) {
  const started = performance.now();
  const attempts = [];
  let workingMessages = messages;
  for (let attempt = 1; attempt <= DEFAULT_POLICY.maxJsonAttempts; attempt += 1) {
    const attemptStarted = performance.now();
    let content;
    try {
      content = await rawChat({
        endpoint,
        model,
        token,
        messages: workingMessages,
        scenario,
        timeoutSec: config.timeoutSec,
      });
      const summary = parseSummary(content);
      attempts.push({ attempt, latencyMs: Math.round(performance.now() - attemptStarted), schemaValid: true });
      return {
        summary,
        attempts,
        latencyMs: Math.round(performance.now() - started),
        promptChars: JSON.stringify(messages).length,
        estimatedInputTokens: estimatedTokens(messages),
      };
    } catch (error) {
      attempts.push({
        attempt,
        latencyMs: Math.round(performance.now() - attemptStarted),
        schemaValid: false,
        error: error.message,
        status: error.status ?? null,
        code: error.code ?? null,
      });
      if (error.code === "context_length_exceeded" || error.status === 413) throw error;
      if (attempt === DEFAULT_POLICY.maxJsonAttempts) {
        throw Object.assign(new Error("three_json_attempts_exhausted"), { attempts });
      }
      workingMessages = [
        ...messages,
        ...(content ? [{ role: "assistant", content }] : []),
        {
          role: "user",
          content: "Repair the response. Return only one valid JSON object with the five required keys and exact value types.",
        },
      ];
    }
  }
  throw new Error("unreachable");
}

function runAgentBrowser(session, args, { ignoreHttpsErrors = false, timeoutMs = 300_000 } = {}) {
  const flags = ["--session", session, "--executable-path", CHROME_PATH];
  if (ignoreHttpsErrors) flags.push("--ignore-https-errors");
  return new Promise((resolve) => {
    const child = spawn("agent-browser", [...flags, ...args, "--json"], {
      env: { ...process.env, AGENT_BROWSER_EXECUTABLE_PATH: CHROME_PATH },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    const timer = setTimeout(() => child.kill("SIGTERM"), timeoutMs);
    child.on("close", (code, signal) => {
      clearTimeout(timer);
      const output = `${stdout}${stderr}`.trim();
      const lastLine = output.split("\n").filter(Boolean).at(-1);
      let parsed = null;
      try {
        parsed = JSON.parse(lastLine);
      } catch {
        parsed = { raw: output };
      }
      resolve({ exitCode: code, signal, result: parsed });
    });
  });
}

async function closeBrowser(session, ignoreHttpsErrors = false) {
  await runAgentBrowser(session, ["close"], {
    ignoreHttpsErrors,
    timeoutMs: 30_000,
  });
}

async function measureBrowser(fake) {
  const strictSession = `t31-strict-${process.pid}`;
  const bypassSession = `t31-bypass-${process.pid}`;
  const strict = await runAgentBrowser(strictSession, ["open", MOSS_ORIGIN]);
  await closeBrowser(strictSession);

  const bypassOpen = await runAgentBrowser(
    bypassSession,
    ["open", MOSS_ORIGIN],
    { ignoreHttpsErrors: true },
  );
  const browserScript = `(async()=>{
    const permission = async()=>{try{return await Promise.race([(async()=>({state:(await navigator.permissions.query({name:"local-network-access"})).state}))(),new Promise(resolve=>setTimeout(()=>resolve({state:"query_timeout"}),1000))])}catch(e){return {state:e.name+":"+e.message}}};
    const localNetworkAccess=await permission();
    const fakeResponse=await fetch(${JSON.stringify(`${fake.url}/chat/completions`)},{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer fake-token","X-Prototype-Scenario":"browser-valid"},body:JSON.stringify({model:"deterministic-fake",messages:[{role:"user",content:"valid"}],temperature:0,stream:false})});
    const fakeBody=await fakeResponse.json();
    const controller=new AbortController();
    const cancelStarted=performance.now();
    const pending=fetch(${JSON.stringify(`${fake.url}/chat/completions?scenario=cancel`)},{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"deterministic-fake",messages:[{role:"user",content:"cancel"}],temperature:0,stream:false}),signal:controller.signal}).then(()=>({resolved:true})).catch(e=>({resolved:false,error:e.name+":"+e.message}));
    queueMicrotask(()=>controller.abort());
    const cancelled=await pending;
    return {
      chromeUserAgent:navigator.userAgent,
      origin:location.origin,
      isSecureContext,
      pageTitle:document.title,
      localNetworkAccessPermission:localNetworkAccess.state,
      fakeNonStream:{ok:fakeResponse.ok,status:fakeResponse.status,responseType:fakeResponse.type,parsedSummary:JSON.parse(fakeBody.choices[0].message.content)},
      cancellation:{...cancelled,latencyMs:Math.round(performance.now()-cancelStarted)}
    };
  })()`;
  const evaluation = await runAgentBrowser(
    bypassSession,
    ["eval", browserScript],
    { ignoreHttpsErrors: true },
  );
  await new Promise((resolve) => setTimeout(resolve, 100));
  await closeBrowser(bypassSession, true);
  return {
    chromeVersionCommand: `${CHROME_PATH} --version`,
    strictCertificateNavigation: strict,
    certificateBypassNavigation: bypassOpen,
    pageEvaluation: evaluation,
    fakeEndpointObservations: fake.observations,
  };
}

function applyTrace(state, action, trace) {
  const result = reduceSummaryState(state, action);
  trace.push({ action, effects: result.effects, state: result.state });
  return result.state;
}

async function measureStateMachine(fake) {
  const trace = [];
  let state = createSummaryState();
  state = applyTrace(state, { type: "commit", seq: 5 }, trace);
  state = applyTrace(state, { type: "tick", nowSec: 59, requestId: "r1" }, trace);
  state = applyTrace(state, { type: "tick", nowSec: 60, requestId: "r1" }, trace);
  state = applyTrace(state, { type: "commit", seq: 9 }, trace);
  state = applyTrace(state, { type: "tick", nowSec: 61, requestId: "r2" }, trace);
  state = applyTrace(
    state,
    { type: "success", nowSec: 62, requestId: "r1", summary: { summary: "good-1" } },
    trace,
  );
  state = applyTrace(state, { type: "tick", nowSec: 121, requestId: "r2" }, trace);
  state = applyTrace(state, { type: "tick", nowSec: 122, requestId: "r2" }, trace);

  const backoffTrace = [];
  let backoff = createSummaryState();
  backoff = applyTrace(backoff, { type: "commit", seq: 1 }, backoffTrace);
  const backoffTimes = [60, 120, 240, 480];
  for (const [index, nowSec] of backoffTimes.entries()) {
    const requestId = `b${index + 1}`;
    backoff = applyTrace(backoff, { type: "tick", nowSec, requestId }, backoffTrace);
    backoff = applyTrace(
      backoff,
      { type: "failure", requestId, nowSec, reason: "scripted" },
      backoffTrace,
    );
  }

  const cancelTrace = [];
  let cancel = createSummaryState();
  cancel = applyTrace(cancel, { type: "commit", seq: 1 }, cancelTrace);
  cancel = applyTrace(cancel, { type: "tick", nowSec: 60, requestId: "c1" }, cancelTrace);
  cancel = applyTrace(
    cancel,
    { type: "success", requestId: "c1", nowSec: 61, summary: { summary: "last-good" } },
    cancelTrace,
  );
  cancel = applyTrace(cancel, { type: "commit", seq: 2 }, cancelTrace);
  cancel = applyTrace(cancel, { type: "tick", nowSec: 121, requestId: "c2" }, cancelTrace);
  cancel = applyTrace(cancel, { type: "cancel" }, cancelTrace);

  const roleResults = {};
  for (const role of ["history", "view"]) {
    let roleState = createSummaryState({ role });
    roleState = reduceSummaryState(roleState, { type: "commit", seq: 10 }).state;
    const tick = reduceSummaryState(roleState, { type: "tick", nowSec: 600, requestId: role });
    roleResults[role] = { callEffects: tick.effects.length, state: tick.state };
  }

  const contextTrace = [];
  let context = createSummaryState();
  context.lastGoodSummary = { summary: "prior" };
  context.lastSummarySeq = 1;
  context.pendingSeq = 2;
  context.nextDueSec = 60;
  context = applyTrace(context, { type: "tick", nowSec: 60, requestId: "x1" }, contextTrace);
  context = applyTrace(
    context,
    { type: "context_rejected", requestId: "x1", nowSec: 60 },
    contextTrace,
  );
  context = applyTrace(
    context,
    { type: "success", requestId: "x1", nowSec: 61, summary: { summary: "delta-good" } },
    contextTrace,
  );

  const repair = await callSummary({
    messages: summaryMessages("[00:00:00] Speaker 1: deterministic"),
    endpoint: fake.url,
    model: "deterministic-fake",
    token: "",
    scenario: "repair",
  });

  let contextHttp;
  try {
    await callSummary({
      messages: summaryMessages("full", { summary: "prior", topics: [], details: [], data_references: [], speaker_background: [] }),
      endpoint: fake.url,
      model: "deterministic-fake",
      token: "",
      scenario: "context",
    });
    contextHttp = { firstRejected: false };
  } catch (error) {
    const retry = await callSummary({
      messages: summaryMessages("delta", { summary: "prior", topics: [], details: [], data_references: [], speaker_background: [] }),
      endpoint: fake.url,
      model: "deterministic-fake",
      token: "",
      scenario: "context",
    });
    contextHttp = {
      firstRejected: error.code === "context_length_exceeded",
      retryCount: 1,
      retrySchemaValid: retry.attempts.at(-1).schemaValid,
    };
  }

  return {
    highWatermarkAndSingleFlightTrace: trace,
    backoffTrace,
    cancelTrace,
    nonCaptureRoles: roleResults,
    contextFallbackTrace: contextTrace,
    jsonRepair: repair,
    contextHttp,
    checks: {
      firstCallAt60Sec: trace[2].effects[0]?.targetSeq === 5,
      oneInFlight: trace[4].effects.length === 0,
      highWatermarkCoalesced: trace.at(-1).effects[0]?.targetSeq === 9,
      backoffSequence:
        JSON.stringify(
          backoffTrace.flatMap((row) => row.effects).filter((effect) => effect.type === "schedule").map((effect) => effect.backoffSec),
        ) === JSON.stringify([60, 120, 240, 480]),
      cancelPreservedLastGood: cancel.lastGoodSummary?.summary === "last-good",
      historyCalls: roleResults.history.callEffects,
      viewCalls: roleResults.view.callEffects,
      repairsUsedExactlyThreeAttempts: repair.attempts.length === 3,
      contextRetriedOnceAndSticky: contextHttp.retryCount === 1 && context.stickyDelta,
      eventVocabularyOnly: [...trace, ...backoffTrace, ...cancelTrace, ...contextTrace]
        .flatMap((row) => row.state.events)
        .every((event) => ["llm_status", "llm_summary_update"].includes(event.type)),
    },
  };
}

function timestamp(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = String(Math.floor(value / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((value % 3600) / 60)).padStart(2, "0");
  const secs = String(value % 60).padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
}

function formatTranscript(segments) {
  return segments
    .map((segment) => `[${timestamp(segment.start)}] ${segment.speaker || "Speaker"}: ${segment.text}`)
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
      development: split.groups.development.length,
      validation: split.groups.validation.length,
      manifestEligibleNonHoldout:
        split.groups.development.length + split.groups.validation.length,
      availableEligibleNonHoldout: cases.length,
      unavailableEligibleNonHoldout: unavailable,
      blindHoldoutListedButContentFilesOpened: 0,
      blindHoldoutCount: split.groups.blind_holdout.length,
    },
  };
}

function numericTokens(text) {
  return [...new Set((text.match(/[$€£]?\d[\d,]*(?:\.\d+)?%?/g) ?? []).map((token) => token.replaceAll(",", "").toLowerCase()))].sort();
}

function auditSummary(summary, rows, durationSeconds) {
  const sourceText = rows.map((row) => row.text).join(" ");
  const sourceNumbers = numericTokens(sourceText);
  const outputNumbers = numericTokens(summary.data_references.map((item) => item.value).join(" "));
  const sourceSpeakers = new Set(rows.map((row) => String(row.speaker).toLowerCase()));
  const unsupportedBackgroundNames = summary.speaker_background
    .map((item) => item.split(":", 1)[0].trim())
    .filter(
      (name) =>
        name &&
        !sourceSpeakers.has(name.toLowerCase()) &&
        !sourceText.toLowerCase().includes(name.toLowerCase()),
    );
  const missingDetailTimestamps = summary.details.filter((item) => item.timestamp === "").length;
  const invalidDetailTimestamps = summary.details.filter((item) => {
    if (!/^\d{2}:\d{2}:\d{2}$/.test(item.timestamp)) return item.timestamp !== "";
    const [hours, minutes, seconds] = item.timestamp.split(":").map(Number);
    return hours * 3600 + minutes * 60 + seconds > durationSeconds + 1;
  }).length;
  return {
    summaryWordCount: summary.summary.trim().split(/\s+/).filter(Boolean).length,
    summaryAtMost25Words: summary.summary.trim().split(/\s+/).filter(Boolean).length <= 25,
    topicCount: summary.topics.length,
    topicCountInDefaultRange: summary.topics.length >= 2 && summary.topics.length <= 4,
    detailCount: summary.details.length,
    missingDetailTimestamps,
    invalidDetailTimestamps,
    sourceDigitTokenCount: sourceNumbers.length,
    outputDataReferenceDigitTokenCount: outputNumbers.length,
    missingSourceDigitTokens: sourceNumbers.filter((token) => !outputNumbers.includes(token)),
    unsupportedOutputDigitTokens: outputNumbers.filter((token) => !sourceNumbers.includes(token)),
    unsupportedBackgroundNames,
    broaderSemanticFactualDefects: "unmeasured",
    spelledNumberCoverage: "unmeasured",
  };
}

function publicCallResult(call, rows, durationSeconds) {
  return {
    latencyMs: call.latencyMs,
    promptChars: call.promptChars,
    estimatedInputTokens: call.estimatedInputTokens,
    attempts: call.attempts,
    repairCount: call.attempts.length - 1,
    summary: call.summary,
    audit: auditSummary(call.summary, rows, durationSeconds),
  };
}

function syntheticSummary(caseId, cutoff) {
  return {
    summary: `${caseId} through ${timestamp(cutoff)}.`,
    topics: [{ title: "Measured prefix", description: "Deterministic fake summary for policy sizing." }],
    details: [],
    data_references: [],
    speaker_background: [],
  };
}

function replayPolicies(cases) {
  const strategies = ["always-full", "always-delta", "hybrid"];
  const byStrategy = Object.fromEntries(strategies.map((strategy) => [strategy, []]));
  for (const item of cases) {
    for (const strategy of strategies) {
      const cadencePoints = [];
      for (let point = config.cadenceSec; point < item.duration_seconds; point += config.cadenceSec) {
        cadencePoints.push(point);
      }
      cadencePoints.push(item.duration_seconds);
      let previousSummary = null;
      let previousCount = 0;
      let previousLatencySec = 1;
      const calls = [];
      for (const point of cadencePoints) {
        const current = item.rows.filter((row) => row.end <= point + 0.001);
        if (current.length === previousCount) continue;
        const fullTranscript = formatTranscript(current);
        const deltaTranscript = formatTranscript(current.slice(previousCount));
        const fullMessages = summaryMessages(fullTranscript, previousSummary);
        const decision = chooseSummaryMode({
          strategy,
          fullMessages,
          hasPreviousSummary: previousSummary !== null,
          previousLatencySec,
          tokenBudget: config.hybridBudgetEstimatedTokens,
        });
        const selectedMessages =
          decision.mode === "full"
            ? fullMessages
            : summaryMessages(deltaTranscript, previousSummary);
        calls.push({
          atSec: point,
          targetRows: current.length,
          mode: decision.mode,
          reason: decision.reason,
          fullEstimatedTokens: decision.fullEstimatedTokens,
          selectedEstimatedTokens: estimatedTokens(selectedMessages),
        });
        previousSummary = syntheticSummary(item.case_id, point);
        previousCount = current.length;
        previousLatencySec = 1;
      }
      byStrategy[strategy].push({
        caseId: item.case_id,
        calls,
        totalEstimatedInputTokens: calls.reduce((sum, call) => sum + call.selectedEstimatedTokens, 0),
        firstDeltaAtSec: calls.find((call) => call.mode === "delta")?.atSec ?? null,
      });
    }
  }
  const totals = Object.fromEntries(
    strategies.map((strategy) => [
      strategy,
      {
        cases: byStrategy[strategy].length,
        calls: byStrategy[strategy].reduce((sum, item) => sum + item.calls.length, 0),
        totalEstimatedInputTokens: byStrategy[strategy].reduce(
          (sum, item) => sum + item.totalEstimatedInputTokens,
          0,
        ),
        casesEnteringDelta: byStrategy[strategy].filter((item) => item.firstDeltaAtSec !== null).length,
      },
    ]),
  );
  const slowBranch = chooseSummaryMode({
    strategy: "hybrid",
    fullMessages: summaryMessages("short", syntheticSummary("slow", 60)),
    hasPreviousSummary: true,
    previousLatencySec: 61,
  });
  return { totals, cases: byStrategy, injectedPreviousLatency61Sec: slowBranch };
}

async function measureCorpus(cases) {
  const results = [];
  let actualRequestCount = 0;
  for (const [index, item] of cases.entries()) {
    process.stderr.write(`[T-31 model ${index + 1}/${cases.length}] ${item.case_id}\n`);
    const duration = item.duration_seconds;
    const fullTranscript = formatTranscript(item.rows);
    if (duration <= config.cadenceSec) {
      const first = await callSummary({ messages: summaryMessages(fullTranscript) });
      actualRequestCount += first.attempts.length;
      const shared = publicCallResult(first, item.rows, duration);
      results.push({
        caseId: item.case_id,
        split: item.split,
        durationSec: duration,
        sourceRows: item.rows.length,
        comparisonShape: "first-summary-only; all three policies identical",
        policyDecision: { mode: "full", reason: "first_summary" },
        seed: null,
        alwaysFull: shared,
        alwaysDelta: shared,
        hybrid: shared,
      });
      continue;
    }

    const seedCutoff = Math.max(
      config.cadenceSec,
      Math.floor(duration / 2 / config.cadenceSec) * config.cadenceSec,
    );
    const seedRows = item.rows.filter((row) => row.end <= seedCutoff + 0.001);
    const finalDeltaRows = item.rows.slice(seedRows.length);
    const seed = await callSummary({ messages: summaryMessages(formatTranscript(seedRows)) });
    actualRequestCount += seed.attempts.length;
    const fullMessages = summaryMessages(fullTranscript, seed.summary);
    const deltaMessages = summaryMessages(formatTranscript(finalDeltaRows), seed.summary);
    const order = index % 2 === 0 ? ["full", "delta"] : ["delta", "full"];
    const terminal = {};
    for (const arm of order) {
      terminal[arm] = await callSummary({ messages: arm === "full" ? fullMessages : deltaMessages });
      actualRequestCount += terminal[arm].attempts.length;
    }
    const decision = chooseSummaryMode({
      strategy: "hybrid",
      fullMessages,
      hasPreviousSummary: true,
      previousLatencySec: seed.latencyMs / 1000,
      tokenBudget: config.hybridBudgetEstimatedTokens,
    });
    const fullPublic = publicCallResult(terminal.full, item.rows, duration);
    const deltaPublic = publicCallResult(terminal.delta, item.rows, duration);
    results.push({
      caseId: item.case_id,
      split: item.split,
      durationSec: duration,
      sourceRows: item.rows.length,
      comparisonShape: "seed prefix then same terminal target; full and delta both measured",
      terminalArmOrder: order,
      seedCutoffSec: seedCutoff,
      seedRows: seedRows.length,
      deltaRows: finalDeltaRows.length,
      policyDecision: decision,
      seed: publicCallResult(seed, seedRows, seedCutoff),
      alwaysFull: fullPublic,
      alwaysDelta: deltaPublic,
      hybrid: decision.mode === "full" ? fullPublic : deltaPublic,
    });
  }
  const armAggregate = {};
  for (const arm of ["alwaysFull", "alwaysDelta", "hybrid"]) {
    const measured = results.map((item) => item[arm]);
    armAggregate[arm] = {
      cases: measured.length,
      schemaValidCases: measured.filter((item) => item.attempts.at(-1).schemaValid).length,
      totalRepairs: measured.reduce((sum, item) => sum + item.repairCount, 0),
      totalPromptChars: measured.reduce((sum, item) => sum + item.promptChars, 0),
      totalEstimatedInputTokens: measured.reduce((sum, item) => sum + item.estimatedInputTokens, 0),
      totalLatencyMs: measured.reduce((sum, item) => sum + item.latencyMs, 0),
      summaryLengthViolations: measured.filter((item) => !item.audit.summaryAtMost25Words).length,
      topicCountViolations: measured.filter((item) => !item.audit.topicCountInDefaultRange).length,
      casesWithMissingDigitReferences: measured.filter(
        (item) => item.audit.missingSourceDigitTokens.length > 0,
      ).length,
      casesWithUnsupportedDigitReferences: measured.filter(
        (item) => item.audit.unsupportedOutputDigitTokens.length > 0,
      ).length,
      casesWithUnsupportedBackgroundNames: measured.filter(
        (item) => item.audit.unsupportedBackgroundNames.length > 0,
      ).length,
    };
  }
  return {
    actualHttpRequestCountIncludingRepairs: actualRequestCount,
    terminalPolicyOutputs: results.length * 3,
    independentTerminalCalls: results.filter((item) => item.seed !== null).length * 2 + results.filter((item) => item.seed === null).length,
    cases: results,
    armAggregate,
    semanticComparisonLimit:
      "Machine checks cover schema, default shape, digit-bearing data references, timestamps, and speaker-background names. Broader factual/semantic quality remains unmeasured pending human review.",
  };
}

function browserResultData(browser) {
  return browser.pageEvaluation?.result?.data?.result ?? null;
}

async function main() {
  const fake = await startFakeEndpoint({ allowedOrigin: MOSS_ORIGIN });
  let browser;
  let stateMachine;
  try {
    browser = await measureBrowser(fake);
    stateMachine = await measureStateMachine(fake);
  } finally {
    await fake.close();
  }
  const loaded = await loadCases();
  const policyReplay = replayPolicies(loaded.cases);
  const corpus = await measureCorpus(loaded.cases);
  const browserData = browserResultData(browser);
  const result = {
    schema: "moss-client-configured-llm-prototype.v1",
    measuredAt: new Date().toISOString(),
    question:
      "Does the supported Chrome client-owned LLM path work, and do the adapted prompt and hybrid policy earn defaults?",
    configuration: {
      mossOrigin: MOSS_ORIGIN,
      chromeExecutable: CHROME_PATH,
      endpoint: config.endpoint,
      model: config.model,
      token: config.token ? "present-not-recorded" : "absent",
      prompts: {
        systemChars: SUMMARY_SYSTEM_PROMPT.length,
        customDirectiveChars: DEFAULT_SUMMARY_DIRECTIVE.length,
      },
      cadenceSec: config.cadenceSec,
      timeoutSec: config.timeoutSec,
      temperature: config.temperature,
      hybridBudgetEstimatedTokens: config.hybridBudgetEstimatedTokens,
      tokenEstimator: "ceil(JSON request characters / 4)",
      targetLanguage: config.targetLanguage,
      requiredModelsRoute: false,
    },
    browser,
    stateMachine,
    corpusDenominator: loaded.denominator,
    policyReplay,
    corpus,
    checks: {
      strictOriginRejectedForCertificate:
        browser.strictCertificateNavigation.exitCode !== 0 &&
        JSON.stringify(browser.strictCertificateNavigation).includes("ERR_CERT_AUTHORITY_INVALID"),
      bypassOriginIsSecureContext: browserData?.isSecureContext === true,
      browserOpenAiPostSucceeded: browserData?.fakeNonStream?.ok === true,
      browserNonStreamParsed: typeof browserData?.fakeNonStream?.parsedSummary?.summary === "string",
      fakeBrowserCorsSucceeded:
        browserData?.fakeNonStream?.ok === true && browserData?.fakeNonStream?.responseType === "cors",
      browserCancellationRejectedPromptly:
        browserData?.cancellation?.resolved === false &&
        String(browserData?.cancellation?.error).startsWith("AbortError:") &&
        browserData?.cancellation?.latencyMs < 1000,
      fakePreflightObserved: browser.fakeEndpointObservations.some(
        (row) => row.method === "OPTIONS" && row.accessControlRequestMethod === "POST",
      ),
      stateMachine: stateMachine.checks,
      exactManifestTranscriptDenominator:
        loaded.denominator.manifestEligibleNonHoldout === 16,
      holdoutContentFilesOpened: loaded.denominator.blindHoldoutListedButContentFilesOpened,
      everyAvailableEligibleTranscriptMeasured:
        corpus.cases.length === loaded.denominator.availableEligibleNonHoldout,
    },
    unmeasured: [
      "Non-loopback LAN endpoints and their Local Network Access prompt behavior",
      "Browsers other than installed Google Chrome 151",
      "Cloud endpoints requiring a real bearer token",
      "Meetings longer than the standing 30-minute non-holdout maximum",
      "Languages other than English",
      "Broader semantic factuality beyond the recorded machine-checkable audit",
      "Contention with 2-4 simultaneous ASR sessions",
      ...loaded.denominator.unavailableEligibleNonHoldout.map(
        (item) => `${item.caseId}: ${item.reason} at ${item.referencePath}`,
      ),
    ],
  };
  await writeFile(RESULT_PATH, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch(async (error) => {
  const failure = {
    schema: "moss-client-configured-llm-prototype.failure.v1",
    measuredAt: new Date().toISOString(),
    error: error.stack ?? String(error),
  };
  await writeFile(RESULT_PATH, `${JSON.stringify(failure, null, 2)}\n`, "utf8");
  process.stderr.write(`${JSON.stringify(failure, null, 2)}\n`);
  process.exitCode = 1;
});
