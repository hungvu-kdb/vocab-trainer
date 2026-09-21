# Component Methods — Vocabulary Trainer v2

Method signatures with input/output types and high-level purpose. Detailed business rules and
algorithms are specified per unit in Functional Design (CONSTRUCTION phase).

Signatures use Python type-hint syntax. `async` marks coroutines.

---

## Domain Layer

### `domain.models`

```python
class PartOfSpeech(StrEnum):
    NOUN; VERB; ADJECTIVE; ADVERB; PHRASE

class LookupSource(StrEnum):
    FREE_DICTIONARY; MERRIAM_WEBSTER; GOOGLE_TRANSLATE; NONE

class DuplicateAction(StrEnum):
    KEEP_OLD; REPLACE; DELETE_BOTH

class CollectionSortMode(StrEnum):
    NEWEST_FIRST; OLDEST_FIRST; NAME_ASC

class CharacterKind(StrEnum):
    CAT; CROCODILE

class WidgetState(StrEnum):
    IDLE; ACTIVE

@dataclass(frozen=True)
class WordEntry:
    word: str
    part_of_speech: PartOfSpeech
    meaning: str | None
    example: str | None
    collection_name: str
    collected_on: date

    @property
    def natural_key(self) -> tuple[str, str]:
        """Normalized (word, collection) identity. Delegates to domain.natural_key."""

@dataclass(frozen=True)
class Collection:
    name: str
    created_on: date

@dataclass(frozen=True)
class CollectionSummary:
    name: str
    created_on: date
    word_count: int

@dataclass(frozen=True)
class DefinitionCandidate:
    """One candidate definition from one source, before priority selection."""
    part_of_speech: PartOfSpeech | None
    meaning: str
    example: str | None

@dataclass(frozen=True)
class LookupResult:
    meaning: str | None
    example: str | None
    source: LookupSource

    @property
    def is_empty(self) -> bool: ...

@dataclass
class PracticeWordState:
    entry: WordEntry
    consecutive_correct: int = 0

    @property
    def is_mastered_at(self, required: int) -> bool: ...

@dataclass(frozen=True)
class SessionSummary:
    score: int
    words_practiced: int
    total_penalties: int
    elapsed: timedelta
    finished_at: datetime

@dataclass(frozen=True)
class AttemptOutcome:
    was_correct: bool
    correct_spelling: str
    consecutive_correct: int
    required_correct: int
    became_mastered: bool
    score: int
    total_penalties: int

@dataclass
class AppPreferences:
    master_file_path: Path
    widget_visible: bool = True
    widget_position: tuple[int, int] | None = None
    character: CharacterKind = CharacterKind.CAT
    tts_voice_id: str | None = None
    merriam_webster_api_key: str | None = None
    start_with_windows: bool = False
```

### `domain.natural_key`

```python
def normalize_word(value: str) -> str
    """Case-fold and trim a word for identity comparison."""

def normalize_collection(value: str) -> str
    """Case-fold and trim a collection name for identity comparison."""

def natural_key(word: str, collection_name: str) -> tuple[str, str]
    """The single definition of word identity used everywhere (FR-8.9)."""

def names_conflict(candidate: str, existing: str) -> bool
    """Whether two collection names collide case-insensitively (FR-2.5, FR-7.8)."""
```

### `domain.lookup_priority`

```python
PRIORITY: tuple[LookupSource, ...]
    """FREE_DICTIONARY, MERRIAM_WEBSTER, GOOGLE_TRANSLATE — highest first (FR-3.3)."""

def select_definition(
    candidates: Sequence[DefinitionCandidate],
    preferred: PartOfSpeech,
) -> DefinitionCandidate | None
    """Prefer a part-of-speech match; fall back to the first candidate (FR-3.2)."""

def select_result(
    results: Mapping[LookupSource, LookupResult],
) -> LookupResult
    """Highest-priority non-empty result, or an empty NONE result (FR-3.3, FR-3.5)."""
```

