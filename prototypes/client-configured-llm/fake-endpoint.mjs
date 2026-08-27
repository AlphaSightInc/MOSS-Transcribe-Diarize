// PROTOTYPE — deterministic OpenAI-compatible endpoint; not production code.

import http from "node:http";

const validSummary = Object.freeze({
  summary: "A deterministic summary remains stable.",
  topics: [{ title: "Deterministic behavior", description: "The fake endpoint returns scripted state." }],
  details: [],
  data_references: [],
  speaker_background: [],
});

function corsHeaders(origin, request) {
  const requestedHeaders = request.headers["access-control-request-headers"];
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": requestedHeaders ?? "authorization, content-type, x-prototype-scenario",
    "Access-Control-Allow-Private-Network": "true",
    "Access-Control-Max-Age": "0",
    Vary: "Origin",
  };
}

export async function startFakeEndpoint({ allowedOrigin }) {
  const observations = [];
  const scenarioCounts = new Map();
  const server = http.createServer((request, response) => {
    const requestUrl = new URL(request.url, "http://127.0.0.1");
    const scenario =
      requestUrl.searchParams.get("scenario") ??
      request.headers["x-prototype-scenario"] ??
      "valid";
    const observation = {
      method: request.method,
      path: request.url,
      origin: request.headers.origin ?? null,
      scenario,
      accessControlRequestMethod: request.headers["access-control-request-method"] ?? null,
      accessControlRequestHeaders: request.headers["access-control-request-headers"] ?? null,
      accessControlRequestPrivateNetwork:
        request.headers["access-control-request-private-network"] ?? null,
      clientClosed: false,
    };
    observations.push(observation);
    response.on("close", () => {
      observation.clientClosed = !response.writableEnded;
    });

    const headers = corsHeaders(allowedOrigin, request);
    if (request.method === "OPTIONS") {
      response.writeHead(204, headers);
      response.end();
      return;
    }
    if (request.method !== "POST" || requestUrl.pathname !== "/v1/chat/completions") {
      response.writeHead(404, { ...headers, "Content-Type": "application/json" });
      response.end(JSON.stringify({ error: { message: "not_found" } }));
      return;
    }

    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      observation.requestBytes = Buffer.byteLength(body);
      const count = (scenarioCounts.get(scenario) ?? 0) + 1;
      scenarioCounts.set(scenario, count);

      const send = (status, payload) => {
        if (response.destroyed) return;
        response.writeHead(status, { ...headers, "Content-Type": "application/json" });
        response.end(JSON.stringify(payload));
      };
      if (scenario === "slow-body") {
        response.writeHead(200, { ...headers, "Content-Type": "application/json" });
        response.write('{"id":"slow-completion","choices":[');
        observation.partialBodySent = true;
        const timer = setTimeout(
          () => response.end(
            JSON.stringify([{ message: { content: JSON.stringify(validSummary) } }]) + "}",
          ),
          10_000,
        );
        response.on("close", () => clearTimeout(timer));
        return;
      }
      if (scenario === "slow") {
        const timer = setTimeout(
          () => send(200, completion(JSON.stringify(validSummary))),
          10_000,
        );
        response.on("close", () => clearTimeout(timer));
        return;
      }
      if (scenario === "repair" && count < 3) {
        send(200, completion(count === 1 ? "not json" : '{"summary":'));
        return;
      }
      if (scenario === "context" && count === 1) {
        send(400, {
          error: { code: "context_length_exceeded", message: "scripted context rejection" },
        });
        return;
      }
      send(200, completion(JSON.stringify(validSummary)));
    });
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  return {
    url: `http://127.0.0.1:${address.port}/v1`,
    observations,
    scenarioCounts,
    close: () =>
      new Promise((resolve) => {
        server.close(resolve);
        server.closeAllConnections();
      }),
  };
}

function completion(content) {
  return {
    id: "fake-completion",
    object: "chat.completion",
    choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
  };
}
