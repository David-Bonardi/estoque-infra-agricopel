"""Pacotes Git e atualizacao do servidor Windows. Nao usa credenciais do GitHub."""
import argparse
import ctypes
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT_FILES = {'manage.py', 'requirements.txt', 'requirements-servidor.txt',
              'servidor_settings.py', 'iniciar_servidor.py'}
CODE_DIRS = {'config', 'inventory', 'deploy'}
APP = Path(r'C:\Apps\EstoqueInfra')
BACKUPS = Path(r'C:\ProgramData\EstoqueInfraBackups')
PG = Path(r'C:\Program Files\PostgreSQL\17\bin')


def allowed(name):
    p = PurePosixPath(name)
    if '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or p.as_posix() != name:
        return False
    if any(part.startswith('.') or part == '__pycache__' for part in p.parts):
        return False
    return name in ROOT_FILES or (len(p.parts) > 1 and p.parts[0] in CODE_DIRS
        and p.suffix.lower() in {'.py', '.html', '.css', '.js', '.svg', '.png', '.md', '.ps1'})


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def capture(args, **kwargs):
    return run(args, stdout=subprocess.PIPE, text=True, **kwargs).stdout.strip()


def pack(output):
    repo = Path(__file__).resolve().parent.parent
    if capture(['git', 'status', '--porcelain'], cwd=repo):
        raise RuntimeError('Salve todas as alteracoes em um commit antes de gerar a versao.')
    commit = capture(['git', 'rev-parse', 'HEAD'], cwd=repo)
    raw = run(['git', 'archive', '--format=zip', 'HEAD'], cwd=repo, stdout=subprocess.PIPE).stdout
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        files = {n: source.read(n) for n in source.namelist() if allowed(n) and not n.endswith('/')}
    if not ROOT_FILES.issubset(files) or 'config/settings.py' not in files:
        raise RuntimeError('Commit incompleto: faltam arquivos de execucao.')
    # Detecta segredos locais que tenham sido copiados acidentalmente para o codigo.
    if (repo / '.env').exists():
        secrets = read_env(repo / '.env')
        for key in ('DB_PASSWORD', 'DJANGO_SECRET_KEY'):
            secret = secrets.get(key, '').encode()
            if secret and any(secret in data for data in files.values()):
                raise RuntimeError('Segredo local encontrado no codigo. Pacote nao criado.')
    manifest = {'format': 1, 'commit': commit, 'created': datetime.now(timezone.utc).isoformat(),
                'files': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'estoque-{commit[:12]}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as dest:
        for name, data in files.items():
            dest.writestr(name, data)
        dest.writestr('release.json', json.dumps(manifest, indent=2))
    print(target)
    print('SHA256:', hashlib.sha256(target.read_bytes()).hexdigest())


def validate(package, destination):
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(n.casefold() for n in names)):
            raise RuntimeError('Pacote com nomes duplicados.')
        manifest = json.loads(archive.read('release.json'))
        if manifest['format'] != 1 or not re.fullmatch(r'[0-9a-f]{40}', manifest['commit']):
            raise RuntimeError('Manifesto invalido.')
        files = manifest['files']
        if set(names) != set(files) | {'release.json'} or not ROOT_FILES.issubset(files):
            raise RuntimeError('Pacote incompleto ou com arquivos extras.')
        if 'config/settings.py' not in files or 'inventory/models.py' not in files:
            raise RuntimeError('Faltam modulos da aplicacao.')
        if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise RuntimeError('Pacote excede 100 MB.')
        # Valida todos os caminhos e hashes antes de escrever qualquer arquivo.
        for name, digest in files.items():
            if not allowed(name) or hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise RuntimeError('Caminho ou integridade invalida no pacote.')
        for name in files:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    return manifest


def read_env(path):
    result = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.strip().isidentifier():
            raise RuntimeError('Formato invalido no .env; conteudo nao exibido.')
        result[key.strip()] = json.loads(value.strip()) if value.strip().startswith('"') else value.strip()
    return result