### `domain.shuffle`

```python
def shuffled(pool: Sequence[T], rng: Random | None = None) -> list[T]
    """Random permutation of the pool; preserves membership exactly (FR-5.9)."""

def reinsert_avoiding_next(
    pool: list[T], item: T, rng: Random | None = None
) -> None
    """Reinsert at any index except 0 when len(pool) > 0; index 0 only when the
    pool is otherwise empty (FR-6.7)."""
```

### `domain.scoring`

```python
def answer_matches(submitted: str, target: str) -> bool
    """Case-insensitive, whitespace-trimmed comparison (FR-6.4)."""

def total_required_attempts(pool_size: int, required_correct: int) -> int
    """Denominator for the progress bar (FR-6.3)."""

def compute_score(correct_attempts: int, penalties: int) -> int
    """correct_attempts - penalties; may be negative (FR-6.10)."""
```

---

## Data Layer

### `data.master_file_repository.MasterFileRepository`

```python
def __init__(self, path: Path) -> None

# Lifecycle and integrity
def ensure_workbook(self) -> RepairReport
    """Create the workbook if absent with both sheets and a seeded General
    collection; validate and auto-repair headers. Returns what was changed
    (FR-8.1, FR-8.3, FR-8.4)."""

def start_watching(self, on_external_change: Callable[[], None]) -> None
    """Begin watching the file; invoke the callback once writes settle (FR-8.8)."""

def stop_watching(self) -> None

# Reads
def all_words(self) -> list[WordEntry]
def all_collections(self) -> list[Collection]
def collection_summaries(self) -> list[CollectionSummary]
def find_by_natural_key(self, word: str, collection_name: str) -> WordEntry | None
def word_count_for(self, collection_name: str) -> int

# Word mutations — each atomic and serialized
def insert_word(self, entry: WordEntry) -> None
def patch_word_enrichment(
    self, key: tuple[str, str], meaning: str | None, example: str | None
) -> bool
    """Patch Meaning/Example on an existing row. Returns False if the row is gone,
    so a late lookup never recreates a deleted row (FR-2.9, E2-S4 branch 6c)."""
def replace_word(self, entry: WordEntry) -> None
    """Overwrite Meaning/Example/Date, preserving Word and Collection (FR-4.4)."""
def delete_word(self, key: tuple[str, str]) -> None

# Collection mutations — each atomic and serialized
def insert_collection(self, collection: Collection) -> None
def rename_collection(self, old_name: str, new_name: str) -> None
    """Rename and cascade to every belonging word row, in one atomic write, so a
    partial failure cannot orphan rows (FR-7.9)."""
def delete_collection(self, name: str) -> int
    """Delete the collection and cascade to its word rows in one atomic write.
    Returns the number of word rows removed (FR-7.11)."""
def ensure_default_collection(self) -> None
    """Seed General when no collection exists (FR-8.1, E7-S8 branch 7b)."""
```

Raises `MasterFileLockedError` (distinguishable so callers can offer Retry — FR-8.6) and
`MasterFileUnreadableError` (not a repairable workbook — E8-S3 branch 1a).

### `data.preferences_store.PreferencesStore`

```python
def __init__(self, path: Path) -> None
def load(self) -> AppPreferences
    """Load preferences, applying documented defaults on first run."""
def save(self, preferences: AppPreferences) -> None
```

### `data.history_store.HistoryStore`

```python
def __init__(self, path: Path) -> None
def append(self, summary: SessionSummary) -> bool
    """Append a session record. Returns False on failure without raising, so the
    summary screen still displays (FR-6.16, E6-S6 branch 4a)."""
def all_sessions(self) -> list[SessionSummary]
```

---

## Integration Layer

### `integrations.lookup_client.LookupClient` (protocol)

```python
@property
def source(self) -> LookupSource: ...

def is_available(self) -> bool
    """False when a prerequisite is missing, e.g. no API key (FR-3.8)."""

async def fetch(self, word: str) -> list[DefinitionCandidate]
    """Candidate definitions, or an empty list on any failure. Never raises."""
```

