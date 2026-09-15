import os
from pathlib import Path
from unittest.mock import Mock, patch
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from .environment import load_local_environment, required_environment


class EnvironmentTests(SimpleTestCase):
    def test_local_values_and_process_precedence(self):
        with patch.dict(os.environ, {'EXISTING': 'process'}, clear=True):
            path = Mock(spec=Path)
            path.is_file.return_value = True
            path.read_text.return_value = '# local\nEXISTING="file"\nSPECIAL="test#with=characters"\n'
            load_local_environment(path)
            self.assertEqual(os.environ['EXISTING'], 'process')
            self.assertEqual(os.environ['SPECIAL'], 'test#with=characters')

    def test_missing_required_secret_fails_without_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_SECRET_KEY'):
                required_environment('DJANGO_SECRET_KEY')

    def test_invalid_local_value_does_not_leak_contents(self):
        path = Mock(spec=Path)
        path.is_file.return_value = True
        path.read_text.return_value = 'TOKEN="invalid-sensitive-value'
        with self.assertRaises(ImproperlyConfigured) as raised:
            load_local_environment(path)
        self.assertNotIn('invalid-sensitive-value', str(raised.exception))
