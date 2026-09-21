/*
 * Practice window behaviour.
 *
 * This file captures input and renders state. It makes no judgements: whether an
 * answer is correct, when a word is mastered, how progress is computed, and which
 * words remain are all decided by Python and arrive as data. Keeping it that way is
 * what lets the drill rules stay identical no matter which UI drives them.
 */

const state = {
  selected: new Set(),
  requiredWrites: 3,
  search: "",
  sort: "newest_first",
  awaitingNext: false,
};

/* Preview state. `previewCollection` doubles as the "is the modal open" flag, so a
 * bridge reply arriving after it closes is discarded rather than rendered. */
let previewCollection = null;
let previewTimer = null;

const PREVIEW_POLL_MS = 1000;
/* One second, and only while a row is actually pending. */

/* ------------------------------------------------------------------ */
/* Screens                                                            */
/* ------------------------------------------------------------------ */

function showScreen(name) {
  show(el("screen-setup"), name === "setup");
  show(el("screen-drill"), name === "drill");
  show(el("screen-summary"), name === "summary");
}

/* ------------------------------------------------------------------ */
/* Setup                                                              */
/* ------------------------------------------------------------------ */

async function loadCollections() {
  const response = await Bridge.call("list_collections", state.search, state.sort);
  if (!response.ok) {
    banner("setup-banner", response.error);
    return;
  }
  banner("setup-banner", "");
  renderCollections(response.collections);
  await refreshPool();
}

function renderCollections(collections) {
  const list = el("collection-list");
  list.innerHTML = "";

  show(el("no-results"), collections.length === 0);

  collections.forEach((collection) => {
    const checked = state.selected.has(collection.name);
    const row = document.createElement("div");
    row.className = `collection-item${checked ? " selected" : ""}`;
    row.innerHTML = `
      <label>
        <input type="checkbox" ${checked ? "checked" : ""} />
        <span>${escapeHtml(collection.name)}</span>
      </label>
      <span class="count">${collection.wordCount} words &middot; created ${escapeHtml(collection.createdOn)}</span>
      <button type="button" class="preview-button" title="Preview words">&#128065;</button>
    `;

    /* The button sits outside the <label>, but stop propagation anyway: a click
     * that bubbled to the row must not toggle the checkbox as a side effect of
     * asking to look at the collection. */
    row.querySelector(".preview-button").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openPreview(collection.name);
    });

    const box = row.querySelector("input");
    box.addEventListener("change", () => {
      /* Selection is tracked here and passed back to Python by name, which is why a
       * collection filtered out of view stays selected. */
      if (box.checked) {
        state.selected.add(collection.name);
      } else {
        state.selected.delete(collection.name);
      }
      row.classList.toggle("selected", box.checked);
      refreshPool();
    });

    list.appendChild(row);
  });
}

