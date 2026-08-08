# MFA Readiness

Preparação estrutural para autenticação multifator (MFA). Nenhum fator
adicional é implementado funcionalmente — esta issue garante apenas que a
evolução para MFA não exigirá refatoração estrutural dos fluxos de login.

## Modelos preparados

### `User` (`app/models/user.py`)

- `mfa_enabled` (`Boolean`, default `False`) — indica se o usuário possui MFA
  ativo.
- `mfa_type` (`String(16)`, nullable) — fator preferido/primário (ex.:
  `"totp"`, `"sms"`, `"email"`), sem lógica ainda.
- `mfa_methods` — relacionamento `one-to-many` com `MfaMethod`.

### `MfaMethod` (`app/models/mfa_method.py`)

Suporta múltiplos fatores por usuário:

| Campo        | Tipo       | Propósito                                        |
| ------------ | ---------- | ------------------------------------------------ |
| `id`         | `String(36)` | Chave primária (UUID).                          |
| `user_id`    | `String(36)` | FK para `users.id` (CASCADE).                    |
| `type`       | `String(16)` | Tipo do fator (`totp`, `sms`, `email`, ...).     |
| `secret`     | `String(512)` | Segredo específico do fator (ex.: seed TOTP).   |
| `metadata`   | `JSON`     | Dados extras do fator, sem acoplar o schema a um método (atributo Python `data`, coluna `metadata`). |
| `is_active`  | `Boolean`  | Fator ativo/verificado.                           |
| `created_at` | `DateTime` | Data de registro.                                 |

Índices: `(user_id)` e `(user_id, type)`.

## Ponto de extensão no fluxo de login

Marcado com `# MFA_HOOK` em `app/services/user_service.py` →
`authenticate_user`: após validar a senha e **antes** de emitir o access
token final. É ali que entraria a verificação do segundo fator.

## Estratégia futura: token intermediário

Quando MFA for ativado, o fluxo planejado é:

1. Senha validada → emitir um **token intermediário de curta duração** (ex.:
   2–5 minutos) em vez do access token final, marcando "password verificado".
2. O cliente envia o desafio MFA (ex.: código TOTP) acompanhado desse token.
3. Desafio validado → emitir o par de tokens final (access + refresh).

Isso mantém o access token final com TTL curto e evita emitir tokens antes
da verificação do segundo fator.

## Claims do JWT

Convenção pretendida para o claim `amr` (authentication methods reference):

- Senha apenas: `"amr": ["pwd"]`.
- Senha + MFA: `"amr": ["pwd", "mfa"]`.

Não implementado nesta issue; apenas a convenção fica documentada para
expansão futura da política de claims.

## Fatores planejados (futuro)

1. **TOTP** — primeira implementação recomendada (não requer infraestrutura
   externa, apenas a biblioteca `pyotp`/equivalente).
2. SMS — requer provedor de SMS.
3. E-mail de confirmação em duas etapas — pode reutilizar a infraestrutura de
   tokens opacos já existente.

## Próximos passos (fora do escopo)

- Implementar o fator TOTP (geração do segredo, QR code, validação de código).
- Endpoints de ativação/desativação de MFA pelo usuário.
- Fluxo de recuperação em caso de perda do segundo fator (backup codes).
