# EXPLAIN_GOOGLE_IMPLEMENTATION.md

Este documento explica, do zero, como o **login com conta Google (OAuth 2.0 /
OpenID Connect)** foi implementado neste projeto. Foi escrito para alguém que
**nunca** integrou o Google em uma aplicação: o fluxo completo, os conceitos,
onde cada pedaço vive no código, como configurar e como testar.

---

## 1. O que é o OAuth 2.0 / OpenID Connect (em palavras simples)

Quando um usuário clica em "Entrar com Google", a sua aplicação **não recebe a
senha do Google** dele. Em vez disso, acontece o seguinte:

1. A sua aplicação redireciona o navegador do usuário para uma página do Google
   (a "tela de consentimento").
2. O usuário faz login no Google (se ainda não estiver) e **autoriza** a sua
   aplicação a ver alguns dados dele (nome e e-mail, por exemplo).
3. O Google redireciona o navegador de volta para a sua aplicação, levando um
   **código** (o "authorization code").
4. A sua aplicação troca esse código por um **ID Token** (um JWT assinado pelo
   Google que contém o e-mail, o nome e um identificador único do usuário).
5. A sua aplicação **verifica** se esse token foi mesmo emitido pelo Google e se
   não foi adulterado.
6. De posse do e-mail verificado, a aplicação cria o usuário (se não existir) ou
   o associa à conta já existente, e gera os tokens JWT **da própria aplicação**
   (access + refresh).

O **OAuth 2.0** cuida da autorização (dar acesso a dados). O **OpenID Connect**
(OIDC) é uma camada em cima do OAuth que cuida da *autenticação*: ele define o
**ID Token**, um JWT com os dados da identidade do usuário. O Google usa os dois
juntos.

### Termos que você precisa conhecer

| Termo | O que é | Analogia |
|---|---|---|
| `client_id` | Identificador público da sua aplicação no Google. Não é segredo. | Seu crachá de identificação. |
| `client_secret` | Senha da sua aplicação junto ao Google. **Nunca** exponha. | A chave do seu armário. |
| `redirect_uri` | URL para onde o Google manda o navegador depois do consentimento. Tem que estar cadastrada no console. | O endereço de onde o "correio" chega. |
| `authorization code` | Código de uso único que o Google devolve no redirect. | Um vale-compras de uso único. |
| `id_token` | JWT assinado pelo Google com nome, e-mail, `sub` etc. | O RG carimbado pelo Google. |
| `sub` | Identificador único do usuário dentro do Google (Google User ID). | O número do RG. |
| `scopes` | Permissões pedidas (`openid`, `email`, `profile`). | O que você pede para ver. |
| `state` | Valor aleatório que você envia e recebe de volta, para proteger contra CSRF. | A senha combinada com o porteiro. |
| `JWKS` | Conjunto de chaves públicas do Google usadas para validar a assinatura do `id_token`. | O livro com as assinaturas oficiais. |

### O Authorization Code Flow (o fluxo "certinho")

```
 Navegador                Seu Backend                    Google
    |  1. GET /api/auth/google/url  |                        |
    |------------------------------->|   gera `state`        |
    |                                |                        |
    |  2. 302 -> consent screen      |                        |
    |<-------------------------------------------------------|
    |  3. usuário loga e autoriza    |                        |
    |                                                        |
    |  4. redirect_uri?code=X&state=S                       |
    |<-------------------------------------------------------|
    |  5. POST /api/auth/google/callback {code, state}      |
    |-------------------------------|   valida `state`       |
    |                                |  6. POST token endpoint|
    |                                |------------------------>  code -> id_token
    |                                |  7. valida id_token    |
    |                                |  8. cria/associa user  |
    |  9. access_token + refresh_token                       |
```

---

## 2. Configurando o lado do Google (Google Cloud Console)

> Faça isso **uma vez**; nada disso muda o código.

