import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const frontendRoot = new URL("../", import.meta.url);

test("initial markup shows loading and hides unresolved authentication states", async () => {
  const html = await readFile(new URL("index.html", frontendRoot), "utf8");

  assert.match(html, /id="auth-loading" class="auth-panel">/);
  assert.match(html, /id="auth-anonymous" class="auth-panel" hidden>/);
  assert.match(html, /id="auth-authenticated" class="auth-panel" hidden>/);
  assert.match(html, /id="auth-unavailable" class="auth-panel" hidden>/);
});

test("authentication changes are announced without exposing the session", async () => {
  const html = await readFile(new URL("index.html", frontendRoot), "utf8");
  const source = await Promise.all(
    ["src/api.js", "src/auth.js", "src/main.js"].map((path) =>
      readFile(new URL(path, frontendRoot), "utf8"),
    ),
  );

  assert.match(html, /id="auth-status"[\s\S]*role="status"[\s\S]*aria-live="polite"/);
  assert.ok(source.every((contents) => !contents.includes("document.cookie")));
  assert.ok(source.every((contents) => !contents.includes("localStorage")));
  assert.ok(source.every((contents) => !contents.includes("sessionStorage")));
});
