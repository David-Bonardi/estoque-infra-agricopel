import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from deploy import versao


def package(path, extra=None):
    files = {n: b'# new version\n' for n in versao.ROOT_FILES}
    files.update({'config/settings.py': b'# settings\n', 'inventory/models.py': b'# models\n',
                  'deploy/versao.py': b'# updater\n'})
    files.update(extra or {})
    manifest = {'format': 1, 'commit': 'a' * 40,
                'files': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr('release.json', json.dumps(manifest))
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackageTests(unittest.TestCase):
    def test_generator_requires_clean_commit(self):
        with patch.object(versao, 'capture', return_value=' M inventory/models.py'), patch.object(versao, 'run') as run:
            with self.assertRaises(RuntimeError):
                versao.pack(Path('unused'))
            run.assert_not_called()

    def test_generator_filters_data_and_produces_valid_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.zip'
            package(source, {'.env': b'PRIVATE', 'dados.json': b'PRIVATE', 'README.md': b'docs'})
            with patch.object(versao, 'capture', side_effect=['', 'b' * 40]), \
                 patch.object(versao, 'read_env', return_value={}), \
                 patch.object(versao, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=source.read_bytes())):
                versao.pack(root / 'releases')
            result = next((root / 'releases').glob('*.zip'))
            manifest = versao.validate(result, root / 'extract')
            self.assertEqual(manifest['commit'], 'b' * 40)
            self.assertNotIn('.env', manifest['files'])
            self.assertNotIn('dados.json', manifest['files'])

    def test_rejects_secrets_and_path_traversal_before_extracting(self):
        for name in ('.env', 'config/../../.env', 'config//settings.py', 'config/bad:stream.py',
                     'servico/EstoqueInfra.xml', 'inventory/data.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                package(root / 'bad.zip', {name: b'not allowed'})
                dest = root / 'extract'
                dest.mkdir()
                with self.assertRaises(RuntimeError):
                    versao.validate(root / 'bad.zip', dest)
                self.assertEqual(list(dest.iterdir()), [])

    def test_wrong_hash_never_stops_service(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(versao, 'service') as service:
            path = Path(tmp) / 'release.zip'
            package(path)
            with self.assertRaises(RuntimeError):
                versao.update(path, '0' * 64)
            service.assert_not_called()

    def test_tampered_content_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root / 'good.zip')
            with zipfile.ZipFile(root / 'good.zip') as source, zipfile.ZipFile(root / 'bad.zip', 'w') as dest:
                for name in source.namelist():
                    dest.writestr(name, b'changed' if name == 'manage.py' else source.read(name))
            with self.assertRaises(RuntimeError):
                versao.validate(root / 'bad.zip', root / 'extract')


@unittest.skipUnless(versao.os.name == 'nt', 'Windows deployment')
class DeploymentTests(unittest.TestCase):
    def simulate(self, failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, backups, pg = root / 'app', root / 'backups', root / 'pg'
            for folder in (app / '.venv/Scripts', app / 'config', app / 'inventory', app / 'servico', pg):
                folder.mkdir(parents=True)
            (app / '.venv/Scripts/python.exe').write_bytes(b'python placeholder')
            (pg / 'pg_dump.exe').write_bytes(b'pg placeholder')
            (app / 'inventory/obsolete.py').write_text('# old')
            (app / 'config/settings.py').write_text('# original')
            (app / 'servico/EstoqueInfra.xml').write_text('preserve-service')
            values = {'DB_NAME': 'estoque', 'DB_USER': 'estoque_app', 'DB_PASSWORD': 'test-only',
                      'DB_HOST': '127.0.0.1', 'DB_PORT': '5432', 'DJANGO_SECRET_KEY': 'test-only'}
            original_env = '\n'.join(f'{k}={json.dumps(v)}' for k, v in values.items())
            (app / '.env').write_text(original_env)
            release = root / 'release.zip'
            digest = package(release)
            calls = []
            def fake_run(args, **kwargs):
                args = [str(a) for a in args]
                calls.append(args)
                if '-Fc' in args:
                    if failure == 'backup':
                        raise subprocess.CalledProcessError(1, 'pg_dump')
                    Path(args[-1]).write_bytes(b'backup placeholder')
                if failure == 'migration' and 'migrate' in args:
                    raise subprocess.CalledProcessError(1, 'migrate')
                return subprocess.CompletedProcess(args, 0)
            with patch.object(versao, 'APP', app), patch.object(versao, 'BACKUPS', backups), \
                 patch.object(versao, 'PG', pg), patch.object(versao, 'run', side_effect=fake_run), \
                 patch.object(versao, 'service') as service, patch.object(versao, 'health'), \
                 patch.object(versao.ctypes.windll.shell32, 'IsUserAnAdmin', return_value=1):
                if failure:
                    with self.assertRaises(subprocess.CalledProcessError):
                        versao.update(release, digest)
                else:
                    versao.update(release, digest)
                actions = [c.args[0] for c in service.call_args_list]
            self.assertEqual((app / '.env').read_text(), original_env)
            self.assertEqual((app / 'servico/EstoqueInfra.xml').read_text(), 'preserve-service')
            if failure == 'backup':
                self.assertEqual(actions, ['check', 'stop', 'start'])
                self.assertEqual((app / 'config/settings.py').read_text(), '# original')
                self.assertFalse(any('migrate' in c for c in calls))
            else:
                backup = next(backups.iterdir())
                self.assertEqual((backup / 'codigo/config/settings.py').read_text(), '# original')
                self.assertTrue((backup / '.venv/Scripts/python.exe').exists())
                self.assertFalse((app / 'inventory/obsolete.py').exists())
                if failure == 'migration':
                    self.assertEqual(actions, ['check', 'stop', 'stop'])
                    self.assertFalse((app / 'versao-instalada.json').exists())
                else:
                    self.assertEqual(actions, ['check', 'stop', 'start'])
                    self.assertEqual(json.loads((app / 'versao-instalada.json').read_text())['commit'], 'a' * 40)

    def test_success_preserves_config_service_and_previous_version(self):
        self.simulate()

    def test_backup_failure_restarts_unchanged_version(self):
        self.simulate('backup')

    def test_migration_failure_keeps_service_stopped(self):
        self.simulate('migration')


if __name__ == '__main__':
    unittest.main()
