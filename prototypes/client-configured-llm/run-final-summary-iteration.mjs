#!/usr/bin/env node
// PROTOTYPE — question: can prompt changes increase relevant data-reference coverage above the
// V10 baseline (3/7 summaries, 4 entries) while preserving 7/7 raw valid JSON? One final-summary
// call per finalized recording; no rolling summaries or retries.

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  parseSummaryOutput,
  validateInsightSummaryStructure,
} from "./summary-contract.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const SPLIT_PATH = path.join(REPO, "prototypes/streaming-diarization/l15/split-manifest.json");
const PROMPT_PATH = path.join(HERE, "final-summary-prompt.txt");
const FINAL_CASE_IDS = [
  "5m-acquired-nfl",
  "5m-acquired-jamie-dimon",
  "30m-lex-bill-ackman",
  "5m-lex-javier-milei",
  "3m-lex-adam-frank",
  "3m-lex-shapiro-destiny",
  "5m-acquired-alphabet",
];
const EXCLUDED_INTERIM_CASE_IDS = [
  "1m-acquired-nfl",
  "1m-acquired-jamie-dimon",
  "3m-acquired-jamie-dimon",
  "5m-lex-bill-ackman",
  "1m-lex-bill-ackman",
  "1m-lex-javier-milei",
];
const iteration = Number(process.env.T33_PROMPT_ITERATION);
if (!Number.isInteger(iteration) || iteration < 1 || iteration > 15) {
  throw new Error("T33_PROMPT_ITERATION must be an integer from 1 through 15");
}
const suffix = String(iteration).padStart(2, "0");
const RESULT_PATH = path.join(HERE, `final-summary-iteration-${suffix}.json`);
const REVIEW_PATH = path.join(HERE, `final-summary-iteration-${suffix}.md`);
const config = {
  endpoint: (process.env.T33_LLM_ENDPOINT ?? "https://openrouter.ai/api/v1").replace(/\/$/, ""),
  model: process.env.T33_LLM_MODEL ?? "google/gemini-3.5-flash-lite",
  token: process.env.T33_LLM_TOKEN ?? "",
  timeoutMs: 240_000,
};

function timestamp(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  return [Math.floor(value / 3600), Math.floor((value % 3600) / 60), value % 60]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

function formatTranscript(rows) {
  return rows
    .map((row) => `[${timestamp(row.start)}] ${row.speaker || "Speaker"}: ${row.text}`)
    .join("\n");
}

async function loadCases() {
  const split = JSON.parse(await readFile(SPLIT_PATH, "utf8"));
  const indexed = new Map(
    [...split.groups.development, ...split.groups.validation].map((item) => [item.case_id, item]),
  );
  const cases = [];
  for (const caseId of FINAL_CASE_IDS) {
    const item = indexed.get(caseId);
    if (!item) throw new Error(`final case absent from non-holdout manifest: ${caseId}`);
    const source = await readFile(path.join(REPO, item.reference_path), "utf8");
    const rows = source
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line))
      .sort((left, right) => left.start - right.start);
    cases.push({ ...item, rows });
  }
  return cases;
}

async function rawChat(messages) {
  const headers = { "Content-Type": "application/json" };
  if (config.token) headers.Authorization = `Bearer ${config.token}`;
  const response = await fetch(`${config.endpoint}/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify({ model: config.model, messages, temperature: 0, stream: false }),
    signal: AbortSignal.timeout(config.timeoutMs),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.error?.message ?? `http_${response.status}`);
  const content = body?.choices?.[0]?.message?.content;
  if (typeof content !== "string" || content.trim() === "") throw new Error("empty completion");
  return { content, resolvedModel: body.model ?? null, provider: body.provider ?? null, usage: body.usage ?? null };
}

function renderReview(result) {
  const sections = result.cases.map((item) => `## ${item.caseId}

Latency: ${item.latencyMs} ms; structure: ${item.structurePassed ? "pass" : "fail"}; metrics: ${item.parsedSummary?.data_references.length ?? 0}.

\`\`\`json
${JSON.stringify(item.parsedSummary, null, 2)}
\`\`\``);
  return `# Final-summary prompt iteration ${result.iteration}

**PROTOTYPE — exactly one model call per finalized recording; no rolling summaries or repair calls.**

${sections.join("\n\n")}
`;
}

