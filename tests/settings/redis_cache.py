from .locmem import *


CACHES = {
    "default": {
        "BACKEND": "redis_cache.RedisCache",
        "LOCATION": ["127.0.0.1:6379"],
    }
}
