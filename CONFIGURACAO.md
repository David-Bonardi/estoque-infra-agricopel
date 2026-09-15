# Configuração local e segredos

O projeto lê as variáveis do processo e depois o arquivo `.env` na raiz, sem sobrescrever variáveis já definidas no processo. O `.env` e suas variantes são ignorados pelo Git; apenas `.env.example`, sem credenciais, deve ser versionado.

Para uma instalação nova, copie `.env.example` para `.env`, preencha `DB_PASSWORD` com a senha do banco e gere uma chave exclusiva para `DJANGO_SECRET_KEY`. Não reaproveite credenciais de commits antigos.

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copie a chave gerada para `DJANGO_SECRET_KEY` no `.env`. Não execute a cópia sobre uma configuração local existente. Valores podem ser texto simples ou strings JSON entre aspas duplas. Linhas de comentário começam com `#`; não há interpolação de variáveis nem execução de comandos.

| Variável | Uso |
| --- | --- |
| DJANGO_SECRET_KEY | Chave exclusiva e obrigatória do Django |
| DJANGO_DEBUG | `1` para desenvolvimento; ausente ou `0` desativa debug |
| DJANGO_ALLOWED_HOSTS | Hosts permitidos, separados por vírgula |
| DB_NAME, DB_USER, DB_PASSWORD | Base e credenciais do PostgreSQL |
| DB_HOST, DB_PORT | Endereço do PostgreSQL |
| USE_SQLITE | `1` ativa a demonstração SQLite e dispensa DB_PASSWORD |

Após alterar credenciais, reinicie o processo Django. Se houver variáveis exportadas no terminal/serviço, atualize-as também: elas têm prioridade sobre o `.env`. Em produção, forneça os segredos pelo ambiente de execução e use `DJANGO_DEBUG=0`.

## Credenciais anteriormente versionadas

A senha do PostgreSQL e a SECRET_KEY presentes no commit inicial devem ser consideradas expostas. Ambas foram substituídas no ambiente local durante a correção. As credenciais antigas não devem ser usadas em nenhuma outra instalação.

Um novo commit removendo os valores não apaga commits antigos, clones ou caches. A rotação invalida os valores antigos. Caso se decida remover também o conteúdo do histórico, planeje uma reescrita coordenada com os colaboradores; isso exige atualizar referências remotas e cópias locais. O fluxo normal de correção não faz push forçado.
