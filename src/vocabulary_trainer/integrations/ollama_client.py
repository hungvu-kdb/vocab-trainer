"""Local-LLM meaning generation through Ollama (FR-3.10).

Highest priority *when enabled*, which it never is by default. Ollama is not
bundled or installed by this app -- the user brings their own -- so every path
here treats "not installed" and "not running" as ordinary, silent outcomes rather
than errors. A machine without Ollama behaves exactly as it did before the feature
existed.

Talks to Ollama's HTTP API on ``127.0.0.1:11434``:

* ``GET  /api/tags``     -- installed models, used to populate the Settings list
  and to decide availability.
* ``POST /api/generate`` -- the completion itself, with ``stream: false`` so one
  response arrives as one JSON object.

Two design points worth stating, because both are easy to get wrong:

**The definition is asked for as JSON, not prose.** A free-form answer would need
parsing out of whatever preamble the model felt like adding ("Sure! Here's a
definition..."), which differs per model and per run. Requesting a fixed shape and
handing Ollama ``format: "json"`` makes the response machine-readable by
construction. The parser still tolerates a model that ignores the instruction and
wraps its JSON in prose or a markdown fence, because smaller models sometimes do.

**The part of speech the user picked is passed in as a constraint, not a filter.**
Unlike a dictionary, which returns many senses to choose between, the model is
asked directly for the sense matching that part of speech. So this client returns
at most one candidate, and ``select_definition`` has nothing to choose from -- by
design, since asking for one right answer beats generating five and guessing.

The generation timeout is deliberately longer than the web clients': a local model
on CPU can take several seconds to produce its first token, and the lookup is
already off the UI thread and non-blocking for saving (FR-2.8).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    LookupSource,
    PartOfSpeech,
)

__all__ = ["DEFAULT_HOST", "OllamaClient"]

DEFAULT_HOST = "http://127.0.0.1:11434"
"""Ollama's default loopback address.

Loopback only, and not configurable from the UI: pointing this at a remote host
would send every word the user collects to a third party, which is a materially
different privacy proposition than a local model.
"""

_TAGS_TIMEOUT = 2.0
"""Short: this runs when the Settings tab opens and when availability is checked.

Ollama answers in milliseconds when running. When it is *not* running the
connection is refused immediately, so this ceiling only matters for the odd case of
something listening on the port but not responding -- where waiting longer would
stall the UI for no gain.
"""

_GENERATE_TIMEOUT = 60.0
"""Generous, because a cold local model on CPU can genuinely take this long.

Matches ``LookupService._GENERATIVE_TIMEOUT`` deliberately. A shorter value here
would be the real ceiling regardless of what the service allows, so the two have to
agree or the wider one is a fiction -- this was 45s while the service allowed 60s,
which would have cut generation short at 45.

Safe because lookup never blocks saving: the row is written immediately and patched
when the result lands (FR-2.9).
"""

_PROMPT = """You are a concise English dictionary. Define the {pos} "{word}".

Reply with only a JSON object, no other text:
{{"meaning": "<one clear sentence, plain English, no more than 25 words>", \
"example": "<one natural sentence using it, or null>"}}

