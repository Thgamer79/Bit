# BotGigas 2026 — Changelog de Reconstrução

## Resumo das Adaptações

Este projeto foi reconstruído mantendo **100% da estrutura original** do bot,
aplicando apenas as adaptações necessárias para funcionar corretamente em 2026.

---

## Arquivos Modificados

### `requirements.txt`
- `pyTelegramBotAPI` atualizado para `>=4.22.0`
- `requests>=2.32.0` (compatível com urllib3>=2.2)
- `urllib3>=2.2.0` (substitui parâmetro `method_whitelist` por `allowed_methods`)
- `flask>=3.1.0` (Flask 3.x — API estável)
- `PyJWT>=2.9.0` — **crítico**: versões antigas são incompatíveis com Python 3.12+
- `Werkzeug>=3.1.0` (dependência do Flask 3.x)
- `Pillow>=11.0.0` (suporte a Python 3.12/3.13)
- `qrcode>=8.0`

### `config.py`
- **User-Agent atualizado**: Chrome 136 fake → `Chrome/124.0.6367.82 Mobile (SM-S928B, Android 14)`
- Estrutura idêntica, apenas UA e comentários atualizados

### `api_client.py`
- **User-Agent**: `SM-S928B Android 14 Chrome/124`
- **sec-ch-ua**: atualizado para Chrome 124
- **sec-ch-ua-mobile**: `?1` (mobile)
- **sec-ch-ua-platform**: `"Android"`
- Import de `jwt` tornado condicional (não quebra se PyJWT não instalado)

### `api_vivo.py`
- **PyJWT>=2.9**: `jwt.decode()` agora exige `algorithms=["HS256","RS256"]` mesmo com `verify_signature=False`
  — corrigido via `_decode_jwt_safe()`
- **okhttp**: `4.11.0` → `4.12.0`
- **osVersion** no context: `"13"` → `"14"` (Android 14)
- `session.verify = False` explícito para urllib3>=2.2

### `api_tim.py`
- Mesmas correções de PyJWT>=2.9 via `_decode_jwt_safe()`
- **okhttp**: `4.11.0` → `4.12.0`
- **osVersion**: `"13"` → `"14"`
- JWT inicial TIM separado em constante nomeada

### `config_vivo.py`
- **okhttp**: `4.11.0` → `4.12.0` no `MOBILE_HEADERS_BASE`
- `Dart/3.6 (dart:io)` mantido (versão atual do Flutter SDK)

### `bot_main.py`
- `DeprecationWarning` de urllib3/requests suprimido
- Limite de restarts (`max_restarts=50`) para evitar loop infinito em falhas persistentes
- **Recria BotSession** a cada restart (limpa estado corrompido)

### `utils.py`
- `allowed_methods=["GET","POST"]` — parâmetro correto para `urllib3>=2.0`
  (`method_whitelist` foi removido no urllib3>=2.0)
- Timeouts ajustados: `CONNECT_TIMEOUT=15`, `READ_TIMEOUT=30`

### `webhook_server.py`
- `request.get_json(silent=True)` — evita raise em body JSON inválido (Flask 3.x)
- Thread de processamento de pagamento com `daemon=True` correto
- `use_reloader=False` no Flask run (obrigatório em thread secundária no Flask 3.x)

### `pix_payment.py`
- `date_of_expiration` no formato ISO 8601 com timezone (`-03:00`)
  — formato exigido pelo Mercado Pago SDK 2.2.x
- `float(amount)` explícito no `transaction_amount`

### `squarecloud.config`
- `AUTORESTART=true` (era `false`) — reinício automático em produção

---

## Arquivos Não Modificados (estrutura preservada)
- `bot_core.py` — apenas warnings filters adicionados no topo
- `database.py` — compatível com Python 3.12, SQLite3 nativo
- `admin.py`, `revenda.py`, `states.py`, `stats.py`
- `mensagem_start.py`, `config_tim.py`

---

## Compatibilidade
- **Python**: 3.10 / 3.11 / 3.12 / 3.13
- **SquareCloud**: versão `recommended` (Python 3.11+)
- **PyTelegramBotAPI**: 4.22+ (polling e webhook estáveis)
- **Flask**: 3.1.x
- **Mercado Pago SDK**: 2.2.x