async function refreshPool() {
  const names = Array.from(state.selected);
  const response = await Bridge.call("pool_summary", names);
  if (!response.ok) return;

  const wordLabel = response.wordCount === 1 ? "word" : "words";
  const collLabel = response.collectionCount === 1 ? "collection" : "collections";
  el("pool-line").innerHTML =
    `Pool size: <b>${response.wordCount} ${wordLabel}</b> from ${response.collectionCount} ${collLabel}`;

  el("start-button").disabled = !response.canStart;
  show(el("blocked-note"), !response.canStart && names.length > 0);
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
  /* The modal may have closed while this was in flight. */
  if (previewCollection === null) return;

  if (!response.ok) {
    banner("preview-banner", response.error);
    renderPreviewTable([]);
    stopPreviewPolling();
    return;
  }

  renderPreviewTable(response.words);

  /* Poll only while a lookup is genuinely outstanding. */
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
  show(el("preview-table"), hasWords);

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

/* Blank-and-waiting is shown differently from blank-and-finished; the workbook
 * itself cannot tell them apart, since both are an empty cell. Matches the Settings
 * preview so the two tables cannot disagree. */
function previewCell(value, pending) {
  if (value) return escapeHtml(value);
  if (pending) {
    return '<span class="preview-pending"><span class="spinner"></span>Looking up\u2026</span>';
  }
  return '<span class="preview-blank">\u2014</span>';
}

function closePreview() {
  show(el("preview-backdrop"), false);
  previewCollection = null;
  stopPreviewPolling();
}

async function adjustWrites(delta) {
  const response = await Bridge.call("clamp_required_writes", state.requiredWrites + delta);
  if (!response.ok) return;
  state.requiredWrites = response.value;
  setText("writes-value", String(state.requiredWrites));

  /* Disable at the bounds rather than letting a press do nothing silently. */
  const atMin = (await Bridge.call("clamp_required_writes", state.requiredWrites - 1)).value === state.requiredWrites;
  const atMax = (await Bridge.call("clamp_required_writes", state.requiredWrites + 1)).value === state.requiredWrites;
  el("writes-down").disabled = atMin;
  el("writes-up").disabled = atMax;
}

async function startSession() {
  const response = await Bridge.call(
    "start_session",
    Array.from(state.selected),
    state.requiredWrites
  );
  if (!response.ok) {
    banner("setup-banner", response.error);
    return;
  }
  showScreen("drill");
  renderPrompt(response);
  el("answer-input").focus();
}

/* ------------------------------------------------------------------ */
/* Drill                                                              */
/* ------------------------------------------------------------------ */

function renderPrompt(data) {
  state.awaitingNext = false;

  if (!data.hasWord) {
    finishSession();
    return;
  }

  el("drill-type").textContent = data.partOfSpeech;

  const meaning = el("drill-meaning");
  meaning.textContent = data.meaning;
  /* A word saved while every lookup failed has no meaning; say so rather than
   * presenting an empty prompt. */
  meaning.classList.toggle("missing", !data.hasMeaning);

  show(el("drill-feedback"), false);
  show(el("next-button"), false);
  el("drill-hint").textContent = "Type the word";

  const input = el("answer-input");
  input.value = "";
  input.className = "answer-input";
  input.readOnly = false;
  input.focus();

  renderMeters(data);
  renderMastery(data.correctCount, data.wrongCount, data.requiredCorrect, null);
}

function renderMeters(data) {
  setText("drill-score", (data.score >= 0 ? "+" : "") + data.score);
  setText("drill-penalties", String(data.totalPenalties));
  setText(
    "drill-counter",
    `Attempt ${data.attemptsMade} of ${data.totalRequiredAttempts}`
  );

  /* Misses add attempts without adding progress, so the ratio can exceed 1 -- clamp
   * the bar rather than letting it overflow its track. */
  const ratio = data.totalRequiredAttempts
    ? Math.min(1, data.attemptsMade / data.totalRequiredAttempts)
    : 0;
  el("drill-progress").style.width = `${(ratio * 100).toFixed(1)}%`;
}

function renderMastery(correctCount, wrongCount, required, note) {
  /* Under the NOR rule the target itself moves: a miss adds one repetition on top
   * of whatever was originally required, so the dot row is sized to the *current*
   * target (required + wrongCount), not the session's original required count.
   * Filled dots are correctCount, exactly as before. */
  const target = required + wrongCount;
  const row = el("mastery-row");
  row.innerHTML = "";
  for (let index = 0; index < target; index += 1) {
    const dot = document.createElement("span");
    dot.className = `mastery-dot${index < correctCount ? " filled" : ""}`;
    row.appendChild(dot);
  }
  setText("mastery-note", note || "");
}

async function submitAnswer() {
  if (state.awaitingNext) {
    advance();
    return;
  }

  const input = el("answer-input");
  const response = await Bridge.call("submit_attempt", input.value);
  if (!response.ok) {
    banner("setup-banner", response.error);
    return;
  }
  if (response.ignored) return;

  renderMeters(response);

  const feedback = el("drill-feedback");
  if (response.wasCorrect) {
    input.className = "answer-input correct";
    feedback.className = "feedback correct";
    feedback.innerHTML = `&#128266; &#10003; Correct &mdash; &ldquo;${escapeHtml(response.correctSpelling)}&rdquo;`;
    show(feedback, true);

    renderMastery(
      response.correctCount,
      response.wrongCount,
      response.requiredCorrect,
      response.becameMastered
        ? "Mastered for this session"
        : `${response.remainingRepetitions} more correct ${response.remainingRepetitions === 1 ? "write" : "writes"} needed \u2014 back in the pool`
    );

    if (response.isFinished) {
      window.setTimeout(finishSession, 900);
      return;
    }
    /* A correct answer moves on by itself; only a miss waits for the user. */
    window.setTimeout(advance, 900);
  } else {
    input.className = "answer-input wrong";
    feedback.className = "feedback wrong";
    feedback.innerHTML = `&#10007; Not quite &mdash; correct spelling: <b>${escapeHtml(response.correctSpelling)}</b>`;
    show(feedback, true);

    renderMastery(
      response.correctCount,
      response.wrongCount,
      response.requiredCorrect,
      `${response.remainingRepetitions} more correct ${response.remainingRepetitions === 1 ? "write" : "writes"} needed \u2014 try again, still in the pool`
    );

    /* Wait for an explicit Next so the revealed spelling can actually be read. */
    state.awaitingNext = true;
    input.readOnly = true;
    el("drill-hint").textContent = "Read the spelling, then continue";
    show(el("next-button"), true);
    el("next-button").focus();
  }
}

async function advance() {
  const response = state.awaitingNext
    ? await Bridge.call("acknowledge_and_advance")
    : await Bridge.call("current_prompt");
  if (!response.ok) return;
  renderPrompt(response);
}

/* ------------------------------------------------------------------ */
/* Summary                                                            */
/* ------------------------------------------------------------------ */

async function finishSession() {
  const response = await Bridge.call("end_session");
  if (!response.ok) {
    banner("summary-banner", response.error);
    showScreen("summary");
    return;
  }

  setText("summary-score", (response.score >= 0 ? "+" : "") + response.score);
  const wordLabel = response.wordsPracticed === 1 ? "word" : "words";
  setText(
    "summary-label",
    `Final score \u00b7 ${response.wordsPracticed} ${wordLabel} mastered`
  );
  setText("summary-words", String(response.wordsPracticed));
  setText("summary-penalties", String(response.totalPenalties));
  setText("summary-elapsed", response.elapsed);
  banner("summary-banner", "");
  showScreen("summary");
}

async function practiceAgain() {
  const response = await Bridge.call("practice_again");
  if (!response.ok) {
    /* The collections may have been deleted in Settings since. */
    banner("summary-banner", response.error);
    return;
  }
  showScreen("drill");
  renderPrompt(response);
}

async function backToSetup() {
  const config = await Bridge.call("last_config");
  if (config.ok) {
    state.selected = new Set(config.collections);
    state.requiredWrites = config.requiredCorrect;
    setText("writes-value", String(state.requiredWrites));
  }
  showScreen("setup");
  await loadCollections();
}

/* ------------------------------------------------------------------ */
/* Wiring                                                            */
/* ------------------------------------------------------------------ */

function wire() {
  el("collection-search").addEventListener("input", (event) => {
    state.search = event.target.value;
    loadCollections();
  });

  el("collection-sort").addEventListener("change", (event) => {
    state.sort = event.target.value;
    loadCollections();
  });

  el("writes-down").addEventListener("click", () => adjustWrites(-1));
  el("writes-up").addEventListener("click", () => adjustWrites(1));
  el("start-button").addEventListener("click", startSession);
  el("preview-close").addEventListener("click", closePreview);

  el("answer-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitAnswer();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (
      event.key === "Escape" &&
      !el("preview-backdrop").classList.contains("hidden")
    ) {
      closePreview();
    }
  });
  el("next-button").addEventListener("click", advance);
  el("end-button").addEventListener("click", finishSession);

  el("practice-again").addEventListener("click", practiceAgain);
  el("back-to-setup").addEventListener("click", backToSetup);

  /* Sort resets to Newest first every time the window opens (FR-5.5); the select's
   * default markup already reflects that, so nothing further is needed here. */
  loadCollections();
  adjustWrites(0);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wire);
} else {
  wire();
}
