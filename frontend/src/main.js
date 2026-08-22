import "./style.css";

import { createApiClient } from "./api.js";
import { AUTH_STATES, createAuthController } from "./auth.js";

const apiStatus = document.querySelector("#api-status");
const checkApiButton = document.querySelector("#check-api");
const authCard = document.querySelector("#auth-card");
const authStatus = document.querySelector("#auth-status");
const authPanels = {
  [AUTH_STATES.LOADING]: document.querySelector("#auth-loading"),
  [AUTH_STATES.ANONYMOUS]: document.querySelector("#auth-anonymous"),
  [AUTH_STATES.AUTHENTICATED]: document.querySelector("#auth-authenticated"),
  [AUTH_STATES.UNAVAILABLE]: document.querySelector("#auth-unavailable"),
};
const loginForm = document.querySelector("#login-form");
const loginButton = loginForm.querySelector('button[type="submit"]');
const passwordInput = document.querySelector("#password");
const logoutButton = document.querySelector("#logout");
const retrySessionButton = document.querySelector("#retry-session");
const sessionName = document.querySelector("#session-name");
const sessionHandle = document.querySelector("#session-handle");
const sessionEmail = document.querySelector("#session-email");
const sessionExpiration = document.querySelector("#session-expiration");
const currentOrigin = document.querySelector("#current-origin");

const api = createApiClient();

currentOrigin.textContent = window.location.origin;

function showStatus(element, message, kind = "neutral") {
  element.textContent = message;
  element.dataset.kind = kind;
}

function formatExpiration(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Fecha de caducación no disponible";
  }
  return `${new Intl.DateTimeFormat(undefined, {
    dateStyle: "long",
    timeStyle: "short",
  }).format(date)} (hora local)`;
}

function renderAuth(state) {
  authCard.dataset.state = state.status;
  authCard.setAttribute("aria-busy", String(state.status === AUTH_STATES.LOADING));
  for (const [name, panel] of Object.entries(authPanels)) {
    panel.hidden = name !== state.status;
  }

  showStatus(authStatus, state.message, state.kind);
  loginButton.disabled = state.status === AUTH_STATES.LOADING;
  logoutButton.disabled = state.status === AUTH_STATES.LOADING;
  retrySessionButton.disabled = state.status === AUTH_STATES.LOADING;

  if (state.status === AUTH_STATES.AUTHENTICATED) {
    sessionName.textContent = state.session.user.name;
    sessionHandle.textContent = state.session.user.handle;
    sessionEmail.textContent = state.session.user.email;
    sessionExpiration.dateTime = state.session.expires_at;
    sessionExpiration.textContent = formatExpiration(state.session.expires_at);
  }
}

const auth = createAuthController({ api, onStateChange: renderAuth });

async function checkApi() {
  checkApiButton.disabled = true;
  showStatus(apiStatus, "Consultando /healthz…");

  try {
    const payload = await api.health();
    showStatus(apiStatus, `API disponible: ${payload.status}`, "success");
  } catch (error) {
    showStatus(apiStatus, `No fue posible conectar: ${error.message}`, "error");
  } finally {
    checkApiButton.disabled = false;
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(loginForm);
  await auth.login(Object.fromEntries(formData.entries()));
  if (auth.state.status === AUTH_STATES.AUTHENTICATED) {
    passwordInput.value = "";
  } else if (auth.state.status === AUTH_STATES.ANONYMOUS) {
    passwordInput.focus();
  }
});

logoutButton.addEventListener("click", () => auth.logout());
retrySessionButton.addEventListener("click", () => auth.restoreSession());
checkApiButton.addEventListener("click", checkApi);

checkApi();
auth.restoreSession();
