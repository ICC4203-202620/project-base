import "./style.css";

import { createApiClient } from "./api.js";
import { AUTH_STATES, createAuthController } from "./auth.js";
import {
  RESTAURANT_STATES,
  createRestaurantsController,
} from "./restaurants.js";

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
const restaurantsCard = document.querySelector("#restaurants-card");
const restaurantsStatus = document.querySelector("#restaurants-status");
const restaurantsList = document.querySelector("#restaurants-list");
const retryRestaurantsButton = document.querySelector("#retry-restaurants");
const restaurantPanels = {
  [RESTAURANT_STATES.LOADING]: document.querySelector("#restaurants-loading"),
  [RESTAURANT_STATES.READY]: document.querySelector("#restaurants-ready"),
  [RESTAURANT_STATES.EMPTY]: document.querySelector("#restaurants-empty"),
  [RESTAURANT_STATES.ERROR]: document.querySelector("#restaurants-error"),
};
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

function createRestaurantItem(restaurant) {
  const item = document.createElement("li");
  item.className = "restaurant-item";

  const article = document.createElement("article");
  const name = document.createElement("h3");
  name.textContent = restaurant.name;
  const address = document.createElement("address");
  address.textContent = restaurant.address;
  const styles = document.createElement("ul");
  styles.className = "cuisine-list";
  styles.setAttribute("aria-label", "Estilos de comida");

  for (const cuisine of restaurant.cuisine_styles) {
    const style = document.createElement("li");
    style.textContent = cuisine.name;
    styles.append(style);
  }

  article.append(name, address, styles);
  item.append(article);
  return item;
}

function renderRestaurants(state) {
  restaurantsCard.dataset.state = state.status;
  restaurantsCard.setAttribute(
    "aria-busy",
    String(state.status === RESTAURANT_STATES.LOADING),
  );
  for (const [name, panel] of Object.entries(restaurantPanels)) {
    panel.hidden = name !== state.status;
  }

  showStatus(restaurantsStatus, state.message, state.kind);
  retryRestaurantsButton.disabled = state.status === RESTAURANT_STATES.LOADING;
  restaurantsList.replaceChildren();

  if (state.status === RESTAURANT_STATES.READY) {
    restaurantsList.append(...state.items.map(createRestaurantItem));
  }
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
    restaurantsCard.hidden = false;
    restaurants.load();
  } else {
    restaurantsCard.hidden = true;
    restaurants.reset();
  }
}

let auth;
const restaurants = createRestaurantsController({
  api,
  onStateChange: renderRestaurants,
  onUnauthorized: () => auth.invalidateSession(),
});
auth = createAuthController({ api, onStateChange: renderAuth });

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
retryRestaurantsButton.addEventListener("click", () => restaurants.load());
checkApiButton.addEventListener("click", checkApi);

checkApi();
auth.restoreSession();
