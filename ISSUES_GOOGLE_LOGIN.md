# ISSUES_GOOGLE_LOGIN.md

## Titulo: [EPIC-3][AUTH] Implementar Login com Google OAuth 2.0

### Descrição:
Implementar o fluxo de autenticação e login social utilizando Google OAuth 2.0 (OpenID Connect / Google Sign-In). A funcionalidade deve permitir que usuários realizem login/cadastro simplificado via conta Google, gerando os tokens JWT de acesso/refresh da aplicação (mantendo a consistência do sistema de autenticação existente). Se o e-mail retornado pelo Google já existir no banco de dados, a conta deve ser associada/autenticada; caso não exista, um novo perfil de usuário deve ser criado automaticamente (marcado como verificado).

---

### Tarefas:

- [x] **Configuração e Variáveis de Ambiente (`app/core/config.py`)**
  - [x] Adicionar credenciais do Google OAuth no `Settings` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`).
  - [x] Adicionar flags de ativação do login social (ex: `GOOGLE_LOGIN_ENABLED`).
  - [x] Atualizar `.env.example` e `.env.template` com as variáveis necessárias.

- [x] **Modelos de Dados e Banco (`app/models/user.py` / `migrations`)**
  - [x] Garantir suporte para usuários criados via OAuth (ex: `hashed_password` nula ou marcada como social login, campo `oauth_provider` / `google_id` opcional).
  - [x] Criar migration Alembic para ajustar a tabela `users` caso novos campos de provedor OAuth sejam adicionados.

- [x] **Schemas Pydantic (`app/schemas/auth.py` / `app/schemas/google.py`)**
  - [x] Criar schema para requisição do callback/token do Google (`GoogleLoginRequest` contendo `code` ou `id_token`).
  - [x] Criar schemas de resposta para URL de autorização OAuth e resposta de login.

- [x] **Serviço de Autenticação Google (`app/services/google_auth_service.py` ou `app/services/auth_service.py`)**
  - [x] Implementar função para gerar a URL de autorização do Google OAuth com parâmetros `state` (proteção CSRF) e escopos (`openid`, `email`, `profile`).
  - [x] Implementar a troca do `code` de autorização pelo token de acesso/ID Token junto à API do Google (utilizando `httpx` ou biblioteca oficial).
  - [x] Implementar a validação e decodificação do `id_token` obtido do Google para extrair `email`, `name`, `sub` (Google User ID) e status de verificação.
  - [x] Implementar lógica de busca ou criação do usuário no banco:
    - [x] Se o e-mail existir: associar/autenticar e garantir que `is_verified` seja `True`.
    - [x] Se o e-mail não existir: criar novo usuário com `is_verified=True` e sem necessidade de senha local inicial.
  - [x] Gerar e retornar o par de tokens JWT da aplicação (`access_token` e `refresh_token`) reaproveitando `auth_service.create_token_pair`.

- [x] **Endpoints HTTP (`app/api/routers/auth.py` ou `app/api/routers/google_auth.py`)**
  - [x] Implementar rota `GET /auth/google/url`: Retorna a URL de redirecionamento para a tela de consentimento do Google.
  - [x] Implementar rota `POST /auth/google/callback` (ou `POST /auth/google/login`): Recebe o `code` ou `id_token`, processa a autenticação e retorna os tokens JWT da aplicação (`Token`).
  - [x] Registrar novas rotas no router principal (`app/api/router.py`).

- [x] **Tratamento de Exceções e Segurança (`app/core/exceptions.py` / `app/core/error_handlers.py`)**
  - [x] Criar exceções customizadas para falhas na autenticação Google (ex: `GoogleAuthError`, `InvalidGoogleTokenError`).
  - [x] Garantir log de eventos de segurança via `log_security_event` para logins via Google (`GOOGLE_LOGIN_SUCCESS`, `GOOGLE_LOGIN_FAILED`).

- [x] **Testes Automatizados (`tests/test_google_auth.py`)**
  - [x] Criar mocks para chamadas externas HTTP à API do Google (troca de token e verificação do ID Token).
  - [x] Testar fluxo completo de login via Google para novo usuário (criação automática de conta).
  - [x] Testar fluxo completo de login via Google para usuário pré-existente (vinculação de conta).
  - [x] Testar tratamento de erro para `code` ou `id_token` inválido/expirado.
  - [x] Testar comportamento quando o login via Google estiver desativado nas configurações.

---

### Critérios de Aceite:

- [x] Usuários conseguem realizar login/cadastro utilizando suas contas Google via fluxo OAuth 2.0 / OpenID Connect.
- [x] Usuários autenticados via Google recebem um par de tokens JWT (`access_token` e `refresh_token`) idêntico ao fluxo de login tradicional por e-mail/senha.
- [x] Se o e-mail da conta Google já existir no sistema, o login é realizado na conta existente sem duplicar registros.
- [x] Novos usuários criados via Google têm o e-mail marcado automaticamente como verificado (`is_verified = True`).
- [x] Requisições externas à API do Google são totalmente mockadas nos testes automatizados, garantindo execução rápida e isolada.
- [x] Credenciais e URLs do OAuth são totalmente configuráveis via variáveis de ambiente/Settings sem alteração no código fonte.

---

### Fora de Escopo:

- Suporte a outros provedores de login social (ex: GitHub, Facebook, Apple) — a ser tratado em issues dedicadas.
- Vinculação manual de múltiplos provedores OAuth a uma mesma conta a partir de um painel de configurações do usuário.
- Sincronização contínua de fotos de perfil ou dados cadastrais atualizados no Google após o login inicial.

---

### Dependências:
- `[EPIC-3][AUTH] Implementar login com JWT.`

---

### Labels:
- `auth`, `feature`, `security`, `oauth`
