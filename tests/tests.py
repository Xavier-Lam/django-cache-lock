import threading
import time

from django.core.cache import cache
from django.test import TestCase

from django_lock import DEFAULT_PREFIX, Lock, patch_lock


class LockTestCase(TestCase):
    lock_name = "lock"
    seconds = 0.5

    def setUp(self):
        patch_lock()
        self.lock = Lock(cache, self.lock_name)
        cache.delete(self.lock.key)

    def tearDown(self):
        self.lock.release()

    def test_acquire(self):
        started = time.time()

        def locker():
            self.assertTrue(self.lock.acquire(False))
            try:
                time.sleep(self.seconds)
            finally:
                self.lock.release()

        t = threading.Thread(target=locker)
        t.start()

        self.assertFalse(self.lock.acquire(False))
        self.assertFalse(self.lock.acquire(0.2))
        self.assertTrue(self.lock.acquire())
        self.assertGreaterEqual(time.time(), started + self.seconds)

    def test_name(self):
        self.assertEqual(self.lock.key, DEFAULT_PREFIX + self.lock_name)

        prefix = "prefix:"
        with self.settings(DJANGOLOCK_PREFIX=prefix):
            self.assertEqual(self.lock.key, prefix + self.lock_name)

    def test_token(self):
        self.assertTrue(self.lock.acquire(False))
        try:
            self.assertEqual(cache.get(self.lock.key), self.lock.local.token)
        finally:
            self.lock.release()

    def test_lock(self):
        self.assertTrue(self.lock.acquire(False))
        key = "another_lock"
        lock = Lock(cache, key)
        self.assertTrue(lock.acquire(False))
        lock.release()

    def test_context(self):
        started = time.time()

        def locker():
            with cache.lock(self.lock_name):
                time.sleep(self.seconds)

        t = threading.Thread(target=locker)
        t.start()

        self.assertFalse(self.lock.acquire(False))
        self.assertFalse(self.lock.acquire(0.2))
        self.assertTrue(self.lock.acquire())
        self.assertGreaterEqual(time.time(), started + self.seconds)

    def test_decorator(self):
        started = time.time()

        @cache.lock(self.lock_name)
        def locker():
            time.sleep(self.seconds)

        t = threading.Thread(target=locker)
        t.start()

        self.assertFalse(self.lock.acquire(False))
        self.assertFalse(self.lock.acquire(0.2))
        self.assertTrue(self.lock.acquire())
        self.assertGreaterEqual(time.time(), started + self.seconds)

    def test_callablename(self):
        started = time.time()
        name = "1.2"

        @cache.lock(lambda *args: ".".join(args))
        def locker(*args):
            time.sleep(self.seconds)

        t = threading.Thread(target=locker, args=name.split("."))
        t.start()

        lock = Lock(cache, name)
        self.assertFalse(lock.acquire(False))
        self.assertFalse(lock.acquire(0.2))
        self.assertTrue(lock.acquire())
        self.assertGreaterEqual(time.time(), started + self.seconds)
        lock.release()

    def test_lockinstancename(self):
        started = time.time()

        @cache.lock(self.lock)
        def locker():
            time.sleep(self.seconds)

        t = threading.Thread(target=locker)
        t.start()

        self.assertFalse(self.lock.acquire(False))
        self.assertFalse(self.lock.acquire(0.2))
        self.assertTrue(self.lock.acquire())
        self.assertGreaterEqual(time.time(), started + self.seconds)
