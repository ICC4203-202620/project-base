import { ApiError } from "./api.js";

export const RESTAURANT_STATES = Object.freeze({
  IDLE: "idle",
  LOADING: "loading",
  READY: "ready",
  EMPTY: "empty",
  ERROR: "error",
});

const MESSAGES = Object.freeze({
  idle: "El índice se mostrará después de verificar la sesión.",
  loading: "Cargando la primera página de restaurantes…",
  empty: "El backend respondió correctamente, pero aún no hay restaurantes.",
});

function readyMessage(count) {
  return count === 1
    ? "Se cargó 1 restaurante desde el backend."
    : `Se cargaron ${count} restaurantes desde el backend.`;
}

function errorMessage(error) {
  if (error instanceof ApiError && error.kind === "network") {
    return "No fue posible conectar con el backend para cargar los restaurantes.";
  }
  const status = error instanceof ApiError && error.status ? ` (HTTP ${error.status})` : "";
  return `No fue posible cargar los restaurantes${status}. Vuelve a intentar.`;
}

function isUnauthorized(error) {
  return error instanceof ApiError && error.status === 401;
}

export function createRestaurantsController({
  api,
  onStateChange = () => {},
  onUnauthorized = () => {},
}) {
  let state;
  let requestVersion = 0;
  let activeRequest = null;

  function transition(status, details) {
    state = Object.freeze({ status, ...details });
    onStateChange(state);
    return state;
  }

  function reset() {
    requestVersion += 1;
    activeRequest?.abort();
    activeRequest = null;
    return transition(RESTAURANT_STATES.IDLE, {
      message: MESSAGES.idle,
      kind: "neutral",
    });
  }

  async function load() {
    requestVersion += 1;
    const version = requestVersion;
    activeRequest?.abort();
    const controller = new AbortController();
    activeRequest = controller;

    transition(RESTAURANT_STATES.LOADING, {
      message: MESSAGES.loading,
      kind: "neutral",
    });

    try {
      const items = await api.restaurants({ signal: controller.signal });
      if (version !== requestVersion) {
        return state;
      }
      activeRequest = null;
      if (items.length === 0) {
        return transition(RESTAURANT_STATES.EMPTY, {
          items: Object.freeze([]),
          message: MESSAGES.empty,
          kind: "neutral",
        });
      }
      return transition(RESTAURANT_STATES.READY, {
        items: Object.freeze([...items]),
        message: readyMessage(items.length),
        kind: "success",
      });
    } catch (error) {
      if (version !== requestVersion) {
        return state;
      }
      activeRequest = null;
      if (isUnauthorized(error)) {
        reset();
        onUnauthorized(error);
        return state;
      }
      return transition(RESTAURANT_STATES.ERROR, {
        message: errorMessage(error),
        kind: "error",
      });
    }
  }

  reset();

  return Object.freeze({
    get state() {
      return state;
    },
    load,
    reset,
  });
}
