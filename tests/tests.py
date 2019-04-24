# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import threading
import time
try:
    from unittest import mock, TestCase as BaseTestCase
except ImportError:
    import mock
    from unittest2 import TestCase as BaseTestCase
import warnings

from django_fake_model import models as f
from django.core.cache import cache
from django.db import models
from django.db.backends.sqlite3 import schema
from django.test import TestCase
import six

from django_lock import (
    DEFAULT_SETTINGS, lock, lock_model, Locked, LockWarning)


class LockTestCase(type(str("TestCase"), (TestCase, BaseTestCase), dict())):
    lock_name = "lock"

    @classmethod
    def setUpClass(cls):
        super(LockTestCase, cls).setUpClass()
        if six.PY3:
            schema.DatabaseSchemaEditor.__enter__ = \
                schema.BaseDatabaseSchemaEditor.__enter__
        warnings.simplefilter("ignore")

    def setUp(self):
        self.lock = lock(self.lock_name)
        cache.delete(self.lock.key)

    def tearDown(self):
        self.lock.release(True)
        del self.lock

    def test_name(self):
        default_prefix = DEFAULT_SETTINGS["PREFIX"]
        self.assertEqual(self.lock.key, default_prefix + self.lock_name)

        prefix = "prefix:"
        with self.settings(DJANGOLOCK_PREFIX=prefix):
            self.assertEqual(self.lock.key, prefix + self.lock_name)

    def test_acquire(self):
        self.assertTrue(self.lock.acquire(False))
        self.assertFalse(self.lock.acquire(False))
        self.assertRaises(Locked, self.lock.acquire_raise, blocking=False)

        lock_a = lock("lock_a")
        self.assertTrue(lock_a.acquire(False))
        self.assertFalse(lock_a.acquire(False))
        self.lock.release()
        lock_a.release()
        self.assertTrue(self.lock.acquire(False))

    def test_release(self):
        self.assertTrue(self.lock.acquire())
        lock_a = lock(self.lock_name)
        self.assertWarns(LockWarning, lock_a.release)
        self.assertTrue(self.lock.locked)
        self.lock.release()
        self.assertFalse(self.lock.locked)

    def test_timeout(self):
        started = time.time()
        timeout = 0.3
        lock_a = lock(self.lock_name, timeout=timeout)

        def try_lock():
            self.assertFalse(lock_a.acquire(False))
            self.assertTrue(lock_a.acquire())
            diff = time.time() - started
            self.assertGreaterEqual(diff, timeout)
            self.assertLessEqual(diff, timeout + lock_a.sleep)
            lock_a.release()

        t = threading.Thread(target=try_lock)
        self.assertTrue(lock_a.acquire(False))
        t.start()
        time.sleep(timeout*2)
        self.assertWarns(LockWarning, lock_a.release)
        t.join()

    def test_block(self):
        block = 0.2
        lock_a = lock(self.lock_name, blocking=block)
        with lock_a:
            started = time.time()
            self.assertFalse(lock_a.acquire())
            diff = time.time() - started
            self.assertGreaterEqual(diff, block)
            self.assertLess(diff, block + lock_a.sleep)

            block = 0.1
            self.assertFalse(lock_a.acquire(block))
            diff = time.time() - started - diff
            self.assertGreaterEqual(diff, block)
            self.assertLess(diff, block + lock_a.sleep)

    def test_sleep(self):
        count = 3
        sleep = DEFAULT_SETTINGS["SLEEP"]
        lock_a = lock(self.lock_name, sleep=sleep)
        with lock_a:
            with mock.patch.object(lock, "_acquire"):
                lock._acquire.return_value = False
                block = sleep*count + sleep/2
                self.assertFalse(lock_a.acquire(block))
                self.assertEqual(lock._acquire.call_count, count + 2)

            with mock.patch.object(lock, "_acquire"):
                sleep = 0.05
                lock._acquire.return_value = False
                lock_b = lock(self.lock_name, sleep=sleep)
                block = sleep*count + sleep/2
                self.assertFalse(lock_b.acquire(block))
                self.assertEqual(lock._acquire.call_count, count + 2)

    def test_token(self):
        with self.lock:
            self.assertEqual(
                cache.get(self.lock.key),
                getattr(self.lock.local, "token"))

    def test_context(self):
        with self.lock:
            self.assertTrue(self.lock.locked)
        self.assertFalse(self.lock.locked)

    def test_decorator(self):
        lock_a = lock(self.lock_name, blocking=False)

        @lock_a
        def resource():
            self.assertTrue(lock_a.locked)
            self.assertRaises(Locked, resource)

        self.assertEqual(resource.__name__, "resource")
        resource()
        self.assertFalse(lock_a.locked)

    def test_dynamicname(self):
        name = "1.2"
        lock_b = lock(name)

        def name_generator(*args, **kwargs):
            return ".".join(args)

        @lock(name_generator, blocking=False)
        def resource(*args):
            self.assertTrue(lock_b.locked)
            self.assertRaises(Locked, resource, *name.split("."))

        self.assertEqual(resource.__name__, "resource")
        resource(*name.split("."))
        self.assertFalse(lock_b.locked)

    def test_owned(self):
        lock_a = lock(self.lock_name)
        self.assertTrue(self.lock.acquire())
        self.assertTrue(self.lock.owned)
        self.assertFalse(lock_a.owned)

    def test_thread(self):
        unsafe_lock = lock("lock_b", thread_local=False)

        def another_thread():
            self.assertWarns(LockWarning, self.lock.release)
            self.assertTrue(self.lock.locked)
            unsafe_lock.release()
            self.assertFalse(unsafe_lock.locked)
        t = threading.Thread(target=another_thread)

        self.assertTrue(self.lock.acquire())
        self.assertTrue(unsafe_lock.acquire())
        t.start()
        t.join()
        self.assertTrue(self.lock.locked)
        self.assertFalse(unsafe_lock.locked)

    def test_model(self):
        class Foo(f.FakeModel):
            bar = models.CharField(max_length=8)

            @lock_model
            def lock_id_no_arg(self, callback=None):
                callback and callback()

            @lock_model(blocking=False)
            def lock_id(self, callback=None):
                callback and callback()

            @lock_model("bar", blocking=False)
            def lock_bar(self, callback=None):
                callback and callback()

            @property
            def pk_lockname(self):
                return "pk:" + str(self.id)

            @property
            def bar_lockname(self):
                return "bar:" + str(self.bar)

        @Foo.fake_me
        def test_method():
            a = Foo.objects.create(bar="a")
            b = Foo.objects.create(bar="b")

            self.assertEqual(a.lock_id_no_arg.__name__, "lock_id_no_arg")
            self.assertEqual(a.lock_id.__name__, "lock_id")
            self.assertEqual(a.lock_bar.__name__, "lock_bar")

            def callback():
                self.assertTrue(lock(a.pk_lockname).locked)
                self.assertFalse(lock(b.pk_lockname).locked)
                self.assertRaises(Locked, a.lock_id)
            a.lock_id_no_arg(callback)
            self.assertFalse(lock(a.pk_lockname).locked)

            a.lock_id(callback)
            self.assertFalse(lock(a.pk_lockname).locked)

            def callback():
                self.assertTrue(lock(a.bar_lockname).locked)
                self.assertFalse(lock(b.bar_lockname).locked)
                self.assertRaises(Locked, a.lock_bar)
            a.lock_bar(callback)
            self.assertFalse(lock(a.bar_lockname).locked)

        test_method()
