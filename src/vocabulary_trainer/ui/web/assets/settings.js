/*
 * Settings window behaviour.
 *
 * Renders state supplied by Python and sends user actions back. Two rules it follows
 * strictly:
 *
 *  - Toggles are set from the state Python *achieved*, never optimistically from what
 *    the user clicked. Registration can fail, and a switch showing "on" over a failed
 *    write would misrepresent the machine.
 *  - The delete confirmation quotes the word count Python reports, rather than a count
 *    computed here from a possibly stale list.
 */

const PANES = ["general", "collections", "widget", "audio", "about"];

let pendingDelete = null;

/* Preview state. `previewCollection` doubles as the "is the modal open" flag, so a
 * bridge reply that arrives after closing can be discarded rather than rendered
 * into a hidden table. */
let previewCollection = null;
let previewTimer = null;

const PREVIEW_POLL_MS = 1000;
/* One second: fast enough that a finished lookup appears promptly, slow enough that
 * re-reading the workbook costs nothing noticeable. Only runs while at least one row
 * is actually pending. */

/* ------------------------------------------------------------------ */
/* Navigation                                                         */
/* ------------------------------------------------------------------ */

function selectPane(name) {
  PANES.forEach((pane) => show(el(`pane-${pane}`), pane === name));
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.pane === name);
  });

  /* Reload on entry so a pane never shows data that changed while it was hidden. */
  if (name === "general") loadGeneral();
  if (name === "collections") loadCollections();
  if (name === "widget") loadWidget();
  if (name === "audio") loadAudio();
  if (name === "about") loadAbout();
}

/* ------------------------------------------------------------------ */
/* General                                                            */
/* ------------------------------------------------------------------ */

async function loadGeneral() {
  const response = await Bridge.call("general_state");
  if (!response.ok) {
    banner("general-banner", response.error);
    return;
  }
  el("master-path").value = response.masterFilePath;
  el("startup-toggle").checked = response.startWithWindows;
  el("mw-key").placeholder = response.hasMerriamWebsterKey
    ? "Key saved \u2014 paste a new one to replace"
    : "Paste key";

  await loadOllama();
}

/* ------------------------------------------------------------------ */
/* Local AI model (Ollama)                                            */
/* ------------------------------------------------------------------ */

async function loadOllama() {
  const response = await Bridge.call("ollama_state");
  if (!response.ok) {
    banner("ollama-banner", response.error);
    return;
  }

  const select = el("ollama-model");
  const toggle = el("ollama-toggle");
  select.innerHTML = "";

  response.models.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  });

  /* No models means nothing can be enabled, so say why rather than offering a
   * switch that silently does nothing. The two causes need different fixes. */
  const hasModels = response.models.length > 0;
  if (!hasModels) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = response.running
      ? "No models installed"
      : "Ollama not detected";
    select.appendChild(option);
  }

  select.disabled = !hasModels;
  toggle.disabled = !hasModels;

  el("ollama-desc").textContent = hasModels
    ? "Meanings are written by the model instead of looked up in a dictionary"
    : response.running
      ? "Ollama is running but has no models. Pull one, e.g. \u2018ollama pull llama3.2\u2019, then Refresh."
      : `No Ollama server at ${response.defaultHost}. Install it and run \u2018ollama serve\u2019, then Refresh.`;

  if (response.model && hasModels) select.value = response.model;
  toggle.checked = response.enabled;

  /* A model that was chosen and has since been removed from Ollama: lookups would
   * quietly stop using it, so the reason is stated rather than left to be guessed. */
  if (response.modelMissing) {
    banner(
      "ollama-banner",
      `The model \u2018${response.model}\u2019 is no longer installed in Ollama. Pick another one.`,
      "warning"
    );
  } else {
    banner("ollama-banner", "");
  }
}

async function saveOllama() {
  const response = await Bridge.call(
    "set_ollama",
    el("ollama-toggle").checked,
    el("ollama-model").value
  );

  /* Reflect the state Python achieved, not what was clicked. */
  el("ollama-toggle").checked = response.enabled;
  if (!response.ok) {
    banner("ollama-banner", response.error, "warning");
    return;
  }
  banner("ollama-banner", "");
}

async function browseMasterFile() {
  /* The native file dialog is opened by Python; the page only asks for it. */
  const chosen = await Bridge.call("pick_master_file");
  if (!chosen.ok) {
    if (chosen.error) banner("general-banner", chosen.error);
    return;
  }
  if (!chosen.path) return; /* user cancelled */

  const response = await Bridge.call("change_master_file", chosen.path);
  if (!response.ok) {
    banner("general-banner", response.error);
    return;
  }

  el("master-path").value = response.masterFilePath;
  if (response.repairs && response.repairs.length) {
    /* FR-8.4: say exactly what was changed, rather than a vague "repaired". */
    banner(
      "general-banner",
      `The workbook's layout was repaired: ${response.repairs.join("; ")}.`,
      "warning"
    );
  } else if (response.created) {
    banner("general-banner", "A new workbook was created at that location.", "success");
  } else {
    banner("general-banner", "Master file updated.", "success");
  }
}