1. Acesse <https://console.cloud.google.com/> e crie/selecione um projeto.
2. Ative a API **OAuth consent screen**:
   - Menu hambúrguer → *APIs & Services* → *OAuth consent screen*.
   - Escolha *External* (ou *Internal* se for uso interno) e preencha o nome da
     aplicação e o e-mail de suporte.
   - Em *Authorized domains* adicione o domínio da sua aplicação.
   - Em *Scopes*, não precisa adicionar nada manualmente: os scopes `email`,
     `profile` e `openid` já vêm habilitados.
3. Crie as credenciais:
   - *APIs & Services* → *Credentials* → *Create credentials* → **OAuth client
     ID**.
   - Application type: **Web application**.
   - **Authorized redirect URIs**: cadastre exatamente o `GOOGLE_REDIRECT_URI`
     da sua aplicação (ex.: `http://localhost:8001/api/auth/google/callback`).
     Uma URL diferente da cadastrada **falha na troca do código**.
   - Ao final, o console mostra o `client_id` e o `client_secret`.

> Dica: o `client_secret` só aparece uma vez — copie na hora. Trate-o como senha.

4. Preencha o `.env` da aplicação (veja a seção 3).

---

## 3. Variáveis de ambiente

Adicionadas em `app/core/config.py` (`BaseAppSettings`) e documentadas em
`.env.example` e `.env.template`:

| Variável | Obrigatória? | Descrição |
|---|---|---|
| `GOOGLE_LOGIN_ENABLED` | Sim (definir `true` para ligar) | Liga/desliga o login Google. Padrão: `false`. |
| `GOOGLE_CLIENT_ID` | Sim, se habilitado | Id público da sua aplicação. |
| `GOOGLE_CLIENT_SECRET` | Sim, se habilitado | Segredo da sua aplicação. |
| `GOOGLE_REDIRECT_URI` | Sim, se habilitado | URL de callback cadastrada no console. |
| `GOOGLE_AUTH_URL` | Não | URL da tela de consentimento (default já correto). |
| `GOOGLE_TOKEN_URL` | Não | Endpoint de troca do código (default já correto). |
| `GOOGLE_CERTS_URL` | Não | JWKS do Google (default já correto). |
| `GOOGLE_ISSUER` | Não | Emissor esperado no `id_token` (default já correto). |

Exemplo:

```dotenv
GOOGLE_LOGIN_ENABLED=true
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
GOOGLE_REDIRECT_URI=http://localhost:8001/api/auth/google/callback
```

Os valores default de `GOOGLE_AUTH_URL`, `GOOGLE_TOKEN_URL`, `GOOGLE_CERTS_URL`
e `GOOGLE_ISSUER` são os endpoints oficiais e raramente precisam mudar (mantê-los
no `.env` permite trocar por um ambiente de teste quando quiser).

> **Segurança:** `GOOGLE_CLIENT_SECRET` nunca deve ir para o frontend, nem para
> logs, nem para o repositório. É lido apenas no backend, do `Settings`.

---

## 4. Modelo de dados e migration

O usuário criado via Google **não tem senha** local. Por isso:

- `users.hashed_password` deixou de ser `NOT NULL` (agora aceita `NULL`).
- Novos campos opcionais:
  - `oauth_provider` (`VARCHAR(32)`) — guarda `'google'`.
  - `google_id` (`VARCHAR(255)`) — guarda o `sub` do Google.

Migration: `migrations/versions/c1d2e3f4a5b6_google_oauth_social_login.py`.

- Em SQLite (que não suporta `ALTER COLUMN`), usa `op.batch_alter_table`
  (recria a tabela). Em outros bancos, altera in-place.
- Verifique com:
  ```bash
  alembic upgrade head
  alembic downgrade base   # para testar o rollback
  ```

Arquivos:
- `app/models/user.py` — campos novos + `hashed_password` nullable.
- `app/repositories/user_repository.py` — `create()` aceita `hashed_password=None`,
  `oauth_provider`, `google_id`, `is_verified`.

