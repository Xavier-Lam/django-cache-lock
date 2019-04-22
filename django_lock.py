# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from functools import wraps
import time
import threading
import uuid

from django.conf import settings
from django.core.cache import BaseCache, cache
from django.utils.module_loading import import_string


__all__ = ("DEFAULT_SETTINGS", "lock", "IncorrectLock", "Locked", "LockError")


DEFAULT_SETTINGS = dict(
    PREFIX="lock:",
    SLEEP=0.1,
    RELEASEONDEL=True
)


def _get_setting(name):
    return getattr(settings, "DJANGOLOCK_" + name, DEFAULT_SETTINGS[name])


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
        token=None, release_on_del=None):
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
        self.local = threading.local()
        if self.timeout and self.sleep > self.timeout:
            raise IncorrectLock("'sleep' must be less than 'timeout'")
        self.token_generator = token or uuid.uuid1
        if release_on_del is None:
            release_on_del = _get_setting("RELEASEONDEL")
        self.release_on_del = release_on_del

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
                self.local.token = token
                return True
            if not blocking:
                return False
            if blocking is not True and time.time() - try_started > blocking:
                return False
            time.sleep(self.sleep)

    def _acquire(self, token):
        return self.client.add(self.key, token, self.timeout)

    def release(self):
        """
        Releases the already acquired lock
        """
        try:
            self._release()
        except IncorrectLock:
            pass

    def _release(self):
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
        token = self.client.get(self.key)
        return self.local.token is not None and token == self.local.token

    def __enter__(self):
        self.acquire_raise()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def __del__(self):
        self.release_on_del and self.release()

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
