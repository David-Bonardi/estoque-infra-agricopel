# Atualizar o servidor Windows

O desenvolvimento usa o banco local. A producao fica em `C:\Apps\EstoqueInfra`, no servidor `192.168.0.36`, com o servico `EstoqueInfra`, IIS e PostgreSQL 17. O endereco continua `http://192.168.0.36`.

O push salva o codigo no GitHub; a publicacao e uma etapa manual separada. Como a instalacao foi feita por ZIP e o servidor apresentou erro de certificado ao acessar o GitHub, esta primeira versao usa pacotes gerados de um commit local. Nao exige Git nem credenciais GitHub no servidor. Nao foi configurado CI/CD.

## Uma vez: registrar os arquivos de execucao

O repositorio agora inclui `servidor_settings.py`, `iniciar_servidor.py`, `requirements-servidor.txt` e `deploy/versao.py`. Eles correspondem ao backend HTTP usado na instalacao. O atualizador preserva o servico WinSW e o site IIS existentes; nao execute novamente os instaladores desses componentes.

Antes de salvar o primeiro commit, revise todas as alteracoes existentes com `git status` e `git diff`. Ha alteracoes funcionais anteriores no projeto que tambem precisam ser versionadas para que o pacote reflita o sistema instalado. `.env`, backups e o JSON de importacao nao devem aparecer entre os arquivos a adicionar. A deteccao de segredos no gerador e uma verificacao adicional, nao substitui essa revisao.

Copie `deploy\versao.py` do computador de desenvolvimento para `C:\Apps\EstoqueInfra\atualizar_estoque.py` no servidor. Use esta copia externa ao diretorio `deploy` para iniciar as atualizacoes. Ao atualizar o proprio mecanismo de publicacao, revise e copie novamente esse arquivo.

## A cada alteracao, no computador de desenvolvimento

Na pasta do repositorio, implemente e teste usando o banco local. Quando modificar os modelos, gere e revise as migracoes:

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings
.\.venv\Scripts\python.exe -m unittest deploy.test_versao
git status
git diff
```

Depois da revisao, salve e envie a versao:

```powershell
git add -A
git commit -m "Descreva a alteracao"
git push origin main
.\.venv\Scripts\python.exe deploy\versao.py gerar
```

Se estiver trabalhando em outra branch, abra/revise a alteracao e gere a versao a partir do commit aprovado. O gerador usa o `HEAD` local e exige a arvore de trabalho limpa; ele nao confirma se o push teve sucesso. Nao publique se o push falhou.

O comando imprime o caminho `releases\estoque-<commit>.zip` e o SHA256. O pacote inclui apenas os diretorios de codigo e arquivos de execucao permitidos. Nao leva banco, `.env`, servico, `.venv`, logs ou configuracao do IIS. Os hashes detectam arquivos alterados durante a transferencia; nao sao uma assinatura digital. Use apenas pacotes gerados por voce a partir de codigo revisado.

## Publicar no servidor

Avise a equipe sobre a breve indisponibilidade. Copie o ZIP para `C:\Apps\EstoqueInfra\releases` (crie a pasta se necessario). Use o nome e o hash impressos na geracao, substituindo os exemplos abaixo.

Em PowerShell como administrador:

```powershell
Set-Location C:\Apps\EstoqueInfra
.\.venv\Scripts\python.exe .\atualizar_estoque.py atualizar .\releases\estoque-COMMIT.zip --sha256 HASH_IMPRESSO --somente-validar
```

Esse primeiro comando valida o pacote sem parar o servico. Para publicar:

```powershell
.\.venv\Scripts\python.exe .\atualizar_estoque.py atualizar .\releases\estoque-COMMIT.zip --sha256 HASH_IMPRESSO
```

O atualizador:

1. Confere hashes, estrutura do ZIP, servidor, banco, permissoes e servico. Bloqueia atualizacoes simultaneas.
2. Para o servico para interromper as gravacoes pela aplicacao.
3. Faz `pg_dump` completo do banco `estoque`, verifica se o indice do backup e legivel e guarda codigo anterior, `.env` e `.venv` em `C:\ProgramData\EstoqueInfraBackups\<data>-<commit>`. Essa pasta fica restrita a Administradores e SYSTEM.
4. Substitui apenas codigo e arquivos de execucao, incluindo a remocao de arquivos de codigo que deixaram de existir na nova versao.
5. Instala dependencias, verifica o Django e migracoes pendentes de gerar, aplica `migrate` e executa `collectstatic`.
6. Confere consultas de usuarios e saldos no banco, inicia o servico e testa a tela de login e o CSS pelo IIS.
7. Grava o commit em `versao-instalada.json`.

O script de atualizacao exige Python 3.12+; o servidor atual usa 3.13. A versao do Python base nao e atualizada por esse processo. O pip precisa acessar o indice de pacotes; erros de certificado devem ser corrigidos na confianca de certificados/proxy da empresa, sem desativar a verificacao TLS.

O `.env` de producao e mantido. O script nao reimporta o JSON inicial, nao executa `flush` e nao substitui o banco pelo banco de desenvolvimento. Migracoes podem alterar dados: revise migracoes de remocao/transformacao antes de publicar.

Os backups nao sao apagados automaticamente. Reserve espaco para o banco, copia da `.venv` e codigo a cada atualizacao. O backup antes da publicacao nao substitui backups diarios em outro equipamento. A leitura do indice com `pg_restore --list` nao substitui um teste completo de restauracao.

## Depois da publicacao

```powershell
Get-Service EstoqueInfra
Get-Content .\versao-instalada.json
```

No navegador, entre em `http://192.168.0.36`, teste login, saldo e a funcionalidade alterada. As verificacoes automaticas nao fazem login nem criam movimentacoes de teste em producao. O HTTPS continua pendente e sera configurado separadamente.

## Se ocorrer falha

- Antes de substituir o codigo: se o servico chegou a ser parado, o script tenta reiniciar a versao anterior.
- A partir da substituicao do codigo: o script tenta manter o servico parado e informa a pasta do backup. Nao faz rollback automatico do banco, pois uma migracao pode ter aplicado alteracoes parcialmente.
- Logs do aplicativo: `C:\Apps\EstoqueInfra\servico\logs`. Preserve a mensagem do atualizador e a pasta de backup.

Para recuperar, primeiro identifique a etapa que falhou. O diretorio `codigo` contem a copia completa anterior e `.venv` contem suas dependencias. `backup.json` confirma que essa copia terminou antes das alteracoes. Se a falha ocorreu na instalacao de dependencias ou antes de `migrate`, restaure codigo e `.venv` com o servico parado, preserve o `.env`, recoloque as permissoes de leitura da conta LocalService e gere novamente os estaticos da versao anterior. A copia da `.venv` deve voltar ao mesmo caminho original para funcionar.

Se `migrate` comecou, avalie primeiro as migracoes aplicadas e o banco. Restaure `estoque.dump` em um banco separado com PostgreSQL 17 para validar antes de decidir pela troca. O dump nao inclui usuarios globais do PostgreSQL; mantenha/crie o papel `estoque_app` e use `pg_restore --no-owner --no-acl` para restaurar sob esse papel. Nao restaure por cima da producao nem reinicie o codigo antigo sem essa avaliacao. Uma restauracao depois de reabrir o sistema pode perder movimentacoes feitas apos o backup.

Fontes: [Django: checklist de publicacao](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) e [PostgreSQL: pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html).