Rules:
- Define it as a {pos}. If it is not normally used as a {pos}, set meaning to null.
- Do not repeat the word itself in the meaning.
- Write for an intermediate English learner."""

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
"""Markdown fence some models wrap JSON in despite being told not to."""

_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
"""Fallback: the outermost brace pair, for a model that adds prose around it."""


class OllamaClient:
    """Generates an English definition using a locally running Ollama model."""

    def __init__(
        self,
        enabled: bool = False,
        model: str | None = None,
        host: str = DEFAULT_HOST,
        timeout: float = _GENERATE_TIMEOUT,
    ) -> None:
        self._enabled = bool(enabled)
        self._model = (model or "").strip() or None
        self._host = host.rstrip("/")
        self._timeout = timeout

    @property
    def source(self) -> LookupSource:
        return LookupSource.OLLAMA

    # ------------------------------------------------------------------
    # Configuration, pushed in by SettingsService on change
    # ------------------------------------------------------------------

    def configure(self, *, enabled: bool, model: str | None) -> None:
        """Apply a Settings change at runtime, without a restart."""
        self._enabled = bool(enabled)
        self._model = (model or "").strip() or None

    @property
    def model(self) -> str | None:
        return self._model

    def is_available(self) -> bool:
        """False unless switched on *and* given a model (FR-3.10).

        Deliberately does not probe the network. ``is_available`` is called on every
        lookup to decide which clients to run, and a synchronous connection attempt
        there would add latency to a hot path -- and could not be awaited anyway.
        A configured-but-absent Ollama simply fails its fetch and is treated as not
        having answered, which ``select_result`` already handles.
        """
        return self._enabled and self._model is not None

    # ------------------------------------------------------------------
    # Model discovery, for the Settings dropdown
    # ------------------------------------------------------------------

    async def list_models(self) -> list[str]:
        """Installed model names, or an empty list if Ollama is not reachable.

        Empty is a legitimate answer, not an error: Ollama may not be installed, may
        not be running, or may be running with no models pulled. The Settings tab
        distinguishes those cases in its wording rather than showing a failure.
        """
        payload = await self._get("/api/tags", timeout=_TAGS_TIMEOUT)
        if not isinstance(payload, dict):
            return []

        models = payload.get("models")
        if not isinstance(models, list):
            return []

        names: list[str] = []
        for entry in models:
            if isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
        # Sorted so the dropdown order does not shift between openings -- Ollama
        # returns them by modification time, which changes as models are used.
        return sorted(set(names))

    async def is_running(self) -> bool:
        """Whether an Ollama server answered, regardless of app settings.

        Used by Settings to explain *why* the model list is empty. Kept separate
        from ``is_available``, which reports configuration rather than reachability.
        """
        return await self._get("/api/tags", timeout=_TAGS_TIMEOUT) is not None

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        """Not used: this client needs the part of speech, so see ``generate``.

        Present because :class:`LookupClient` requires it. Returning empty rather
        than raising keeps the protocol's "never raises" guarantee intact if some
        future caller reaches for it generically.
        """
        return []

    async def generate(
        self, word: str, part_of_speech: PartOfSpeech
    ) -> list[DefinitionCandidate]:
        """Ask the model for one definition matching ``part_of_speech``."""
        if not self.is_available() or not word.strip():
            return []

        prompt = _PROMPT.format(pos=part_of_speech.value, word=word.strip())
        payload = await self._post(
            "/api/generate",
            {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                # Ask Ollama itself to constrain the output to JSON. Supported models
                # then cannot emit a prose preamble at all; the parser below still
                # copes with those that ignore it.
                "format": "json",
                "options": {
                    # Low temperature: a definition should be the model's most
                    # confident reading, not a creative one.
                    "temperature": 0.2,
                    # Two sentences of JSON need nothing more, and a cap keeps a
                    # rambling model from burning the whole timeout.
                    "num_predict": 200,
                },
            },
            timeout=self._timeout,
        )

        if not isinstance(payload, dict):
            return []

        response = payload.get("response")
        if not isinstance(response, str):
            return []

        return self._parse(response, part_of_speech)

    @classmethod
    def _parse(
        cls, response: str, part_of_speech: PartOfSpeech
    ) -> list[DefinitionCandidate]:
        data = cls._extract_json(response)
        if data is None:
            return []

        meaning = cls._clean(data.get("meaning"))
        if not meaning:
            # The prompt asks for null when the word is not used as the chosen part
            # of speech. Honouring that is the point: a wrong-part-of-speech
            # definition ranked first would be worse than no LLM answer at all,
            # since a dictionary source will then supply the meaning instead.
            return []

        return [
            DefinitionCandidate(
                part_of_speech=part_of_speech,
                meaning=meaning,
                example=cls._clean(data.get("example")) or None,
            )
        ]

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Pull a JSON object out of a model response.

        Three attempts, cheapest first: the whole string, a markdown fence, then the
        outermost brace pair. Smaller models wrap or annotate their JSON even when
        told not to, and re-prompting would double the wait.
        """
        for candidate in (text, *(m.group(1) for m in [_FENCE.search(text)] if m)):
            try:
                parsed = json.loads(candidate)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed

        match = _OBJECT.search(text)
        if match is not None:
            try:
                parsed = json.loads(match.group(0))
            except (TypeError, ValueError):
                return None
            if isinstance(parsed, dict):
                return parsed

        return None

    @staticmethod
    def _clean(value: object) -> str:
        """Normalise a model-supplied string, treating JSON null and "null" as empty.

        Models routinely emit the *string* ``"null"`` when asked for a null, which
        would otherwise be stored as a definition reading "null".
        """
        if not isinstance(value, str):
            return ""
        text = " ".join(value.split()).strip()
        if text.casefold() in {"null", "none", "n/a", ""}:
            return ""
        return text

    # ------------------------------------------------------------------
    # Transport. Never raises, per the LookupClient contract.
    # ------------------------------------------------------------------

    async def _get(self, path: str, *, timeout: float) -> Any | None:
        try:
            import httpx
        except ImportError:  # pragma: no cover - dependency is declared
            return None

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{self._host}{path}")
                if response.status_code != 200:
                    return None
                return response.json()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Ollama not installed, not running, or the port refused the
            # connection. All ordinary, all silent.
            return None

    async def _post(self, path: str, body: dict[str, Any], *, timeout: float) -> Any | None:
        try:
            import httpx
        except ImportError:  # pragma: no cover - dependency is declared
            return None

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{self._host}{path}", json=body)
                if response.status_code != 200:
                    return None
                return response.json()
        except asyncio.CancelledError:
            raise
        except Exception:
            return None
