/*
 * Connects the page to the Python bridge over QWebChannel.
 *
 * Every call returns a promise resolving to the payload Python sent. The bridge
 * always answers with an { ok, ... } envelope and never lets an exception cross the
 * channel, so a rejected promise here means the channel itself failed rather than an
 * operation being refused -- a refusal arrives as ok: false with a message.
 */

const Bridge = (() => {
  let backend = null;
  let readyResolve;
  const ready = new Promise((resolve) => {
    readyResolve = resolve;
  });

  function connect() {
    if (typeof QWebChannel === "undefined") {
      // Opened outside the app (a plain browser, for inspection). The page still
      // renders; every call simply reports the backend as unavailable.
      console.warn("QWebChannel unavailable - running without a backend.");
      readyResolve(null);
      return;
    }
    new QWebChannel(qt.webChannelTransport, (channel) => {
      backend = channel.objects.backend;
      readyResolve(backend);
    });
  }

  /* Invoke a Python slot by name. */
  async function call(method, ...args) {
    const api = await ready;
    if (!api || typeof api[method] !== "function") {
      return { ok: false, error: "The application backend is not available." };
    }
    return new Promise((resolve) => {
      api[method](...args, (result) => resolve(result || { ok: false, error: "No response." }));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", connect);
  } else {
    connect();
  }

  return { call, ready };
})();

/* ------------------------------------------------------------------ */
/* Small DOM helpers, so the screen scripts stay about behaviour       */
/* ------------------------------------------------------------------ */

function el(id) {
  return document.getElementById(id);
}

function show(node, visible) {
  if (node) node.classList.toggle("hidden", !visible);
}

function setText(id, text) {
  const node = el(id);
  if (node) node.textContent = text;
}

/* Render a message banner, or clear it when message is falsy. */
function banner(id, message, kind) {
  const node = el(id);
  if (!node) return;
  if (!message) {
    node.textContent = "";
    node.className = "banner hidden";
    return;
  }
  node.textContent = message;
  node.className = `banner ${kind || "error"}`;
}

/* Escape text before inserting it into innerHTML.
 *
 * Collection names and word meanings come from a user-editable Excel file, so they
 * are untrusted input as far as this page is concerned. */
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