---

## 5. Schemas (Pydantic) — `app/schemas/google.py`

- **`GoogleAuthUrlResponse`**: `{authorization_url, state}` — o que o frontend
  usa para redirecionar o navegador.
- **`GoogleLoginRequest`**: recebe **exatamente um** de `code` ou `id_token`.
  - Se vier `code`, o `state` é obrigatório (validador `@model_validator`).
  - `extra='forbid'` (consistente com os demais schemas do projeto).

---

## 6. Exceções — `app/core/exceptions.py`

| Exceção | HTTP | `code` | Quando |
|---|---|---|---|
| `GoogleLoginDisabledError` | 403 | `GOOGLE_LOGIN_DISABLED` | Login Google desligado via `GOOGLE_LOGIN_ENABLED`. |
| `InvalidGoogleTokenError` | 400 | `INVALID_GOOGLE_TOKEN` | `code`/`id_token`/`state` inválido, expirado, e-mail não verificado, `kid` desconhecido. |
| `GoogleAuthError` | 502 | `GOOGLE_AUTH_ERROR` | Falha de rede/HTTP com as APIs do Google. |

Todas herdam de `AppError` e são renderizadas pelo `app/core/error_handlers.py`
no mesmo formato de erro do resto da API.

---

## 7. O serviço — `app/services/google_auth_service.py`

É o coração da feature. Funções principais:

### `create_google_state() -> str`
Gera o token `state` (CSRF): um JWT curto (10 min) assinado com o `SECRET_KEY`,
com `type='google_state'`, `nonce` aleatório e `iat`/`exp`.

### `verify_google_state(state) -> None`
Valida assinatura, expiração e `type`. Falhou → `InvalidGoogleTokenError`.

> Por que o `state`? Sem ele, um atacante poderia forjar o callback e "logar"
> com a conta de outra pessoa (login CSRF). O `state` é uma senha combinada
> entre o passo 1 (gerar URL) e o passo 5 (enviar o código).

### `build_authorization_url(state) -> str`
Monta a URL da tela de consentimento com `client_id`, `redirect_uri`,
`response_type=code`, `scope="openid email profile"`, `access_type=online`,
`prompt=select_account` e o `state`.

### `class GoogleIdentityProvider`
Cliente HTTP (via `httpx.AsyncClient`) que conversa com o Google.

- **`exchange_code_for_id_token(code)`** — `POST` no `GOOGLE_TOKEN_URL` com
  `code`, `client_id`, `client_secret`, `redirect_uri` e
  `grant_type=authorization_code`. Resposta não-200 → `InvalidGoogleTokenError`;
  erro de rede (`httpx.HTTPError`) → `GoogleAuthError`.
- **`verify_id_token(id_token)`** — o passo de **confiança zero**:
  1. Lê o header do JWT (`kid`, `alg`). Exige `alg == 'RS256'`.
  2. Busca o JWKS do Google (`GOOGLE_CERTS_URL`), com **cache de 5 minutos**
     para não bater no Google a cada login.
  3. Acha a chave pública cujo `kid` bate com o do token. Não achou →
     `InvalidGoogleTokenError`.
  4. `jwt.decode` verificando **assinatura**, `audience` (= `client_id`),
     `issuer` (= `GOOGLE_ISSUER`), expiração e claims obrigatórias
     (`sub`, `email`, `exp`, `iss`, `aud`).
  5. Exige `email_verified == true` e e-mail presente. Caso contrário →
     `InvalidGoogleTokenError`.
- **`aclose()`** — fecha o cliente HTTP (só se foi criado internamente).

> Por que verificar tudo isso? Porque o `id_token` é um **JWT assinado** — se
> você apenas decodificar sem validar, qualquer um pode forjar um token com o
> e-mail que quiser. A verificação da assinatura garante que o Google de fato
> emitiu aquele token para o seu `client_id`.