def service(action):
    commands = {
        'stop': "Stop-Service EstoqueInfra -ErrorAction Stop; (Get-Service EstoqueInfra).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(60))",
        'start': "Start-Service EstoqueInfra -ErrorAction Stop; (Get-Service EstoqueInfra).WaitForStatus('Running',[TimeSpan]::FromSeconds(60))",
        'check': "if ((Get-Service EstoqueInfra -ErrorAction Stop).Status -ne 'Running') { throw 'O servico deve estar Running antes da atualizacao.' }",
    }
    run(['powershell.exe', '-NoProfile', '-Command', "$ErrorActionPreference='Stop'; " + commands[action]])


def health():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(20):
        try:
            with opener.open('http://192.168.0.36/', timeout=2) as response:
                if response.status != 200 or b'csrfmiddlewaretoken' not in response.read():
                    raise RuntimeError('Pagina de login nao encontrada.')
            with opener.open('http://192.168.0.36/static/inventory/app.css', timeout=2) as response:
                if response.status != 200:
                    raise RuntimeError('CSS indisponivel.')
            return
        except Exception:
            if attempt == 19:
                raise RuntimeError('Falha no teste HTTP de login/estilos.') from None
            time.sleep(1)


def update(package, expected_hash, check_only=False):
    if hashlib.sha256(package.read_bytes()).hexdigest().lower() != expected_hash.lower():
        raise RuntimeError('SHA256 diferente do informado na geracao do pacote.')
    with tempfile.TemporaryDirectory(prefix='estoque-release-') as tmp, ExitStack() as stack:
        staging = Path(tmp)
        manifest = validate(package, staging)
        print('Pacote validado. Commit:', manifest['commit'])
        if check_only:
            return
        if os.name != 'nt' or not ctypes.windll.shell32.IsUserAnAdmin():
            raise RuntimeError('Execute no PowerShell como administrador do servidor.')
        # Guardas contra executar por engano no computador de desenvolvimento.
        run(['powershell.exe', '-NoProfile', '-Command',
             "if (-not (Get-NetIPAddress -IPAddress 192.168.0.36 -ErrorAction SilentlyContinue)) { exit 1 }"])
        import msvcrt
        lock = stack.enter_context((APP / '.deploy.lock').open('a+b'))
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Outra atualizacao esta em andamento.') from None
        service('check')
        python = APP / '.venv/Scripts/python.exe'
        if not python.is_file() or not (PG / 'pg_dump.exe').is_file():
            raise RuntimeError('Python ou PostgreSQL 17 nao encontrado no caminho esperado.')
        for folder in CODE_DIRS | {'.venv'}:
            if (APP / folder).is_symlink() or (APP / folder).is_junction():
                raise RuntimeError('Pasta de aplicacao nao pode ser link/junction.')
        values = read_env(APP / '.env')
        for key in ('DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DJANGO_SECRET_KEY'):
            if not values.get(key):
                raise RuntimeError(f'Configure {key} no .env.')
        if values.get('USE_SQLITE') == '1' or values['DB_NAME'] != 'estoque' or values['DB_HOST'] not in ('127.0.0.1', 'localhost'):
            raise RuntimeError('Banco diferente do estoque local esperado.')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DJANGO_', 'DB_')) and k != 'USE_SQLITE'}
        env.update(values)
        env['DJANGO_SETTINGS_MODULE'] = 'servidor_settings'
        original_env = (APP / '.env').read_bytes()
        if BACKUPS.is_symlink() or BACKUPS.is_junction():
            raise RuntimeError('A pasta de backups nao pode ser link/junction.')
        BACKUPS.mkdir(parents=True, exist_ok=True)
        # Backups contêm dados internos. Acesso somente Administradores e SYSTEM.
        run(['icacls.exe', BACKUPS, '/inheritance:r', '/grant:r',
             '*S-1-5-32-544:(OI)(CI)(F)', '*S-1-5-18:(OI)(CI)(F)'], stdout=subprocess.DEVNULL)
        backup = BACKUPS / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + manifest['commit'][:12])
        backup.mkdir()
        print('Backup desta atualizacao:', backup, flush=True)
        stopped = changed = False
        try:
            service('stop')
            stopped = True
            pg_env = dict(env, PGPASSWORD=values['DB_PASSWORD'], PGCONNECT_TIMEOUT='10')
            run([PG / 'pg_dump.exe', '-h', values['DB_HOST'], '-p', values['DB_PORT'],
                 '-U', values['DB_USER'], '-d', values['DB_NAME'], '-w', '-Fc', '-f', backup / 'estoque.dump'], env=pg_env)
            run([PG / 'pg_restore.exe', '--list', backup / 'estoque.dump'], stdout=subprocess.DEVNULL)
            shutil.copy2(APP / '.env', backup / '.env')
            shutil.copytree(APP / '.venv', backup / '.venv')
            if (APP / 'versao-instalada.json').exists():
                shutil.copy2(APP / 'versao-instalada.json', backup / 'versao-instalada.json')
            old_code = backup / 'codigo'
            old_code.mkdir()
            for name in sorted(CODE_DIRS | ROOT_FILES):
                current = APP / name
                if current.is_dir():
                    shutil.copytree(current, old_code / name)
                elif current.is_file():
                    shutil.copy2(current, old_code / name)
            (backup / 'backup.json').write_text(json.dumps({
                'target_commit': manifest['commit'], 'code_backup_complete': True,
                'previous_files': sorted(p.name for p in old_code.iterdir()),
            }, indent=2), encoding='utf-8')
            retired = backup / 'substituidos'
            retired.mkdir()
            # Move somente os diretorios de codigo explicitamente permitidos.
            # .env, servico, logs, dados e configuracao IIS permanecem no lugar.
            changed = True
            for name in sorted(CODE_DIRS | ROOT_FILES):
                target = APP / name
                if target.resolve().parent != APP.resolve():
                    raise RuntimeError('Destino fora da pasta da aplicacao.')
                if target.exists():
                    shutil.move(str(target), str(retired / name))
                incoming = staging / name
                if incoming.is_dir():
                    shutil.copytree(incoming, target)
                elif incoming.is_file():
                    shutil.copy2(incoming, target)
            # Arquivos novos recebem a permissao necessaria ao servico LocalService.
            for name in sorted(CODE_DIRS | ROOT_FILES):
                if (APP / name).exists():
                    run(['icacls.exe', APP / name, '/grant', '*S-1-5-19:RX', '/T', '/Q'], stdout=subprocess.DEVNULL)
            run([python, '-m', 'pip', 'install', '-r', 'requirements-servidor.txt'], cwd=APP, env=env)
            run([python, '-m', 'pip', 'check'], cwd=APP, env=env)
            def manage(*args):
                run([python, 'manage.py', *args], cwd=APP, env=env)
            manage('check')
            manage('makemigrations', '--check', '--dry-run')
            manage('migrate', '--noinput')
            manage('collectstatic', '--noinput', '--clear')
            manage('shell', '-c', 'from django.contrib.auth import get_user_model; from inventory.models import Balance; print("Usuarios:", get_user_model().objects.count(), "Saldos:", Balance.objects.count())')
            if (APP / '.env').read_bytes() != original_env:
                raise RuntimeError('.env alterado inesperadamente.')
            service('start')
            health()
            (APP / 'versao-instalada.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            print('Atualizacao concluida. Login e CSS responderam pelo IIS. Teste seu login e o estoque.')
        except BaseException:
            if changed:
                try:
                    service('stop')
                except Exception:
                    pass
                print('ATUALIZACAO INTERROMPIDA. Nao reinicie sem avaliar as migracoes. Backup:', backup, file=sys.stderr)
            elif stopped:
                service('start')
                print('Codigo e banco nao alterados; versao anterior reiniciada.', file=sys.stderr)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('gerar')
    build.add_argument('--saida', type=Path, default=Path('releases'))
    install = commands.add_parser('atualizar')
    install.add_argument('pacote', type=Path)
    install.add_argument('--sha256', required=True)
    install.add_argument('--somente-validar', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'gerar':
            pack(args.saida)
        else:
            update(args.pacote, args.sha256, args.somente_validar)
    except Exception as error:
        print(f'Falha: {error}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