async function toggleStartup(event) {
  const response = await Bridge.call("set_start_with_windows", event.target.checked);
  /* Reflect what was achieved, which may differ from what was requested. */
  el("startup-toggle").checked = response.startWithWindows;
  banner("general-banner", response.ok ? "" : response.error);
}

async function saveMerriamWebsterKey() {
  const field = el("mw-key");
  const response = await Bridge.call("set_merriam_webster_key", field.value);
  if (!response.ok) {
    banner("general-banner", response.error);
    return;
  }
  field.value = "";
  field.placeholder = response.hasKey
    ? "Key saved \u2014 paste a new one to replace"
    : "Paste key";
  banner(
    "general-banner",
    response.hasKey ? "Merriam-Webster key saved." : "Merriam-Webster key cleared.",
    "success"
  );
}

/* ------------------------------------------------------------------ */
/* Collections                                                        */
/* ------------------------------------------------------------------ */

async function loadCollections() {
  const response = await Bridge.call("list_collections");
  if (!response.ok) {
    banner("collections-banner", response.error);
    return;
  }
  renderCollections(response.collections);
}

function renderCollections(collections) {
  const list = el("collections-list");
  list.innerHTML = "";

  if (!collections.length) {
    list.innerHTML = '<div class="empty-note">No collections yet.</div>';
    return;
  }

  collections.forEach((collection) => {
    const row = document.createElement("div");
    row.className = "collection-manage-row";
    const wordLabel = collection.wordCount === 1 ? "word" : "words";
    row.innerHTML = `
      <div>
        <div>${escapeHtml(collection.name)}</div>
        <div class="meta">${collection.wordCount} ${wordLabel}</div>
      </div>
      <div class="actions">
        <button title="Preview words" data-action="preview">&#128065;</button>
        <button title="Rename" data-action="rename">&#9998;</button>
        <button title="Delete" data-action="delete">&#128465;</button>
      </div>
    `;

    row.querySelector('[data-action="preview"]').addEventListener("click", () =>
      openPreview(collection.name)
    );
    row.querySelector('[data-action="rename"]').addEventListener("click", () =>
      beginRename(row, collection.name)
    );
    row.querySelector('[data-action="delete"]').addEventListener("click", () =>
      askToDelete(collection.name)
    );

    list.appendChild(row);
  });
}

function beginRename(row, currentName) {
  row.innerHTML = `
    <input class="text-input rename-input" value="${escapeHtml(currentName)}" />
    <div class="actions">
      <button title="Save" data-action="save">&#10003;</button>
      <button title="Cancel" data-action="cancel">&#10007;</button>
    </div>
  `;

  const input = row.querySelector("input");
  input.focus();
  input.select();

  const commit = async () => {
    const response = await Bridge.call("rename_collection", currentName, input.value);
    if (!response.ok) {
      banner("collections-banner", response.error);
      return;
    }
    banner("collections-banner", "");
    await loadCollections();
  };

  row.querySelector('[data-action="save"]').addEventListener("click", commit);
  row.querySelector('[data-action="cancel"]').addEventListener("click", loadCollections);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") commit();
    if (event.key === "Escape") loadCollections();
  });
}

async function createCollection() {
  const list = el("collections-list");
  const row = document.createElement("div");
  row.className = "collection-manage-row";
  row.innerHTML = `
    <input class="text-input rename-input" placeholder="Collection name" />
    <div class="actions">
      <button title="Create" data-action="save">&#10003;</button>
      <button title="Cancel" data-action="cancel">&#10007;</button>
    </div>
  `;
  list.appendChild(row);

  const input = row.querySelector("input");
  input.focus();

  const commit = async () => {
    const response = await Bridge.call("create_collection", input.value);
    if (!response.ok) {
      banner("collections-banner", response.error);
      input.focus();
      return;
    }
    banner("collections-banner", "");
    await loadCollections();
  };

  row.querySelector('[data-action="save"]').addEventListener("click", commit);
  row.querySelector('[data-action="cancel"]').addEventListener("click", loadCollections);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") commit();
    if (event.key === "Escape") loadCollections();
  });
}

