"""Pure domain logic.

No file I/O, no network, no UI framework imports. Every module here is
deterministic given its inputs, with randomness injected rather than sourced
internally.

This layer holds the rules that must not vary between the application's two UI
surfaces -- word identity, lookup priority, pool ordering, and scoring.
"""
