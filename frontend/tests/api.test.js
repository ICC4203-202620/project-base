import assert from "node:assert/strict";
import test from "node:test";

import { ApiError, createApiClient, errorDetail } from "../src/api.js";

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("the API client uses relative URLs and includes browser credentials", async () => {
  const calls = [];
  const responses = [
    jsonResponse({ status: "ok" }),
    jsonResponse({ user: { name: "Demo" }, expires_at: "2030-01-01T00:00:00Z" }),
    jsonResponse([]),
    new Response(null, { status: 204 }),
    new Response(null, { status: 204 }),
  ];
  const api = createApiClient(async (path, options) => {
    calls.push({ path, options });
    return responses.shift();
  });

  await api.health();
  await api.session();
  await api.restaurants();
  await api.login({ email: "demo@example.com", password: "secret" });
  await api.logout();

  assert.deepEqual(
    calls.map(({ path }) => path),
    [
      "/healthz",
      "/api/v1/auth/session",
      "/api/v1/restaurants?limit=20&offset=0",
      "/api/v1/auth/login",
      "/api/v1/auth/logout",
    ],
  );
  assert.ok(calls.every(({ options }) => options.credentials === "include"));
  assert.equal(calls[3].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[3].options.body), {
    email: "demo@example.com",
    password: "secret",
  });
  assert.equal(calls[4].options.method, "POST");
});

test("the restaurants request accepts pagination and cancellation", async () => {
  let received;
  const controller = new AbortController();
  const api = createApiClient(async (path, options) => {
    received = { path, options };
    return jsonResponse([]);
  });

  await api.restaurants({ limit: 5, offset: 10, signal: controller.signal });

  assert.equal(received.path, "/api/v1/restaurants?limit=5&offset=10");
  assert.equal(received.options.signal, controller.signal);
  assert.equal(received.options.credentials, "include");
});

test("HTTP errors retain status and use the backend detail", async () => {
  const api = createApiClient(async () =>
    jsonResponse({ detail: "Invalid credentials" }, 401),
  );

  await assert.rejects(api.login({}), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.kind, "http");
    assert.equal(error.status, 401);
    assert.equal(error.message, "Invalid credentials");
    return true;
  });
});

test("validation error arrays become a concise message", () => {
  assert.equal(
    errorDetail(
      {
        detail: [
          { loc: ["body", "email"], msg: "value is not a valid email address" },
          { loc: ["body", "password"], msg: "field required" },
        ],
      },
      "fallback",
    ),
    "value is not a valid email address. field required",
  );
  assert.equal(errorDetail(null, "HTTP 500"), "HTTP 500");
});

test("network failures are distinguishable from HTTP responses", async () => {
  const cause = new TypeError("fetch failed");
  const api = createApiClient(async () => {
    throw cause;
  });

  await assert.rejects(api.session(), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.kind, "network");
    assert.equal(error.status, null);
    assert.equal(error.cause, cause);
    return true;
  });
});