async function askToDelete(name) {
  /* Ask Python for the count rather than reusing the rendered one: the workbook may
   * have changed since this list was drawn, and the dialog has to state a real
   * number. */
  const preview = await Bridge.call("deletion_preview", name);
  if (!preview.ok) {
    banner("collections-banner", preview.error);
    return;
  }

  pendingDelete = name;
  const wordLabel = preview.wordCount === 1 ? "word" : "words";

  el("confirm-title").textContent = `Delete "${name}"?`;
  el("confirm-body").innerHTML =
    preview.wordCount === 0
      ? "This collection contains no words. This cannot be undone."
      : `This will permanently delete <b>${preview.wordCount} ${wordLabel}</b> in the master file that belong to this collection. This cannot be undone.`;
  el("confirm-delete").textContent =
    preview.wordCount === 0
      ? "Delete collection"
      : `Delete ${preview.wordCount} ${wordLabel}`;

  show(el("confirm-backdrop"), true);
}

function cancelDelete() {
  pendingDelete = null;
  show(el("confirm-backdrop"), false);
}

async function confirmDelete() {
  if (!pendingDelete) return;
  const name = pendingDelete;
  cancelDelete();

  const response = await Bridge.call("delete_collection", name);
  if (!response.ok) {
    banner("collections-banner", response.error);
    return;
  }
  const wordLabel = response.removed === 1 ? "word" : "words";
  banner(
    "collections-banner",
    `Deleted "${name}" and ${response.removed} ${wordLabel}.`,
    "success"
  );
  await loadCollections();
}

async function openPreview(name) {
  el("preview-title").textContent = name;
  banner("preview-banner", "");
  show(el("preview-backdrop"), true);
  previewCollection = name;
  await refreshPreview();
}

async function refreshPreview() {
  if (previewCollection === null) return;

  const response = await Bridge.call("collection_words", previewCollection);
  /* Guard against a reply arriving after the modal closed or moved on to another
   * collection -- the poll below makes that genuinely possible. */
  if (previewCollection === null) return;

  if (!response.ok) {
    banner("preview-banner", response.error);
    renderPreviewTable([]);
    stopPreviewPolling();
    return;
  }

  renderPreviewTable(response.words);

  /* Poll only while something is actually being looked up, and stop as soon as
   * nothing is. A permanent timer would keep the workbook being re-read for a
   * modal the user left open on a finished collection. */
  if (response.anyPending) {
    startPreviewPolling();
  } else {
    stopPreviewPolling();
  }
}

function startPreviewPolling() {
  if (previewTimer !== null) return;
  previewTimer = setInterval(refreshPreview, PREVIEW_POLL_MS);
}

function stopPreviewPolling() {
  if (previewTimer === null) return;
  clearInterval(previewTimer);
  previewTimer = null;
}

