# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import threading
import time
from unittest import skipIf, skipUnless
try:
    from unittest import mock, TestCase as BaseTestCase
except ImportError:
    import mock
    from unittest2 import TestCase as BaseTestCase
import warnings

import django
from django_fake_model import models as f
from django.conf import settings
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends.memcached import BaseMemcachedCache
from django.db import models
from django.db.backends.sqlite3 import schema
from django.test import TestCase

from django_lock import (_backend_cls, DEFAULT_SETTINGS, lock, lock_model,
                         Lock, Locked, LockWarning, redis_backends)


class BaseFakeModel(f.FakeModel):
    @property
    def lock_name(self):
        return "{app_label}:{table}:".format(
            app_label=self._meta.app_label,
            table=self._meta.db_table
        )

    @property
    def pk_lockname(self):
        return self.lock_name + "pk:" + str(self.id)

    class Meta(object):
        abstract = True
        app_label = 'django_fake_models'


custom_lock_name = "foo:another_lock:"


class Foo(BaseFakeModel):
    bar = models.CharField(max_length=8)

    @lock_model
    def lock_id_no_arg(self, callback=None):
        callback and callback()

    @lock_model(blocking=False)
    def lock_id(self, callback=None):
        callback and callback()

    @lock_model(name=custom_lock_name)
    def another_lockid(self, callback=None):
        callback and callback()

    @lock_model("bar", blocking=False)
    def lock_bar(self, callback=None):
        callback and callback()

    @lock_model(refresh_from_db=False)
    def lock_without_refresh(self):
        pass

    @property
    def bar_lockname(self):
        return self.lock_name + "bar:" + str(self.bar)


class Another(BaseFakeModel):
    @lock_model(blocking=False)
    def lock_id(self, callback=None):
        callback and callback()


