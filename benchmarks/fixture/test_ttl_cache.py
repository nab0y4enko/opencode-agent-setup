"""Deterministic acceptance tests for ``ttl_cache.TTLCache``.

The suite is fixed: it drives the cache through an explicit fake clock so no
test sleeps, waits on wall time or depends on ordering of the interpreter.
Do not edit or delete a test here; fix the implementation in ``ttl_cache.py``.
"""

import unittest

from ttl_cache import TTLCache


class FakeClock:
    """Manually advanced monotonic clock; every cache instance gets one."""

    def __init__(self, start=1000.0):
        self.now = float(start)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.now

    def advance(self, delta):
        self.now += float(delta)


class TTLCacheTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.cache = TTLCache(clock=self.clock)

    def test_hit_before_deadline(self):
        self.cache.set("alpha", "value-a", ttl=10)
        self.clock.advance(9.5)
        self.assertEqual(self.cache.get("alpha", "MISS"), "value-a")
        self.assertIn("alpha", self.cache)

    def test_miss_after_deadline(self):
        self.cache.set("alpha", "value-a", ttl=10)
        self.clock.advance(10.5)
        self.assertEqual(self.cache.get("alpha", "MISS"), "MISS")
        self.assertIsNone(self.cache.get("alpha"))
        self.assertNotIn("alpha", self.cache)

    def test_miss_exactly_at_deadline(self):
        self.cache.set("alpha", "value-a", ttl=10)
        self.clock.advance(10)
        self.assertEqual(self.cache.get("alpha", "MISS"), "MISS",
                         "deadline is exclusive: reaching it must be a miss")
        self.assertIsNone(self.cache.get("alpha"))

    def test_contains_is_false_exactly_at_deadline(self):
        self.cache.set("alpha", "value-a", ttl=4)
        self.clock.advance(4)
        self.assertNotIn("alpha", self.cache)

    def test_zero_ttl_expires_immediately(self):
        self.cache.set("alpha", "value-a", ttl=0)
        self.assertEqual(self.cache.get("alpha", "MISS"), "MISS",
                         "ttl=0 means the deadline is the current instant")
        self.assertNotIn("alpha", self.cache)
        self.assertEqual(self.cache.keys(), [])

    def test_entries_without_ttl_never_expire(self):
        self.cache.set("session", "keep", ttl=None)
        self.clock.advance(1e9)
        self.assertEqual(self.cache.get("session", "MISS"), "keep")
        self.assertIn("session", self.cache)
        self.assertEqual(self.cache.keys(), ["session"])

    def test_missing_key_returns_supplied_default(self):
        self.cache.set("alpha", "value-a", ttl=10)
        self.assertEqual(self.cache.get("absent", "fallback"), "fallback")
        self.assertIsNone(self.cache.get("absent"))
        self.assertNotIn("absent", self.cache)
        self.clock.advance(20)
        self.assertEqual(self.cache.get("alpha", "MISS"), "MISS")
        self.assertEqual(self.cache.get("absent", "fallback"), "fallback")

    def test_replacing_entry_installs_new_deadline(self):
        self.cache.set("alpha", "first", ttl=10)
        self.clock.advance(10)
        self.cache.set("alpha", "second", ttl=10)
        self.clock.advance(5)
        self.assertEqual(self.cache.get("alpha", "MISS"), "second")
        self.clock.advance(10.5)
        self.assertEqual(self.cache.get("alpha", "MISS"), "MISS")

    def test_none_value_is_distinguished_from_missing(self):
        self.cache.set("alpha", None, ttl=10)
        self.assertIn("alpha", self.cache)
        self.assertIsNone(self.cache.get("alpha", "fallback"))
        self.assertEqual(self.cache.keys(), ["alpha"])
        self.clock.advance(10.5)
        self.assertEqual(self.cache.get("alpha", "fallback"), "fallback")
        self.assertNotIn("alpha", self.cache)

    def test_delete_removes_only_the_target_key(self):
        self.cache.set("alpha", 1, ttl=10)
        self.cache.set("beta", 2, ttl=10)
        self.assertTrue(self.cache.delete("alpha"))
        self.assertFalse(self.cache.delete("alpha"))
        self.assertFalse(self.cache.delete("never-set"))
        self.assertEqual(self.cache.keys(), ["beta"])
        self.assertEqual(self.cache.get("beta", "MISS"), 2)
        self.assertEqual(self.cache.get("alpha", "MISS"), "MISS")

    def test_keys_lists_live_entries_in_insertion_order(self):
        self.cache.set("alpha", 1, ttl=5)
        self.cache.set("beta", 2, ttl=None)
        self.cache.set("gamma", 3, ttl=20)
        self.assertEqual(self.cache.keys(), ["alpha", "beta", "gamma"])
        self.clock.advance(5.5)
        self.assertEqual(self.cache.keys(), ["beta", "gamma"])

    def test_reads_do_not_advance_the_clock(self):
        self.cache.set("alpha", "value-a", ttl=10)
        before = self.clock.calls
        for _ in range(5):
            self.assertEqual(self.cache.get("alpha", "MISS"), "value-a")
        self.assertGreater(self.clock.calls, before)
        self.assertEqual(self.clock.now, 1000.0)
        self.clock.advance(10.5)
        self.assertEqual(self.cache.get("alpha", "MISS"), "MISS")


if __name__ == "__main__":
    unittest.main()
