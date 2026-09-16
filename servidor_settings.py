"""Configuracao para acesso HTTP interno durante a implantacao."""
from config.settings import *

DEBUG = False
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(MIDDLEWARE.index('django.middleware.security.SecurityMiddleware') + 1,
                  'whitenoise.middleware.WhiteNoiseMiddleware')
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

