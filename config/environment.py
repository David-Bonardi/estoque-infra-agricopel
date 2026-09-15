"""Load local JSON-quoted .env values without overriding process environment."""
import json
import os
from django.core.exceptions import ImproperlyConfigured


def load_local_environment(path):
    if not path.is_file():
        return
    for line_number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not separator or not key.isidentifier():
            raise ImproperlyConfigured(f'Formato inválido no .env, linha {line_number}.')
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ImproperlyConfigured(f'Valor inválido no .env, linha {line_number}.') from None
        if not isinstance(value, str):
            raise ImproperlyConfigured(f'O .env exige texto na linha {line_number}.')
        os.environ.setdefault(key, value)


def required_environment(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f'Configure {name} no ambiente ou no arquivo .env local.')
    return value