### `google_login(db, *, code, id_token, state, client_ip, provider) -> Token`
Orquestra o fluxo completo:

1. Se `GOOGLE_LOGIN_ENABLED` for `false` → `GoogleLoginDisabledError`.
2. Se o login é por `code`: valida o `state` e troca o código pelo `id_token`.
3. Valida o `id_token` (recebido do Google ou enviado direto pelo frontend).
4. Busca o usuário por **e-mail**:
   - **Não existe** → cria com `oauth_provider='google'`, `google_id=sub`,
     `is_verified=True`, `hashed_password=None` e `full_name` do Google.
   - **Existe** → `_link_oauth_identity`: garante `is_verified=True`, preenche
     `google_id`/`oauth_provider` se ainda não estiverem e preenche o
     `full_name` se estiver vazio. **Nunca duplica** o registro.
5. Registra eventos de segurança e retorna o par de tokens da aplicação via
   `auth_service.create_token_pair` — **o mesmo par** do login por e-mail/senha.

---

## 8. Endpoints — `app/api/routers/google_auth.py`

Registrados em `app/api/router.py` (prefixo global `/api`):

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| `GET` | `/api/auth/google/url` | — | `GoogleAuthUrlResponse` (`authorization_url`, `state`) |
| `POST` | `/api/auth/google/callback` | `{code, state}` **ou** `{id_token}` | `Token` (`access_token`, `refresh_token`, `token_type`) |

### Como o frontend usa isso (resumo)

```ts
// 1. buscar a URL de autorização
const { authorization_url, state } = await fetch('/api/auth/google/url').then(r => r.json());

// 2. redirecionar o navegador (top-level, não fetch)
window.location.href = authorization_url;

// 3. o Google volta para redirect_uri?code=X&state=Y.
//    Em SPAs, o redirect_uri aponta para a própria página, que lê a query string
//    e chama o backend:
const params = new URLSearchParams(window.location.search);
const res = await fetch('/api/auth/google/callback', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ code: params.get('code'), state: params.get('state') }),
});
const { access_token, refresh_token } = await res.json();
```

O `state` retornado no passo 1 é o **mesmo** que o Google devolve no passo 3 e
que você reenvia no passo 4. Se bater com o que o servidor assinou, ok.

---

## 9. Como as contas são criadas/associadas

- **E-mail novo** → conta criada automaticamente, **verificada** (o Google já
  confirmou o e-mail), sem senha. O usuário não passa por e-mail de confirmação.
- **E-mail já cadastrado** → o login é feito **na conta existente**. O `google_id`
  é gravado para vínculo futuro. Se a conta já tinha senha, a senha continua
  valendo (o usuário passa a ter dois jeitos de entrar: senha ou Google).
- A chave de associação é o **e-mail** (como especificado na issue). Não há
  suporte a múltiplos provedores por conta nem `google_id` como chave única —
  isso está **fora de escopo**.

> Detalhe de segurança: um usuário criado só via Google (`hashed_password=NULL`)
> **não consegue** fazer login por senha. O `authenticate_user` foi ajustado em
> `app/services/user_service.py` para tratar `hashed_password is None` como
> falha de credenciais (em vez de quebrar).

---

## 10. Eventos de segurança

A cada tentativa são emitidos eventos JSON estruturados (ver
`app/core/security_logger.py` e `docs/security-events.md`):

- `GOOGLE_LOGIN_SUCCESS` — login bem-sucedido (`INFO`, com `user_id` e IP).
- `GOOGLE_LOGIN_FAILED` — falha (`WARNING`), com `reason`:
  - `disabled` — feature desligada.
  - `invalid_token` — código/token/state inválido.
  - `upstream_error` — problema com as APIs do Google.

Nunca são logados segredos, tokens completos ou senhas.

---

## 11. Testes — `tests/test_google_auth.py`