function renderPreviewTable(words) {
  const body = el("preview-table-body");
  body.innerHTML = "";

  const hasWords = words.length > 0;
  show(el("preview-empty"), !hasWords);
  el("preview-table-body").closest("table").classList.toggle("hidden", !hasWords);

  words.forEach((entry) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(entry.word)}</td>
      <td>${escapeHtml(entry.partOfSpeech)}</td>
      <td>${previewCell(entry.meaning, entry.lookupPending)}</td>
      <td>${previewCell(entry.example, entry.lookupPending)}</td>
      <td>${escapeHtml(entry.collectedOn)}</td>
    `;
    body.appendChild(row);
  });
}

/* Three distinct states, where there used to be two:
 *   - a value            -> show it
 *   - blank, looking up  -> "Looking up..." so the user knows to wait
 *   - blank, finished    -> the em dash, meaning nothing was found
 * The workbook cannot distinguish the last two: both are an empty cell. */
function previewCell(value, pending) {
  if (value) return escapeHtml(value);
  if (pending) {
    return '<span class="preview-pending"><span class="spinner"></span>Looking up\u2026</span>';
  }
  return '<span class="preview-blank">\u2014</span>';
}

function closePreview() {
  show(el("preview-backdrop"), false);
  /* Clearing the name first makes any in-flight reply a no-op, and stopping the
   * timer prevents a closed modal polling forever. */
  previewCollection = null;
  stopPreviewPolling();
}

/* ------------------------------------------------------------------ */
/* Widget                                                             */
/* ------------------------------------------------------------------ */

async function loadWidget() {
  const response = await Bridge.call("widget_state");
  if (!response.ok) {
    banner("widget-banner", response.error);
    return;
  }

  el("widget-toggle").checked = response.widgetVisible;

  const select = el("character-select");
  select.innerHTML = "";
  const labels = { cat: "Cat", crocodile: "Crocodile" };
  const available = new Set(response.availableCharacters);

  Object.keys(labels).forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    /* Mark unavailable artwork rather than hiding the option, so the absence is
     * explained instead of looking like the feature does not exist. */
    option.textContent = available.has(value)
      ? labels[value]
      : `${labels[value]} (artwork not installed)`;
    option.disabled = !available.has(value);
    select.appendChild(option);
  });

  select.value = response.character;

  /* Range and current value both come from Python, so the slider can never offer
   * a size the service would refuse. */
  const scale = el("widget-scale");
  scale.min = response.minScalePercent;
  scale.max = response.maxScalePercent;
  scale.value = response.widgetScalePercent;
  renderScaleValue(response.widgetScalePercent);
}

function renderScaleValue(percent) {
  el("widget-scale-value").textContent = `${percent}%`;
}

async function changeWidgetScale(event) {
  const percent = Number(event.target.value);
  /* Update the label first: the drag should feel immediate, and the bridge call
   * confirms or corrects it a moment later. */
  renderScaleValue(percent);

  const response = await Bridge.call("set_widget_scale_percent", percent);
  if (!response.ok) {
    banner("widget-banner", response.error);
    /* Snap back to the size actually in effect rather than leaving the slider
     * showing a value the widget is not using. */
    el("widget-scale").value = response.widgetScalePercent;
    renderScaleValue(response.widgetScalePercent);
    return;
  }
  banner("widget-banner", "");
}

async function resetWidgetScale() {
  el("widget-scale").value = 100;
  await changeWidgetScale({ target: { value: 100 } });
}

async function toggleWidget(event) {
  await Bridge.call("set_widget_visible", event.target.checked);
}

async function changeCharacter(event) {
  const response = await Bridge.call("set_character", event.target.value);
  if (!response.ok) {
    banner("widget-banner", response.error);
    await loadWidget(); /* revert the select to the character actually in use */
    return;
  }
  banner("widget-banner", "");
}

/* ------------------------------------------------------------------ */
/* Audio                                                             */
/* ------------------------------------------------------------------ */

async function loadAudio() {
  const response = await Bridge.call("audio_state");
  if (!response.ok) {
    banner("audio-banner", response.error);
    return;
  }

  const select = el("voice-select");
  select.innerHTML = "";

  if (!response.hasVoices) {
    /* A legitimate state, not a fault: practice still plays its success sound. */
    const option = document.createElement("option");
    option.textContent = "No voices installed";
    select.appendChild(option);
    select.disabled = true;
    el("voice-preview").disabled = true;
    banner(
      "audio-banner",
      "No speech voices are installed on this computer. Practice will play its success sound without speaking the word.",
      "warning"
    );
    return;
  }

  select.disabled = false;
  el("voice-preview").disabled = false;
  banner("audio-banner", "");

  response.voices.forEach((voice) => {
    const option = document.createElement("option");
    option.value = voice.id;
    option.textContent = voice.name;
    select.appendChild(option);
  });

  if (response.selectedVoiceId) select.value = response.selectedVoiceId;
}

async function changeVoice(event) {
  await Bridge.call("set_tts_voice", event.target.value);
}

async function previewVoice() {
  const response = await Bridge.call("preview_voice");
  banner("audio-banner", response.ok ? "" : response.error, "warning");
}

/* ------------------------------------------------------------------ */
/* About                                                             */
/* ------------------------------------------------------------------ */

async function loadAbout() {
  const response = await Bridge.call("about_info");
  if (!response.ok) return;
  setText("about-name", response.appName);
  setText("about-version", response.version);
  setText("about-path", response.masterFilePath);
}

/* ------------------------------------------------------------------ */
/* Wiring                                                            */
/* ------------------------------------------------------------------ */

function wire() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => selectPane(item.dataset.pane));
  });

  el("browse-button").addEventListener("click", browseMasterFile);
  el("startup-toggle").addEventListener("change", toggleStartup);
  el("mw-save").addEventListener("click", saveMerriamWebsterKey);

  el("ollama-toggle").addEventListener("change", saveOllama);
  el("ollama-model").addEventListener("change", saveOllama);
  /* Refresh rather than polling: models change when the user runs "ollama pull",
   * which the app has no way to observe. */
  el("ollama-refresh").addEventListener("click", loadOllama);

  el("new-collection").addEventListener("click", createCollection);
  el("confirm-cancel").addEventListener("click", cancelDelete);
  el("confirm-delete").addEventListener("click", confirmDelete);
  el("preview-close").addEventListener("click", closePreview);

  el("widget-toggle").addEventListener("change", toggleWidget);
  el("character-select").addEventListener("change", changeCharacter);
  /* "input" rather than "change": the widget resizes as the slider is dragged,
   * which is what makes picking a size by eye work. */
  el("widget-scale").addEventListener("input", changeWidgetScale);
  el("widget-scale-reset").addEventListener("click", resetWidgetScale);

  el("voice-select").addEventListener("change", changeVoice);
  el("voice-preview").addEventListener("click", previewVoice);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (pendingDelete) {
      cancelDelete();
    } else if (!el("preview-backdrop").classList.contains("hidden")) {
      closePreview();
    }
  });

  selectPane("general");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wire);
} else {
  wire();
}
