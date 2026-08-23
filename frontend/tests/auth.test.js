import assert from "node:assert/strict";
import test from "node:test";

import { ApiError } from "../src/api.js";
import { AUTH_STATES, createAuthController } from "../src/auth.js";

const session = Object.freeze({
  user: {
    id: "00000000-0000-4000-8000-000000000001",
    email: "demo@example.com",
    handle: "@demo",
    name: "Demo Foodie",
  },
  expires_at: "2030-01-01T00:00:00Z",
});

function unauthorized() {
  return new ApiError("Not authenticated", { kind: "http", status: 401 });
}

test("restoring a valid session reaches authenticated state", async () => {
  const transitions = [];
  const controller = createAuthController({
    api: { session: async () => session },
    onStateChange: (state) => transitions.push(state.status),
  });

  await controller.restoreSession();

  assert.equal(controller.state.status, AUTH_STATES.AUTHENTICATED);
  assert.equal(controller.state.session, session);
  assert.deepEqual(transitions, [
    AUTH_STATES.LOADING,
    AUTH_STATES.LOADING,
    AUTH_STATES.AUTHENTICATED,
  ]);
});

test("a missing, expired or revoked session is anonymous", async () => {
  const controller = createAuthController({
    api: {
      session: async () => {
        throw unauthorized();
      },
    },
  });

  await controller.restoreSession();

  assert.equal(controller.state.status, AUTH_STATES.ANONYMOUS);
  assert.equal(controller.state.kind, "neutral");
});

test("login verifies the server session before authenticating the UI", async () => {
  const calls = [];
  const controller = createAuthController({
    api: {
      login: async (credentials) => calls.push(["login", credentials]),
      session: async () => {
        calls.push(["session"]);
        return session;
      },
    },
  });
  const credentials = { email: "demo@example.com", password: "demo-password" };

  await controller.login(credentials);

  assert.deepEqual(calls, [["login", credentials], ["session"]]);
  assert.equal(controller.state.status, AUTH_STATES.AUTHENTICATED);
});

test("a successful login response alone never authenticates the UI", async () => {
  const controller = createAuthController({
    api: {
      login: async () => {},
      session: async () => {
        throw unauthorized();
      },
    },
  });

  await controller.login({ email: "demo@example.com", password: "demo-password" });

  assert.equal(controller.state.status, AUTH_STATES.ANONYMOUS);
});

test("invalid credentials retain anonymous state and do not query session", async () => {
  let sessionCalls = 0;
  const controller = createAuthController({
    api: {
      login: async () => {
        throw unauthorized();
      },
      session: async () => {
        sessionCalls += 1;
      },
    },
  });

  await controller.login({ email: "demo@example.com", password: "wrong" });

  assert.equal(controller.state.status, AUTH_STATES.ANONYMOUS);
  assert.equal(controller.state.kind, "error");
  assert.match(controller.state.message, /contraseña/);
  assert.equal(sessionCalls, 0);
});

test("logout returns to anonymous even if a later reload finds no session", async () => {
  let loggedOut = false;
  const controller = createAuthController({
    api: {
      logout: async () => {
        loggedOut = true;
      },
      session: async () => {
        throw unauthorized();
      },
    },
  });

  await controller.logout();
  assert.equal(loggedOut, true);
  assert.equal(controller.state.status, AUTH_STATES.ANONYMOUS);

  await controller.restoreSession();
  assert.equal(controller.state.status, AUTH_STATES.ANONYMOUS);
});

test("logout treats a session that expired in the meantime as anonymous", async () => {
  const controller = createAuthController({
    api: {
      logout: async () => {
        throw unauthorized();
      },
    },
  });

  await controller.logout();

  assert.equal(controller.state.status, AUTH_STATES.ANONYMOUS);
  assert.equal(controller.state.kind, "success");
});

test("network and infrastructure failures use unavailable state", async () => {
  const networkController = createAuthController({
    api: {
      session: async () => {
        throw new ApiError("fetch failed", { kind: "network" });
      },
    },
  });
  await networkController.restoreSession();
  assert.equal(networkController.state.status, AUTH_STATES.UNAVAILABLE);
  assert.match(networkController.state.message, /conectar/);

  const serviceController = createAuthController({
    api: {
      session: async () => {
        throw new ApiError("unavailable", { kind: "http", status: 503 });
      },
    },
  });
  await serviceController.restoreSession();
  assert.equal(serviceController.state.status, AUTH_STATES.UNAVAILABLE);
  assert.match(serviceController.state.message, /HTTP 503/);
});

test("a protected resource can invalidate the current session", async () => {
  const controller = createAuthController({ api: {} });

  controller.invalidateSession();

  assert.equal(controller.state.status, AUTH_STATES.ANONYMOUS);
  assert.equal(controller.state.kind, "error");
  assert.match(controller.state.message, /caducó|revocada/);
});