async function main() {
  const prompt = (await readFile(PROMPT_PATH, "utf8")).trim();
  const cases = [];
  for (const item of await loadCases()) {
    process.stderr.write(`[final-summary prompt-v${iteration}] ${item.case_id}\n`);
    const transcript = formatTranscript(item.rows);
    const sourceText = item.rows.map((row) => row.text).join(" ");
    const started = performance.now();
    let completion = null;
    let parsedSummary = null;
    let schemaViolations = [];
    let structure = null;
    let error = null;
    try {
      completion = await rawChat([
        { role: "system", content: prompt },
        {
          role: "user",
          content:
            "Create the sole final summary from this complete finalized transcript. There is no prior or rolling summary.\n\n" +
            `FINAL TRANSCRIPT:\n${transcript}`,
        },
      ]);
      const parsed = parseSummaryOutput(completion.content);
      parsedSummary = parsed.summary;
      schemaViolations = parsed.schemaViolations;
      if (schemaViolations.length === 0) {
        structure = validateInsightSummaryStructure(parsedSummary, {
          sourceText,
          durationSeconds: item.duration_seconds,
        });
      }
    } catch (caught) {
      error = caught.message;
    }
    cases.push({
      caseId: item.case_id,
      durationSec: item.duration_seconds,
      sourceRows: item.rows.length,
      latencyMs: Math.round(performance.now() - started),
      error,
      resolvedModel: completion?.resolvedModel ?? null,
      provider: completion?.provider ?? null,
      usage: completion?.usage ?? null,
      strictJsonOnly:
        typeof completion?.content === "string" &&
        completion.content.trim().startsWith("{") &&
        completion.content.trim().endsWith("}"),
      schemaViolations,
      structure,
      structurePassed: schemaViolations.length === 0 && structure?.passed === true,
      parsedSummary,
      rawOutput: completion?.content ?? null,
    });
  }

  const costs = cases.map((item) => item.usage?.cost).filter((value) => typeof value === "number");
  const result = {
    schema: "moss-final-summary-prompt-iteration.v1",
    measuredAt: new Date().toISOString(),
    iteration,
    prompt,
    configuration: {
      endpoint: config.endpoint,
      requestedModel: config.model,
      token: config.token ? "present-not-recorded" : "absent",
      callsPerRecording: 1,
      rollingSummaries: 0,
      repairCalls: 0,
    },
    corpus: {
      finalizedRecordings: FINAL_CASE_IDS,
      excludedInterimCases: EXCLUDED_INTERIM_CASE_IDS,
      unavailableFinal: ["5m-acquired-rolex"],
      sealedBlindHoldoutContentOpened: 0,
    },
    aggregate: {
      cases: cases.length,
      calls: cases.length,
      structurePassed: cases.filter((item) => item.structurePassed).length,
      strictJsonOnly: cases.filter((item) => item.strictJsonOnly).length,
      casesWithMetricAppendix: cases.filter(
        (item) => (item.parsedSummary?.data_references.length ?? 0) > 0,
      ).length,
      metricAppendixEntries: cases.reduce(
        (sum, item) => sum + (item.parsedSummary?.data_references.length ?? 0),
        0,
      ),
      metricAppendixAcceptanceCriterion: false,
      medianLatencyMs: [...cases].sort((a, b) => a.latencyMs - b.latencyMs)[Math.floor(cases.length / 2)].latencyMs,
      maxLatencyMs: Math.max(...cases.map((item) => item.latencyMs)),
      recordedCost: costs.length === cases.length ? costs.reduce((sum, value) => sum + value, 0) : null,
    },
    cases,
    semanticQuality: "requires review of unmodified outputs; no gold summaries exist",
  };
  await writeFile(RESULT_PATH, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  await writeFile(REVIEW_PATH, renderReview(result), "utf8");
  process.stdout.write(`${JSON.stringify({ iteration, aggregate: result.aggregate, result: RESULT_PATH, review: REVIEW_PATH }, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error}\n`);
  process.exitCode = 1;
});
