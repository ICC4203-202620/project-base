import assert from "node:assert/strict";
import test from "node:test";

import { ApiError } from "../src/api.js";
import {
  RESTAURANT_STATES,
  createRestaurantsController,
} from "../src/restaurants.js";

const fixtures = Object.freeze([
  {
    id: "20000000-0000-4000-8000-000000000001",
    name: "Cocina del Barrio",
    address: "Av. Italia 1280, Providencia",
    cuisine_styles: [{ slug: "chilena", name: "Chilena" }],
  },
]);

function unauthorized() {
  return new ApiError("Not authenticated", { kind: "http", status: 401 });
}

test("the controller stays idle until an authenticated flow requests data", () => {
  let calls = 0;
  const controller = createRestaurantsController({
    api: {
      restaurants: async () => {
        calls += 1;
        return fixtures;
      },
    },
  });

  assert.equal(controller.state.status, RESTAURANT_STATES.IDLE);
  assert.equal(calls, 0);
});

test("an authenticated load exposes the returned restaurants", async () => {
  const transitions = [];
  const controller = createRestaurantsController({
    api: { restaurants: async () => fixtures },
    onStateChange: (state) => transitions.push(state.status),
  });

  await controller.load();

  assert.equal(controller.state.status, RESTAURANT_STATES.READY);
  assert.deepEqual(controller.state.items, fixtures);
  assert.deepEqual(transitions, [
    RESTAURANT_STATES.IDLE,
    RESTAURANT_STATES.LOADING,
    RESTAURANT_STATES.READY,
  ]);
});

test("an empty collection has a state distinct from a network error", async () => {
  const empty = createRestaurantsController({
    api: { restaurants: async () => [] },
  });
  const unavailable = createRestaurantsController({
    api: {
      restaurants: async () => {
        throw new ApiError("fetch failed", { kind: "network" });
      },
    },
  });

  await empty.load();
  await unavailable.load();

  assert.equal(empty.state.status, RESTAURANT_STATES.EMPTY);
  assert.equal(unavailable.state.status, RESTAURANT_STATES.ERROR);
  assert.match(unavailable.state.message, /conectar/);
});

test("a 401 clears the collection and reports the lost session", async () => {
  let unauthorizedCalls = 0;
  const controller = createRestaurantsController({
    api: {
      restaurants: async () => {
        throw unauthorized();
      },
    },
    onUnauthorized: () => {
      unauthorizedCalls += 1;
    },
  });

  await controller.load();

  assert.equal(controller.state.status, RESTAURANT_STATES.IDLE);
  assert.equal(unauthorizedCalls, 1);
});

test("reset discards an in-flight result and aborts its request", async () => {
  let resolveRequest;
  let receivedSignal;
  const pending = new Promise((resolve) => {
    resolveRequest = resolve;
  });
  const controller = createRestaurantsController({
    api: {
      restaurants: async ({ signal }) => {
        receivedSignal = signal;
        return pending;
      },
    },
  });

  const loading = controller.load();
  controller.reset();
  resolveRequest(fixtures);
  await loading;

  assert.equal(receivedSignal.aborted, true);
  assert.equal(controller.state.status, RESTAURANT_STATES.IDLE);
});

test("a recoverable error can be retried", async () => {
  let calls = 0;
  const controller = createRestaurantsController({
    api: {
      restaurants: async () => {
        calls += 1;
        if (calls === 1) {
          throw new ApiError("unavailable", { kind: "http", status: 503 });
        }
        return fixtures;
      },
    },
  });

  await controller.load();
  assert.equal(controller.state.status, RESTAURANT_STATES.ERROR);

  await controller.load();
  assert.equal(controller.state.status, RESTAURANT_STATES.READY);
  assert.equal(calls, 2);
});
