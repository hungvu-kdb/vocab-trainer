"""Everything that touches the world outside this process.

Lookup clients, text-to-speech, audio playback, and OS startup registration. Each
module here isolates one external dependency so a failure in it degrades to a
reduced feature rather than an error the user has to deal with.
"""
