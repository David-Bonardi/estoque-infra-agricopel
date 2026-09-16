"""Backend local. O acesso pela rede sera encaminhado pelo IIS."""
import os

os.environ['DJANGO_SETTINGS_MODULE'] = 'servidor_settings'

from django.core.wsgi import get_wsgi_application
from waitress import serve

if __name__ == '__main__':
    application = get_wsgi_application()
    print('Estoque iniciado em http://127.0.0.1:8080. Ctrl+C para encerrar.', flush=True)
    serve(application, listen='127.0.0.1:8080', threads=4,
          clear_untrusted_proxy_headers=True, expose_tracebacks=False)

