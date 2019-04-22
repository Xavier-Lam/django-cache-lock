# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from functools import wraps
import time
import threading
import uuid

from django.conf import settings
from django.core.cache import BaseCache
from django.utils.module_loading import import_string


__all__ = ("lock", "Lock", "LockError", "LockedError", "patch_lock")


DEFAULT_PREFIX = "lock:"


class LockError(ValueError):
    pass


class LockedError(LockError):
    pass


class Lock(object):
    """
    A lock class like `redis.lock.Lock`.
    """

    def __init__(self, client, name, timeout=None, sleep=0.1, blocking=True):
        """
        :type client: django.core.cache.BaseCache
        :type blocking: bool or float
        """
        self.client = client
        self.name = name
        self.timeout = timeout
        self.sleep = sleep
        self.blocking = blocking
        self.local = threading.local()
        if self.timeout and self.sleep > self.timeout:
            raise LockError("'sleep' must be less than 'timeout'")

    @property
    def key(self):
        prefix = getattr(settings, "DJANGOLOCK_PREFIX", DEFAULT_PREFIX)
        return prefix + self.name

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
            token = str(uuid.uuid1())
        if blocking is None:
            blocking = self.blocking
        stop_trying_at = None
        if isinstance(blocking, (int, float)):
            stop_trying_at = time.time() + blocking
        while True:
            if self._acquire(token):
                self.local.token = token
                return True
            if not blocking:
                return False
            if stop_trying_at is not None and time.time() > stop_trying_at:
                return False
            time.sleep(self.sleep)

    def _acquire(self, token):
        return self.client.add(self.key, token, self.timeout)

    def release(self):
        """
        Releases the already acquired lock
        """
        self._release()

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


class lock(object):
    """
    A short cut for Lock.

        from django.core.cache import cache

        with cache.lock("global"):
            pass

        @cache.lock
        def foo():
            pass

    """
    def __init__(self, client, name, timeout=None, sleep=0.1, blocking=True):
        self.client = client
        if callable(name):
            self.name_generator = name
            self.name = None
        else:
            self.name_generator = None
            self.name = name
        self.timeout = timeout
        self.sleep = sleep
        self.blocking = blocking

    def __enter__(self):
        if isinstance(self.name, Lock):
            self.lock = self.name
        else:
            if callable(self.name):
                raise ValueError("You can only use callable as name when decorate a function")
            self.lock = Lock(
                self.client, self.name, self.timeout, self.sleep,
                self.blocking)

        if not self.lock.acquire():
            raise LockedError

        return lock

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            if self.name_generator:
                self.name = self.name_generator(*args, **kwargs)
            with self:
                return func(*args, **kwargs)
        return inner


def patch_lock(locker=None):
    """A dirty method to make lock as an extension method of django's cache

        class AppConfig(AppConfig):
            def ready(self):
                from django_lock import patch_lock
                patch_lock()
    """
    locker = locker or lock

    def partial_lock(self, name, *args, **kwargs):
        return locker(self, name, *args, **kwargs)

    BaseCache.lock = partial_lock
    for cache in settings.CACHES:
        backend = settings.CACHES.get(cache)["BACKEND"]
        cls = import_string(backend)
        cls.lock = partial_lock