Nenhuma chamada real ao Google é feita nos testes. Duas estratégias:

### a) Provider fake (para o fluxo HTTP da API)
`FakeGoogleProvider` substitui `GoogleIdentityProvider` via
`monkeypatch.setattr('app.services.google_auth_service.GoogleIdentityProvider', ...)`.
Cobre:

- `GET /url` retorna a URL de consentimento correta (parâmetros conferidos) e o
  `state` assinado decodificável.
- `GET /url` com feature desligada → 403.
- Login de **novo usuário** → conta criada verificada, sem senha, com
  `google_id`/`oauth_provider` (checado no banco).
- Login de **usuário existente** → vínculo sem duplicar (1 registro).
- Usuário Google **não** consegue logar por senha.
- Login direto por `id_token`.
- `code` inválido, `id_token` inválido, `state` forjado → 400 `INVALID_GOOGLE_TOKEN`.
- Feature desligada → 403 `GOOGLE_LOGIN_DISABLED`.
- Validação do schema: sem `code`/`id_token`, com os dois, `code` sem `state` → 422.
- Eventos de segurança `GOOGLE_LOGIN_SUCCESS`/`GOOGLE_LOGIN_FAILED` emitidos.

### b) Testes unitários do `GoogleIdentityProvider` (criptografia real)
Usam `httpx.MockTransport` + chaves RSA reais geradas em memória:

- `verify_id_token` aceita um token RS256 válido assinado pela chave do "JWKS".
- Rejeita token **expirado**, **audience errada**, **issuer errado**,
  `email_verified=false` e e-mail vazio.
- Rejeita token com `kid` desconhecido.
- `exchange_code_for_id_token` faz o `POST` com os parâmetros corretos e retorna
  o `id_token` do corpo.
- Resposta não-200 → `InvalidGoogleTokenError`.
- Erro de rede no exchange e no fetch de certs → `GoogleAuthError`.

Para rodar:

```bash
uv run pytest tests/test_google_auth.py -v
uv run task test        # suíte completa (353 testes)
uv run task lint        # ruff
```

---

## 12. Checklist de segurança (o que nunca fazer)

- ❌ Enviar o `GOOGLE_CLIENT_SECRET` para o frontend.
- ❌ Aceitar `id_token` sem validar assinatura (`get_unverified_header`/decode
  sem `verify`).
- ❌ Validar o `id_token` sem checar `audience` (outra aplicação poderia emitir
  para o mesmo e-mail).
- ❌ Usar o login Google com `state` opcional (vulnerável a login CSRF).
- ✅ Confiar na assinatura do Google e no `email_verified` antes de criar a conta.
- ✅ Devolver os tokens da aplicação (nunca o `id_token` do Google).
- ✅ Tratar falhas de rede com o Google como erro de infraestrutura (502), não
  como credencial inválida.

---

## 13. FAQ / pegadinhas comuns

- **"O Google me deu `redirect_uri_mismatch`"** → o `GOOGLE_REDIRECT_URI` não é
  exatamente igual a um dos *Authorized redirect URIs* cadastrados no console.
  Bate caractere por caractere (incluindo porta e caminho).
- **"O código expirou"** → o authorization code é de uso único e de vida curta
  (alguns minutos). Sempre troque logo.
- **"E o refresh token do Google?"** → neste fluxo não precisamos dele: só usamos
  o `id_token` para autenticar. O refresh token da **nossa** aplicação é gerado
  por `create_token_pair`, como em qualquer login.
- **"E se o usuário desativar o e-mail `email_verified`?"** → o login é negado
  com `INVALID_GOOGLE_TOKEN`. A conta só entra com e-mail confirmado pelo Google.
- **"Posso usar só o `id_token` sem redirect?"** → sim: o frontend (Google
  Identity Services) pode obter o `id_token` e enviá-lo direto no
  `POST /callback` com `{id_token}`.