Implemented by `FreeDictionaryClient`, `MerriamWebsterClient`, `TranslateClient`.

### `integrations.tts.TextToSpeechService`

```python
def available_voices(self) -> list[VoiceInfo]
def select_voice(self, voice_id: str | None) -> None
def speak(self, text: str) -> bool
    """Speak asynchronously. Returns False when no voice is available or speech
    fails, without raising (FR-6.5, E7-S4 branches)."""
```

### `integrations.audio.AudioFeedbackService`

```python
def play_correct(self) -> None
def play_incorrect(self) -> None
```

### `integrations.startup_registration`

```python
def is_registered() -> bool
def register() -> bool
def unregister() -> bool
    """Return False on failure so the Settings toggle can revert rather than
    showing on while doing nothing (FR-1.8, E1-S5 branch 4a)."""
```

---

## Service Layer

### `services.collect_service.CollectService`

```python
def __init__(
    self,
    repository: MasterFileRepository,
    lookup: LookupService,
    clock: Clock,
) -> None

def available_collections(self) -> list[str]
    """Names for the Collection dropdown, current as of the last load (FR-2.3)."""

def create_collection_inline(self, name: str) -> Collection
    """Validate emptiness and case-insensitive uniqueness, then create
    (FR-2.5). Raises ValidationError with a user-facing message."""

def begin_lookup(self, word: str, pos: PartOfSpeech) -> LookupHandle
    """Start all sources concurrently in the background; returns a handle the UI
    can observe without blocking (FR-3.1, NFR-PERF-01)."""

def check_duplicate(self, word: str, collection_name: str) -> WordEntry | None
    """Existing entry with the same natural key, or None (FR-4.1)."""

def save_word(
    self,
    word: str,
    pos: PartOfSpeech,
    collection_name: str,
    lookup: LookupHandle,
) -> SaveOutcome
    """Save immediately with whatever lookup data has arrived, then patch the
    same row when the lookup completes (FR-2.8, FR-2.9). Returns an outcome
    indicating saved, duplicate-detected, or locked."""

def resolve_duplicate(
    self,
    action: DuplicateAction,
    existing: WordEntry,
    incoming: WordEntry,
) -> None
    """Apply exactly one of: no change / row updated / row removed. The incoming
    word is never inserted as a separate row (FR-4.3, FR-4.4, FR-4.5, FR-4.8)."""
```

### `services.lookup_service.LookupService`

```python
def __init__(self, clients: Sequence[LookupClient], timeout: float) -> None

async def lookup(self, word: str, pos: PartOfSpeech) -> LookupResult
    """Query every available client concurrently under a bounded timeout, then
    select by priority (FR-3.1, FR-3.2, FR-3.3, FR-3.5, NFR-PERF-03)."""
```

### `services.practice_service.PracticeService`

```python
def __init__(
    self,
    repository: MasterFileRepository,
    history: HistoryStore,
    tts: TextToSpeechService,
    audio: AudioFeedbackService,
    clock: Clock,
) -> None

# Setup
def list_collections(
    self, search: str = "", sort: CollectionSortMode = NEWEST_FIRST
) -> list[CollectionSummary]
    """Filter by case-insensitive substring, then sort. The two are independent
    of each other and of which collections are checked (FR-5.3, FR-5.4)."""

def combined_word_count(self, names: Sequence[str]) -> int

def can_start(self, names: Sequence[str]) -> bool
    """False when the combined pool is empty (FR-5.8)."""

def start_session(
    self, names: Sequence[str], required_correct: int
) -> PracticeSession
    """Build and shuffle the pool. Raises EmptyPoolError if zero words
    (FR-5.9, FR-5.8)."""

# Drill
def current_word(self) -> PracticeWordState | None
def submit_attempt(self, answer: str) -> AttemptOutcome
    """Judge, update score and mastery, play audio and speak on success, then
    master or reinsert (FR-6.4 through FR-6.8, FR-6.10, FR-6.11)."""
def advance(self) -> PracticeWordState | None
    """Move to the next word after the user acknowledges a miss (FR-6.9)."""
def progress(self) -> tuple[int, int]
    """(attempts made, total required attempts) — denominator fixed at session
    start so the bar only advances (FR-6.3, E6-S5 branch 2a)."""

# Ending
def end_session(self) -> SessionSummary
    """Produce the summary and append it to history. Reached by mastery, by End
    session, or by window close (FR-6.12, FR-6.13, FR-6.14, FR-6.16)."""
def last_session_config(self) -> tuple[list[str], int] | None
    """Collections and threshold for Practice again (FR-6.15)."""
```

