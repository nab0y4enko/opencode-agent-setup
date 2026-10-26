"""Small deterministic TTL cache.

Contract (see README.md):

* ``set(key, value, ttl=None)`` stores ``value``; ``ttl=None`` never expires,
  otherwise the deadline is ``clock() + ttl`` measured at the moment of the
  ``set`` call.  Replacing a key installs a fresh deadline.
* ``get(key, default=None)`` returns the stored value while the entry is still
  alive and ``default`` once the deadline has been reached or passed.
* An entry whose deadline is exactly the current time is expired: reading it
  is a miss, so a zero TTL expires immediately.
* A stored ``None`` value is a real hit and stays distinguishable from a miss.
"""

import time

_MISSING = object()


class TTLCache:
    """Mapping-like cache whose expiry is decided by ``clock()``."""

    def __init__(self, clock=None):
        self._clock = time.monotonic if clock is None else clock
        self._entries = {}

    def _deadline(self, ttl):
        if ttl is None:
            return None
        ttl = float(ttl)
        if ttl < 0.0:
            raise ValueError("ttl must be non-negative or None")
        return self._clock() + ttl

    def set(self, key, value, ttl=None):
        """Store ``value`` for ``key``, replacing any previous entry."""
        self._entries[key] = (value, self._deadline(ttl))

    def _lookup(self, key):
        entry = self._entries.get(key, _MISSING)
        if entry is _MISSING:
            return _MISSING
        value, deadline = entry
        if deadline is not None and self._clock() > deadline:
            del self._entries[key]
            return _MISSING
        return value

    def get(self, key, default=None):
        """Return the cached value, or ``default`` when absent or expired."""
        found = self._lookup(key)
        return default if found is _MISSING else found

    def __contains__(self, key):
        return self._lookup(key) is not _MISSING

    def delete(self, key):
        """Remove ``key``; return True only when an entry was present."""
        return self._entries.pop(key, _MISSING) is not _MISSING

    def keys(self):
        """Live keys in insertion order; expired entries are dropped."""
        live = []
        for key in list(self._entries):
            if self._lookup(key) is _MISSING:
                continue
            live.append(key)
        return live

    def clear(self):
        self._entries.clear()
