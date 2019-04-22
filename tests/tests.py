import threading
import time

from django.core.cache import cache
from django.test import TestCase

from django_lock import DEFAULT_SETTINGS, lock


class LockTestCase(TestCase):
    lock_name = "lock"
    seconds = 0.5

    def setUp(self):
        self.lock = lock(self.lock_name)
        cache.delete(self.lock.key)

    def tearDown(self):
        del self.lock

    def test_acquire(self):
        def locker():
            self.assertTrue(self.lock.acquire(False))
            try:
                time.sleep(self.seconds)
            finally:
                self.lock.release()

        self.assertLockSuccess(locker, self.lock)

    def test_name(self):
        default_prefix = DEFAULT_SETTINGS["PREFIX"]
        self.assertEqual(self.lock.key, default_prefix + self.lock_name)

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
        name = "another_lock"
        lock_b = lock(name)
        self.assertTrue(lock_b.acquire(False))

    def test_context(self):
        def locker():
            with lock(self.lock_name):
                time.sleep(self.seconds)

        self.assertLockSuccess(locker, self.lock)

    def test_decorator(self):
        @lock(self.lock_name)
        def locker():
            time.sleep(self.seconds)

        self.assertLockSuccess(locker, self.lock)

    def test_callablename(self):
        name = "1.2"

        @lock(lambda *args: ".".join(args))
        def locker(*args):
            time.sleep(self.seconds)

        lock_b = lock(name)
        self.assertLockSuccess(locker, lock_b, args=name.split("."))

    def test_timeout(self):
        lock_b = lock(self.lock_name, timeout=self.seconds, blocking=False)

        @lock_b
        def locker():
            time.sleep(self.seconds*2)

        started = time.time()
        self.assertLockSuccess(locker, lock_b)
        self.assertLess(time.time(), started + self.seconds*2)

    def test_sleep(self):
        self.assertSleep(self.lock, DEFAULT_SETTINGS["SLEEP"])

        sleep = 0.05
        lock_b = lock(self.lock_name, sleep=sleep)
        self.assertSleep(lock_b, sleep)

    def test_thread(self):
        pass

    def assertSleep(self, lock, sleep):
        started = time.time()
        self.assertTrue(lock.acquire())
        time.sleep(self.seconds)
        lock.release()
        time_diff = time.time() - started
        self.assertGreater(time_diff, self.seconds - sleep)
        self.assertLess(time_diff, self.seconds + sleep)

    def assertLockSuccess(self, target, lock, args=()):
        started = time.time()

        t = threading.Thread(target=target, args=args)
        t.start()

        time.sleep(0.1)
        self.assertFalse(lock.acquire(False))
        self.assertFalse(lock.acquire(0.2))
        self.assertTrue(lock.acquire(blocking=True))
        self.assertGreaterEqual(time.time(), started + self.seconds)