### `services.settings_service.SettingsService`

```python
def __init__(
    self,
    repository: MasterFileRepository,
    preferences: PreferencesStore,
    widget_state: WidgetStateService,
    tts: TextToSpeechService,
) -> None

# General
def preferences(self) -> AppPreferences
def change_master_file(self, path: Path) -> RepairReport
    """Validate or create the workbook at the new path, then switch to it.
    Raises MasterFileUnreadableError so the previous path can stay in effect
    (FR-7.3, FR-8.2, E7-S2 branch 4b)."""
def set_start_with_windows(self, enabled: bool) -> bool
    """Returns the achieved state so the toggle can revert on failure (FR-1.8)."""

# Widget
def set_widget_visible(self, visible: bool) -> None
def set_character(self, character: CharacterKind) -> bool
    """False when that character's assets are missing, leaving the previous one
    in place (FR-7.4, E7-S3 branch 4a)."""

# Audio
def available_voices(self) -> list[VoiceInfo]
def set_tts_voice(self, voice_id: str | None) -> None
def preview_voice(self) -> bool

# Integrations
def set_merriam_webster_key(self, key: str | None) -> None
    """Stored in preferences; never logged (FR-3.8, NFR-SEC-01)."""

# About
def about_info(self) -> AboutInfo

# Collections CRUD
def collections_with_counts(self) -> list[CollectionSummary]
def create_collection(self, name: str) -> Collection
def rename_collection(self, old_name: str, new_name: str) -> None
    """Permits recasing the same collection; rejects collision with a different
    one (FR-7.9, E7-S7 branches 4b/4c)."""
def word_count_for_deletion(self, name: str) -> int
    """The exact count shown in the confirmation dialog (FR-7.10)."""
def delete_collection(self, name: str) -> int
    """Cascade delete, re-seeding General if it was the last collection
    (FR-7.11, E7-S8 branch 7b)."""
```

### `services.widget_state_service.WidgetStateService`

```python
def __init__(self, preferences: PreferencesStore) -> None

@property
def state(self) -> WidgetState
@property
def position(self) -> tuple[int, int] | None
@property
def is_visible(self) -> bool
@property
def character(self) -> CharacterKind

def set_state(self, state: WidgetState) -> None
    """Idle vs active, driving which character image renders (FR-1.2)."""
def move_to(self, x: int, y: int) -> None
    """Persist a new position, clamped onto a visible display (FR-1.3, FR-1.4,
    E1-S1 branch 3a)."""
def set_visible(self, visible: bool) -> None
def set_character(self, character: CharacterKind) -> None

def subscribe(self, listener: Callable[[], None]) -> Unsubscribe
    """Observer channel keeping the widget view and Settings in sync (E1-S4)."""
```

### `services.app_context.AppContext`

```python
@classmethod
def build(cls) -> AppContext
    """Composition root: construct and wire every component once (FR-8.1)."""

collect: CollectService
practice: PracticeService
settings: SettingsService
widget_state: WidgetStateService

def on_data_reloaded(self, listener: Callable[[], None]) -> Unsubscribe
    """Fires after an external file change is absorbed, so open views refresh
    without discarding unsaved input (FR-8.8, E8-S5 branches)."""
def shutdown(self) -> None
```