class LockTestCase(type(str("TestCase"), (TestCase, BaseTestCase), dict())):
    lock_name = "lock"

    @classmethod
    def setUpClass(cls):
        super(LockTestCase, cls).setUpClass()
        if django.VERSION[0] >= 2:
            schema.DatabaseSchemaEditor.__enter__ = \
                schema.BaseDatabaseSchemaEditor.__enter__
        settings.DEBUG = True
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
        # redis in python2.7 sometimes won't raise LockWarning
        self.assertWarns(LockWarning, lock_a.release)
        self.assertTrue(self.lock.locked)
        self.lock.release()
        self.assertFalse(self.lock.locked)

        # TODO: release a lock no longer owned
        pass

    @skipUnless(issubclass(_backend_cls(cache), redis_backends),
                "test only when redis backend")
    def test_release_redis(self):
        pass

    def test_extend(self):
        self.assertTrue(self.lock.acquire())
        self.assertTrue(self.lock.extend())
        self.lock.client.delete(self.lock.key)
        self.assertFalse(self.lock.extend())

        lock_a = lock(self.lock_name, timeout=1)
        self.assertTrue(lock_a.acquire())
        self.assertTrue(lock_a.extend())
        time.sleep(1.5)
        self.assertFalse(lock_a.extend())

    def test_acquire_extend(self):
        pass

    @skipIf(issubclass(_backend_cls(cache), BaseMemcachedCache),
            "memcached's expire time is not exact as other backends")
    def test_timeout(self):
        timeout = 1
        lock_a = lock(self.lock_name, timeout=timeout)

        started = time.time()
        self.assertTrue(lock_a.acquire(False))
        self.assertTrue(self.lock.acquire())
        diff = time.time() - started
        self.assertGreaterEqual(diff, timeout)
        self.assertLessEqual(diff, timeout + self.lock.sleep)
        self.lock.release()
        self.assertFalse(lock_a.locked)
        self.assertWarns(LockWarning, lock_a.release)

    @skipUnless(issubclass(_backend_cls(cache), BaseMemcachedCache),
                "memcached's expire time is not exact as other backends")
    def test_timeout_memcached(self):
        timeout = 2
        lock_a = lock(self.lock_name, timeout=timeout)

        started = time.time()
        self.assertTrue(lock_a.acquire(False))
        self.assertTrue(self.lock.acquire())
        diff = time.time() - started
        self.assertGreaterEqual(diff, timeout - 1)
        self.assertLessEqual(diff, timeout + self.lock.sleep)
        self.lock.release()
        self.assertFalse(lock_a.locked)
        self.assertWarns(LockWarning, lock_a.release)

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
            with mock.patch.object(Lock, "_acquire"):
                Lock._acquire.return_value = False
                block = sleep*count + sleep/2
                self.assertFalse(lock_a.acquire(block))
                self.assertEqual(Lock._acquire.call_count, count + 2)

            with mock.patch.object(Lock, "_acquire"):
                sleep = 0.05
                Lock._acquire.return_value = False
                lock_b = lock(self.lock_name, sleep=sleep)
                block = sleep*count + sleep/2
                self.assertFalse(lock_b.acquire(block))
                self.assertEqual(Lock._acquire.call_count, count + 2)

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

        self.assertTrue(self.lock.acquire())
        self.assertTrue(unsafe_lock.acquire())
        t = threading.Thread(target=another_thread)
        t.start()
        t.join()
        self.assertTrue(self.lock.locked)
        self.assertFalse(unsafe_lock.locked)

    @skipIf(issubclass(_backend_cls(cache), LocMemCache),
            "locmem cache unable to lock multi proccess workers")
    def test_proccess(self):
        another = "another"
        commands = [
            "from django_lock import lock",
            "unlock_lock = lock('%s', blocking=False)" % another,
            "locked_lock = lock('%s', blocking=False)" % self.lock_name,
            "unlock_lock.acquire()",
            "unlock_lock.release()",
            "exit(0 if locked_lock.locked else 1)"
        ]
        codes = ";".join(commands)
        with self.lock:
            ret = os.system('django-admin shell -c "%s"' % codes)
        self.assertEqual(ret, 0)

    @Foo.fake_me
    @Another.fake_me
    def test_model(self):
        a = Foo.objects.create(bar="a")
        b = Foo.objects.create(bar="b")
        c = Another.objects.create()

        self.assertEqual(a.lock_id_no_arg.__name__, "lock_id_no_arg")
        self.assertEqual(a.lock_id.__name__, "lock_id")
        self.assertEqual(a.lock_bar.__name__, "lock_bar")

        def callback():
            self.assertTrue(lock(a.pk_lockname).locked)
            self.assertFalse(lock(b.pk_lockname).locked)
            self.assertRaises(Locked, a.lock_id)
            self.assertFalse(lock(c.pk_lockname).locked)
            c.lock_id()
            another_lock_name = a.pk_lockname.replace(
                a.lock_name, custom_lock_name)
            self.assertFalse(lock(another_lock_name).locked)
            a.another_lockid(lambda: self.assertTrue(
                lock(another_lock_name).locked))
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

    @Foo.fake_me
    def test_model_context(self):
        a = Foo.objects.create(bar="a")
        b = Foo.objects.create(bar="b")

        with lock_model(a, blocking=False):
            self.assertTrue(lock(a.pk_lockname).locked)
            self.assertFalse(lock(b.pk_lockname).locked)
            self.assertFalse(lock_model(a, blocking=False).acquire())
            self.assertRaises(Locked, a.lock_id)

        self.assertFalse(lock(a.pk_lockname).locked)

        with lock_model(a, "bar", blocking=False):
            self.assertTrue(lock(a.bar_lockname).locked)
            self.assertFalse(lock(b.bar_lockname).locked)
            self.assertFalse(
                lock_model(a, "bar", blocking=False).acquire())
            self.assertRaises(Locked, a.lock_bar)

        self.assertFalse(lock(a.bar_lockname).locked)

    @Foo.fake_me
    def test_model_refresh(self):
        a = Foo.objects.create(bar="a")
        with mock.patch.object(Foo, "refresh_from_db"):
            a.lock_without_refresh()
            self.assertFalse(Foo.refresh_from_db.called)

            a.lock_id()
            self.assertTrue(Foo.refresh_from_db.called)

        with mock.patch.object(Foo, "refresh_from_db"):
            with lock_model(a, refresh_from_db=False):
                pass
            self.assertFalse(Foo.refresh_from_db.called)

            with lock_model(a):
                pass
            self.assertTrue(Foo.refresh_from_db.called)
