import threading
import time

from django_fake_model import models as f
from django.core.cache import cache
from django.db import models
from django.db.backends.sqlite3 import schema
from django.test import TestCase

from django_lock import DEFAULT_SETTINGS, lock, lock_model, Locked


schema.DatabaseSchemaEditor.__enter__ = schema.BaseDatabaseSchemaEditor.__enter__


class Foo(f.FakeModel):
    bar = models.CharField(max_length=8)

    @lock_model
    def lock_id_blocking(self):
        time.sleep(0.5)

    @lock_model(blocking=False)
    def lock_id(self, blocking=True):
        if not blocking:
            return True
        time.sleep(0.5)

    @lock_model("bar", blocking=False)
    def lock_bar(self, blocking=True):
        if not blocking:
            return True
        time.sleep(0.5)


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
            self.assertEqual(
                cache.get(self.lock.key),
                getattr(self.lock.local, self.lock_name))
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

        self.assertLockSuccess(locker, self.lock).join()

    def test_decorator(self):
        @lock(self.lock_name)
        def locker():
            time.sleep(self.seconds)

        self.assertLockSuccess(locker, self.lock).join()

    def test_callablename(self):
        name = "1.2"

        @lock(lambda *args, **kwargs: ".".join(args), blocking=False)
        def locker(*args, blocking=True):
            if not blocking:
                return True
            time.sleep(self.seconds)

        lock_b = lock(name)
        t = self.assertLockSuccess(locker, lock_b, args=name.split("."))
        self.assertTrue(locker("3", blocking=False))
        t.join()

    def test_timeout(self):
        lock_b = lock(self.lock_name, timeout=self.seconds, blocking=False)

        @lock_b
        def locker():
            time.sleep(self.seconds*2)

        started = time.time()
        t = self.assertLockSuccess(locker, lock_b)
        self.assertLess(time.time(), started + self.seconds*2)
        t.join()

    def test_sleep(self):
        self.assertSleep(self.lock, DEFAULT_SETTINGS["SLEEP"])

        sleep = 0.05
        lock_b = lock(self.lock_name, sleep=sleep)
        self.assertSleep(lock_b, sleep)

    def test_thread(self):
        pass

    @Foo.fake_me
    def test_model(self):
        a = Foo.objects.create(bar="a")
        b = Foo.objects.create(bar="b")

        t = threading.Thread(target=a.lock_id_blocking)
        t.start()
        self._wait_subthread()
        self.assertTrue(b.lock_id(False))
        self.assertTrue(b.lock_id(False))
        with self.assertRaises(Locked):
            a.lock_id()
        t.join()

        t = threading.Thread(target=a.lock_bar)
        t.start()
        self._wait_subthread()
        with self.assertRaises(Locked):
            a.lock_bar()
        with self.assertRaises(Locked):
            Foo(bar=a.bar).lock_bar()
        self.assertTrue(b.lock_bar(False))
        self.assertTrue(b.lock_bar(False))
        t.join()

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

        self._wait_subthread()
        self.assertFalse(lock.acquire(False))
        self.assertFalse(lock.acquire(0.2))
        self.assertTrue(lock.acquire(blocking=True))
        self.assertGreaterEqual(time.time(), started + self.seconds)
        return t

    def _wait_subthread(self):
        time.sleep(0.1)
