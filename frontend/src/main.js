import "./style.css";

const apiStatus = document.querySelector("#api-status");
const checkApiButton = document.querySelector("#check-api");
const loginForm = document.querySelector("#login-form");
const loginStatus = document.querySelector("#login-status");
const currentOrigin = document.querySelector("#current-origin");

currentOrigin.textContent = window.location.origin;

function showStatus(element, message, kind = "neutral") {
  element.textContent = message;
  element.dataset.kind = kind;
}

async function errorMessage(response) {
  try {
    const payload = await response.json();
    return payload.detail ?? JSON.stringify(payload);
  } catch {
    return `HTTP ${response.status}`;
  }
}

async function checkApi() {
  checkApiButton.disabled = true;
  showStatus(apiStatus, "Consultando /healthz…");

  try {
    const response = await fetch("/healthz", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }

    const payload = await response.json();
    showStatus(apiStatus, `API disponible: ${payload.status}`, "success");
  } catch (error) {
    showStatus(apiStatus, `No fue posible conectar: ${error.message}`, "error");
  } finally {
    checkApiButton.disabled = false;
  }
}

async function login(event) {
  event.preventDefault();
  const formData = new FormData(loginForm);
  const credentials = Object.fromEntries(formData.entries());

  showStatus(loginStatus, "Enviando credenciales…");

  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }

    showStatus(
      loginStatus,
      "Login correcto. El navegador guardó la cookie HttpOnly.",
      "success",
    );
  } catch (error) {
    showStatus(loginStatus, `El login falló: ${error.message}`, "error");
  }
}

checkApiButton.addEventListener("click", checkApi);
loginForm.addEventListener("submit", login);

checkApi();
