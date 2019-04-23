# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from functools import wraps
import time
import threading
import uuid

from django.conf import settings
from django.core.cache import BaseCache, cache
from django.utils.module_loading import import_string


__all__ = (
    "DEFAULT_SETTINGS", "IncorrectLock", "lock", "lock_model", "Locked",
    "LockError")


DEFAULT_SETTINGS = dict(
    PREFIX="lock:",
    SLEEP=0.1,
    RELEASEONDEL=True
)


def _get_setting(name):
    return getattr(settings, "DJANGOLOCK_" + name, DEFAULT_SETTINGS[name])


_local = threading.local()
_global = type("dummy", (object,), dict())


class LockError(ValueError):
    pass


class Locked(LockError):
    pass


class IncorrectLock(LockError):
    pass


class lock(object):
    """
    A lock class like `redis.lock.Lock`.
    """

    def __init__(
        self, name, client=None, timeout=None, sleep=None, blocking=True,
        token=None, release_on_del=None, thread_local=True):
        """
        :type client: django.core.cache.BaseCache
        :type blocking: bool or float
        """
        self.client = client or cache
        if callable(name):
            self.name_generator = name
            self.name = None
        else:
            self.name_generator = None
            self.name = name
        self.timeout = timeout
        self.sleep = sleep or _get_setting("SLEEP")
        self.blocking = blocking
        self.local = _local if thread_local else _global
        if self.timeout and self.sleep > self.timeout:
            raise IncorrectLock("'sleep' must be less than 'timeout'")
        self.token_generator = token or uuid.uuid1
        if release_on_del is None:
            release_on_del = _get_setting("RELEASEONDEL")
        self.release_on_del = release_on_del
        self._locked = False

    @property
    def key(self):
        prefix = _get_setting("PREFIX")
        if self.name is None:
            raise IncorrectLock("lock's name must be str")
        return prefix + self.name

    def acquire_raise(self, blocking=None, token=None):
        if not self.acquire(blocking, token):
            raise Locked

    def acquire(self, blocking=None, token=None):
        """
        :param blocking: If blocking is False, always return immediately. If
                         blocking is True, the lock will trying to acquire
                         forever. If blocking is a digit, it indicates the
                         maximum amount of time in seconds to spend trying to
                         acquire the lock
        :type blocking: bool or float
        """
        if token is None:
            token = str(self.token_generator())
        if blocking is None:
            blocking = self.blocking
        try_started = time.time()
        while True:
            if self._acquire(token):
                return True
            if not blocking:
                return False
            if blocking is not True and time.time() - try_started > blocking:
                return False
            time.sleep(self.sleep)

    def _acquire(self, token):
        if self.client.add(self.key, token, self.timeout):
            setattr(self.local, self.name, token)
            return True
        return False

    def release(self, force=False):
        """
        Releases the already acquired lock
        """
        try:
            self._release(force)
        except IncorrectLock:
            pass

    def _release(self, force=False):
        # TODO: use lua script to release redis lock
        expected_token = getattr(self.local, self.name)
        token = self.client.get(self.key)
        if token and token != expected_token and not force:
            raise LockError("Cannot release a lock that's no longer owned")
        self.client.delete(self.key)

    @property
    def locked(self):
        """
        Returns True if this key is locked by any process, otherwise False.
        """
        return bool(self.client.get(self.key))

    @property
    def owned(self):
        """
        Returns True if this key is locked by this lock, otherwise False.
        """
        expected_token = getattr(self.local, self.name)
        token = self.client.get(self.key)
        return bool(token and expected_token == token)

    def __enter__(self):
        self.acquire_raise()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def __del__(self):
        try:
            self.release_on_del and self.name and self.release()
        except:
            pass

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            if self.name_generator:
                self.name = self.name_generator(*args, **kwargs)
            try:
                with self:
                    return func(*args, **kwargs)
            finally:
                if self.name_generator:
                    self.name = None
        return inner

    @classmethod
    def patch_cache(cls):
        """
        A dirty method to make lock as an extension method of django's
        default cache

            class AppConfig(AppConfig):
                def ready(self):
                    from django_lock import lock
                    lock.patch_cache()

            ...

            from django.core.cache import cache
            @cache.lock
            def foo():
                pass

        """
        def partial_lock(self, name, *args, **kwargs):
            return cls(self, name, *args, **kwargs)

        cache.__class__.lock = partial_lock


def lock_model(func_or_args=None, *keys, refresh_from_db=True, **kw):
    """
    A shortcut to lock a model instance

        from django.db import models
        from django_lock import lock_model

        class Foo(models.Model):
            first_name = models.CharField(max_length=32)
            last_name = models.CharField(max_length=32)

            @lock_model
            def bar(self, *args, **kwargs):
                pass

            @lock_model("first_name", "last_name", blocking=False)
            def bar(self, *args, **kwargs):
                pass

    """
    def _get_name(self, *args, **kwargs):
        values = [getattr(self, key) for key in keys]
        kvs = zip(keys, values)
        # TODO: max length of cache key
        return ":".join(map(lambda o: ":".join(map(str, o)), kvs))

    def refresh_wrapper(func):
        @wraps(func)
        def decorated_func(self, *args, **kwargs):
            refresh_from_db and self.refresh_from_db()
            return func(self, *args, **kwargs)
        return decorated_func

    def decorator(func):
        return wraps(
            lock(_get_name, **kw)(
                refresh_wrapper(func)))

    if func_or_args and callable(func_or_args):
        keys = ("pk",)
        return decorator(func_or_args)
    else:
        if func_or_args:
            keys = (func_or_args, ) + keys
        else:
            keys = ("pk",)

        return decorator
