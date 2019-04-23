from .locmem import *


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': os.path.join(BASE_DIR, "django_cache")
    }
}
