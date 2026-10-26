# TTL cache boundary bug

`ttl_cache.py` implements `TTLCache`, a tiny deterministic cache used as the
benchmark task fixture. Its test suite currently fails.

## Task

Make the expiry semantics match the documented contract at the top of
`ttl_cache.py`: an entry is alive only strictly before its deadline, so a read
at exactly the deadline is a miss and `ttl=0` expires immediately. Entries with
`ttl=None` never expire, a stored `None` stays distinguishable from a miss,
replacing a key installs a fresh deadline, and unknown keys return the caller's
default.

## Scope

* Change **only** `ttl_cache.py`.
* `test_ttl_cache.py` and this `README.md` are frozen acceptance inputs: do not
  edit, rename, skip or delete a test, and do not add a test that merely mirrors
  the implementation.
* No new files, dependencies, commits or pushes.

## Required check

```
python3 -m unittest discover -s . -t . -p 'test_*.py' -v
```

Run it from the repository root, capture the complete output in a file outside
the repository, and report the failing test identifiers with source paths.
Acceptance also requires an independent semantic review of the complete diff,
which ends with `VERDICT: PASS <sha256 of the complete diff>`.
