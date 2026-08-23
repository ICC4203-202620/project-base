export class ApiError extends Error {
  constructor(message, { kind, status = null, payload = null, cause = null }) {
    super(message, cause ? { cause } : undefined);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.payload = payload;
  }
}

export function errorDetail(payload, fallback) {
  const detail = payload?.detail ?? payload;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item?.msg === "string" ? item.msg : null))
      .filter(Boolean);
    if (messages.length) {
      return messages.join(". ");
    }
  }
  if (typeof detail?.message === "string" && detail.message.trim()) {
    return detail.message;
  }
  return fallback;
}

async function responsePayload(response) {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function createApiClient(fetchImplementation = globalThis.fetch) {
  if (typeof fetchImplementation !== "function") {
    throw new TypeError("A Fetch API implementation is required");
  }

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetchImplementation(path, {
        credentials: "include",
        ...options,
        headers: {
          Accept: "application/json",
          ...options.headers,
        },
      });
    } catch (cause) {
      throw new ApiError("No fue posible conectar con el backend.", {
        kind: "network",
        cause,
      });
    }

    const payload = await responsePayload(response);
    if (!response.ok) {
      throw new ApiError(errorDetail(payload, `HTTP ${response.status}`), {
        kind: "http",
        status: response.status,
        payload,
      });
    }
    return payload;
  }

  return Object.freeze({
    health: () => request("/healthz"),
    session: () => request("/api/v1/auth/session"),
    restaurants: ({ limit = 20, offset = 0, signal } = {}) =>
      request(`/api/v1/restaurants?limit=${limit}&offset=${offset}`, { signal }),
    login: (credentials) =>
      request("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      }),
    logout: () => request("/api/v1/auth/logout", { method: "POST" }),
  });
}
