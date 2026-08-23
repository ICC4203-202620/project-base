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
    ["src/api.js", "src/auth.js", "src/restaurants.js", "src/main.js"].map((path) =>
      readFile(new URL(path, frontendRoot), "utf8"),
    ),
  );

  assert.match(html, /id="auth-status"[\s\S]*role="status"[\s\S]*aria-live="polite"/);
  assert.ok(source.every((contents) => !contents.includes("document.cookie")));
  assert.ok(source.every((contents) => !contents.includes("localStorage")));
  assert.ok(source.every((contents) => !contents.includes("sessionStorage")));
});

test("the protected restaurant index starts hidden and uses safe DOM rendering", async () => {
  const html = await readFile(new URL("index.html", frontendRoot), "utf8");
  const main = await readFile(new URL("src/main.js", frontendRoot), "utf8");
  const styles = await readFile(new URL("src/style.css", frontendRoot), "utf8");

  assert.match(html, /id="restaurants-card"[\s\S]*hidden/);
  assert.match(html, /<ul id="restaurants-list"/);
  assert.match(html, /id="restaurants-status"[\s\S]*aria-live="polite"/);
  assert.ok(!main.includes("innerHTML"));
  assert.match(main, /\.textContent = restaurant\.name/);
  assert.match(main, /\.textContent = restaurant\.address/);
  assert.match(main, /restaurantsList\.replaceChildren\(\)/);
  assert.match(
    main,
    /state\.status === AUTH_STATES\.AUTHENTICATED[\s\S]*restaurants\.load\(\)/,
  );
  assert.match(styles, /minmax\(min\(100%, 16rem\), 1fr\)/);
  assert.match(styles, /overflow-wrap: anywhere/);
});
