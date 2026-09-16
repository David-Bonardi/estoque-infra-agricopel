# Estoque Infra

Controle de estoque em Django 5.2, com páginas Django Templates e telas próprias de cadastro.

## Funcionalidades

- Filiais identificadas por código único, com busca e filtros.
- Tipos de item com controle por quantidade ou patrimônio individual.
- Equipamentos com patrimônio único e número de série opcional e único.
- Entradas, saídas e transferências atômicas, com bloqueio de saldo insuficiente.
- Histórico com usuário, data, quantidade, origem, destino e motivo.
- Login, logout por POST, proteção CSRF e permissões por grupo.
- Categoria e observações no tipo de item; condição, localização interna e observações no equipamento e no saldo por filial.
- Destinatário e setor opcionais em saídas e transferências, separados do usuário que registra a operação.
- Saldos e histórico somente para consulta no Admin; localização alterada por movimentações.

## Executar no PowerShell

Dentro da pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py setup_roles
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Acesse http://127.0.0.1:8000/ e entre com o usuário criado. Cadastros ficam em `/cadastros/`, integrados ao sistema.
O PostgreSQL usa variáveis de ambiente ou o arquivo local `.env`, conforme `CONFIGURACAO.md`. Cada ambiente deve ter seu próprio banco e suas próprias credenciais.
Para uma demonstração isolada com SQLite, execute `$env:USE_SQLITE = '1'` antes dos comandos acima.

## Primeiro uso

1. Acesse Cadastros para criar filiais e tipos de item. Use Quantidade para mouse/teclado e Patrimônio individual para notebook/monitor.
2. Cadastre os patrimônios em Equipamentos. A filial começa vazia; registre uma Entrada para definir sua localização com histórico.
3. Para materiais, registre a contagem inicial como Entrada, informando filial, quantidade e motivo.
4. O superusuário técnico cria os usuários. Contas comuns novas recebem automaticamente o grupo Gestão de estoque, inclusive quando criadas pelo painel técnico. Não é necessário marcar “Membro da equipe”.
5. Os usuários da equipe podem cadastrar e editar filiais, itens e equipamentos, consultar saldos e histórico e registrar movimentações. O perfil padrão não concede permissões de criação de usuários, alteração de grupos ou acesso ao Admin.

Para aplicar o perfil padrão às contas comuns existentes, execute `manage.py setup_roles --assign-users`. O comando não ativa contas inativas nem transforma usuários em membros da equipe ou superusuários. Os grupos legados Consulta e Operação permanecem disponíveis se o administrador técnico quiser atribuir explicitamente um acesso mais restrito depois, removendo o grupo Gestão de estoque.

O Django Admin permanece como ferramenta técnica exclusiva de superusuários. Usuários comuns recebem HTTP 403 mesmo que estejam marcados como membros da equipe ou tentem acessar diretamente `/admin/` e suas subpáginas. Visitantes são encaminhados ao login do sistema. Não há link para o Admin na navegação do aplicativo.
Criações e alterações de cadastro feitas nas novas telas também registram o usuário responsável no log técnico do Django. Saldos e localização continuam sendo alterados apenas por movimentações. Os cadastros oferecem inativação de filiais e tipos de item; não oferecem exclusão.

Os grupos têm acesso global às filiais; restrições por filial não foram implementadas nesta versão.

Em Estoque, use “Editar detalhes” para registrar prateleira/localização, condição e observações dos materiais daquela filial. Essa tela não altera quantidade, item ou filial. Para patrimônios, os detalhes ficam em Cadastros → Equipamentos; a localização interna só pode ser preenchida depois da entrada em uma filial e é limpa ao movimentar o equipamento. Condição e observações do patrimônio são preservadas.

Para materiais por quantidade, a condição descreve o conjunto, sem contagem separada de unidades utilizáveis. Use “Condições variadas” e detalhe as quantidades nas observações quando necessário. Novas entradas ou transferências recebidas deixam a condição do saldo como “Não informado”, para conferir o conjunto após receber novas unidades. A localização e as observações permanecem. Condição ainda não bloqueia movimentações nem calcula disponibilidade para uso.

Na movimentação, o destinatário é texto livre e não precisa ter usuário no sistema. Os campos aparecem apenas em saídas e transferências. O histórico permite buscar por destinatário e setor e mantém “Registrado por” separado.

A carga inicial da planilha legada já foi realizada na implantação, com os saldos finais na filial 00 — base. Notebooks e monitores sem patrimônio começaram por quantidade. Não reimporte essa carga durante atualizações do sistema nem some novamente as movimentações antigas aos saldos.
Uma saída remove o item do estoque da filial; para equipamentos, a localização fica vazia.
Correções são novas movimentações inversas, com referência ao ID original no motivo. Não há edição/exclusão do histórico pelas telas.
Os bloqueios do histórico são da aplicação: administradores com acesso direto ao banco podem alterar registros.

## Testes

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings
```

Esse comando usa SQLite em memória, sem alterar o PostgreSQL. Para validar no PostgreSQL configurado, use `manage.py test`; o usuário do banco precisa poder criar a base temporária de testes.

## Antes de publicar

A configuração inicial é de desenvolvimento. Configure segredos fora do código, DEBUG=False, ALLOWED_HOSTS, HTTPS, arquivos estáticos e backup do PostgreSQL antes de colocar em produção. O servidor `runserver` serve apenas para desenvolvimento.

## Atualizar a instalação Windows

Consulte [ATUALIZACAO.md](ATUALIZACAO.md) para gerar um pacote de um commit Git e publicar no servidor instalado. O atualizador faz backup antes de substituir o código e preserva o `.env`, o serviço e os dados de produção. A implantação atual usa IIS, Waitress e WhiteNoise; HTTPS e backup diário externo ainda precisam ser configurados.
