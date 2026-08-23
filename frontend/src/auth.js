import { ApiError } from "./api.js";

export const AUTH_STATES = Object.freeze({
  LOADING: "loading",
  ANONYMOUS: "anonymous",
  AUTHENTICATED: "authenticated",
  UNAVAILABLE: "unavailable",
});

const MESSAGES = Object.freeze({
  checking: "Comprobando si existe una sesión vigente…",
  anonymous:
    "No hay una sesión activa. El navegador administrará la cookie HttpOnly al iniciar sesión.",
  authenticated: "La sesión fue verificada por el backend.",
  invalidCredentials: "El correo o la contraseña no son válidos.",
  loginAccepted: "Credenciales aceptadas. Verificando la sesión creada…",
  logout: "Cerrando la sesión en el backend…",
  loggedOut: "La sesión se cerró correctamente.",
  sessionLost: "La sesión caducó o fue revocada. Inicia sesión nuevamente.",
});

function unavailableMessage(error) {
  if (error instanceof ApiError && error.kind === "network") {
    return "No fue posible conectar con el backend. Revisa los servicios y vuelve a intentar.";
  }
  const status = error instanceof ApiError && error.status ? ` (HTTP ${error.status})` : "";
  return `El servicio de autenticación no está disponible${status}. Vuelve a intentar.`;
}

function isUnauthorized(error) {
  return error instanceof ApiError && error.status === 401;
}

export function createAuthController({ api, onStateChange = () => {} }) {
  let state;

  function transition(status, details) {
    state = Object.freeze({ status, ...details });
    onStateChange(state);
    return state;
  }

  function anonymous(message = MESSAGES.anonymous, kind = "neutral") {
    return transition(AUTH_STATES.ANONYMOUS, { message, kind });
  }

  async function restoreSession(message = MESSAGES.checking) {
    transition(AUTH_STATES.LOADING, { message, kind: "neutral" });
    try {
      const session = await api.session();
      return transition(AUTH_STATES.AUTHENTICATED, {
        session,
        message: MESSAGES.authenticated,
        kind: "success",
      });
    } catch (error) {
      if (isUnauthorized(error)) {
        return anonymous();
      }
      return transition(AUTH_STATES.UNAVAILABLE, {
        message: unavailableMessage(error),
        kind: "error",
      });
    }
  }

  async function login(credentials) {
    transition(AUTH_STATES.LOADING, {
      message: "Enviando las credenciales al backend…",
      kind: "neutral",
    });
    try {
      await api.login(credentials);
    } catch (error) {
      if (isUnauthorized(error)) {
        return anonymous(MESSAGES.invalidCredentials, "error");
      }
      return transition(AUTH_STATES.UNAVAILABLE, {
        message: unavailableMessage(error),
        kind: "error",
      });
    }
    return restoreSession(MESSAGES.loginAccepted);
  }

  async function logout() {
    transition(AUTH_STATES.LOADING, { message: MESSAGES.logout, kind: "neutral" });
    try {
      await api.logout();
      return anonymous(MESSAGES.loggedOut, "success");
    } catch (error) {
      if (isUnauthorized(error)) {
        return anonymous(MESSAGES.loggedOut, "success");
      }
      return transition(AUTH_STATES.UNAVAILABLE, {
        message: unavailableMessage(error),
        kind: "error",
      });
    }
  }

  function invalidateSession(message = MESSAGES.sessionLost) {
    return anonymous(message, "error");
  }

  transition(AUTH_STATES.LOADING, { message: MESSAGES.checking, kind: "neutral" });

  return Object.freeze({
    get state() {
      return state;
    },
    restoreSession,
    login,
    logout,
    invalidateSession,
  });
}
