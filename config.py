"""
Configurações do Bot - Reconstrução 2026
Adaptações: User-Agent 2026, Chrome 124, compatibilidade Python 3.12+
"""

# ========================================
# CONFIGURAÇÕES DE REVENDA
# ========================================

RESELLER_CREDIT_PRICES = [
    {"credits": 5,  "price": 35.00},
    {"credits": 10, "price": 50.00},
    {"credits": 17, "price": 70.00},
    {"credits": 24, "price": 80.00},
    {"credits": 35, "price": 100.00},
    {"credits": 50, "price": 130.00},
]

RESELLER_MIN_CREDITS = 1
RESELLER_ENABLE_CUSTOM_MP = True

BOT_USERNAME = "rOxziN_bot"

# ==========================================
# TOKENS / API
# ==========================================

BOT_TOKEN = "8053253244:AAGflN9uTMD_cV4gU_oJ08EEFQj8_HyjTn4"

API_BASE_URL    = "https://api.prezaofree.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72"
API_VERSION     = "3.0.11"
API_CHANNEL     = "WEB"
API_ARTEMIS_CHANNEL_UUID = "cfree-b22d-4079-bca5-96359b6b1f57"
API_ACCESS_TOKEN         = "4e82abb4-2718-4d65-bcd4-c4e147c3404f"

# 2026: User-Agent Chrome 124 (Android 14, SM-S928B) — mais recente que o Chrome 136 falso anterior
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.82 Mobile Safari/537.36"
)

# IDs das Campanhas Claro
CAMPAIGN_IDS = [
    "2b25a088-84ea-11ef-9082-0e639a16be05",
    "ce46818d-e31a-11ef-bb8e-0680334bb059",
    "f9077545-165c-4184-825a-a57459c131dc",
    "dcc45968-df87-403b-8c75-a8c021ec4c8c",
]

# ==========================================
# CONFIGURAÇÕES DO SISTEMA
# ==========================================

MAX_THREADS     = 15
DAILY_LINK_LIMIT = False
MAINTENANCE_MODE = False
DB_FILE         = 'bot_data.db'
USERS_FILE      = 'users.json'
STATS_FILE      = 'stats.json'

AUTO_COLLECT_TIME     = "5:30"
AUTO_COLLECT_TIMEZONE = "America/Sao_Paulo"

# ==========================================
# SEGURANÇA
# ==========================================

ADMIN_PASSWORD     = "15359Vs@"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_COOLDOWN     = 300    # segundos
SESSION_TIMEOUT    = 3600   # segundos
BUTTON_COOLDOWN    = 2      # segundos (anti-autoclick)
CAMPAIGN_COOLDOWN  = 5      # segundos entre campanhas

# ==========================================
# MENU / INTERFACE
# ==========================================

MENU_TYPES = {
    "main": [
        ["🚀 Começar Campanhas", "💎 Ver Moedas"],
        ["🎁 Pacotes Disponíveis", "🤖 Coleta Automática"],
        ["📊 Status", "💰 Pagamento"],
    ],
    "pix": [
        ["💳 Pagar R$ {PIX_PRICE}", "📱 Status da Assinatura"],
        ["📋 Histórico", "🔙 Voltar ao Menu"],
    ],
    "auto_collect": [
        ["✅ Ativar Coleta", "❌ Desativar Coleta"],
        ["🔙 Voltar ao Menu"],
    ],
    "cancel": [["🚫 Cancelar"]],
}

EMOJI_PACK = {
    'success':     '✅',
    'error':       '❌',
    'loading':     '🔄',
    'coins':       '💎',
    'packages':    '🎁',
    'campaigns':   '🚀',
    'warning':     '⚠️',
    'stop':        '🚫',
    'back':        '🔙',
    'home':        '🏠',
    'login':       '🔑',
    'phone':       '📱',
    'message':     '💌',
    'robot':       '🤖',
    'fire':        '🔥',
    'celebration': '🎉',
    'sad':         '😔',
    'chart':       '📊',
}

MESSAGES = {
    'welcome':                '🎉 Bem-vindo ao bot da claro prezao!',
    'maintenance':            '🛠 Bot em manutenção. Tente depois! 💤',
    'error_generic':          '😔 Oops! Algo deu ruim... Tenta de novo?',
    'login_success':          '🎉 Login feito! Agora é só diversão!',
    'campaign_start':         '🚀 Partiu pegar moedas? Bora lá!',
    'campaign_complete':      '🏆 Missão cumprida, chefe!',
    'auto_collect_activated':   '🤖 Modo automático on! Relaxa que eu cuido das paradas!',
    'auto_collect_deactivated': '🤖 Modo automático off! Tu que manda agora!',
    'phone_required':         'Digite seu celular (ex: 16991123450):',
    'pin_required':           '💌 Digite o código recebido:',
    'phone_invalid':          '⚠️ Número inválido ({}). Deve ter 11 dígitos. Digite novamente:',
    'phone_sending':          '📱 Enviando código para {}...',
    'subscription_expired':   '⚠️ Sua assinatura expirou!\n📅 E ganhe {} dias de acesso\n\nClique em \'Pagamento\' para renovar',
    'trial_welcome':          '🎉 Login realizado com sucesso!\n\n🎁 Você ganhou {} dias grátis para testar!',
    'too_many_clicks':        '⚠️ Muitos cliques detectados. Aguarde um momento...',
    'proxy_connecting':       '🔒 Aguarde, conectando a um ambiente seguro...',
    'proxy_connected':        '✅ Conexão segura estabelecida! IP: {} - {}',
    'proxy_failed':           '⚠️ Não foi possível conectar ao proxy. Usando conexão normal.',
    'proxy_changed':          '✅ IP do proxy atualizado! Novo IP: {} - {}',
    'proxy_not_changed':      '⚠️ Não foi possível atualizar o IP do proxy. Mantendo o IP atual: {}',
}

# ==========================================
# PERFORMANCE
# ==========================================

REQUEST_TIMEOUT = 20
RETRY_ATTEMPTS  = 1
RETRY_DELAY     = 5

CACHE_ENABLED  = True
CACHE_TTL      = 300
CACHE_MAX_SIZE = 1000

# ==========================================
# LOGGING
# ==========================================

LOG_LEVEL  = 'INFO'
LOG_FILE   = 'bot.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ==========================================
# PAGAMENTO PIX
# ==========================================

MERCADO_PAGO_ACCESS_TOKEN = "APP_USR-5412847209423784-050615-afb9848bcbdd378a0edc6321dc648fb3-30033708"

PIX_PRICE            = 20.00
PIX_ACTUAL_PRICE     = 20.00
PIX_VALIDITY_MINUTES = 15
PIX_BUTTON_TEXT      = "✅ Verificar"
PIX_RENEWAL_MIN_DAYS = 7

SUBSCRIPTION_DAYS    = 30
TRIAL_DAYS           = 1
SUBSCRIPTION_PAGING  = 5

# ==========================================
# PROXY (Bright Data / ISP)
# ==========================================

PROXY_ENABLED      = True
PROXY_HOST         = "brd.superproxy.io"
PROXY_PORT         = 33335
PROXY_USER         = "brd-customer-hl_637dc23c-zone-isp_proxy1-country-br"
PROXY_PASS         = "85g1r9d7u156"
PROXY_MAX_ATTEMPTS = 3
PROXY_TIMEOUT      = 10

# ==========================================
# OPERADORAS
# ==========================================

OPERATORS = {
    "claro": {
        "name":  "Claro",
        "emoji": "🔵",
        "api_base_url":            "https://api.prezaofree.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72",
        "api_version":             "3.0.11",
        "api_channel":             "WEB",
        "api_artemis_channel_uuid": "cfree-b22d-4079-bca5-96359b6b1f57",
        "api_access_token":        "4e82abb4-2718-4d65-bcd4-c4e147c3404f",
    },
    "vivo": {
        "name":  "Vivo",
        "emoji": "🟢",
        "api_base_url":            "https://api.appvivopontos.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72",
        "api_version":             "2.5.95",
        "api_channel":             "ANDROID",
        "api_artemis_channel_uuid": "vivo-pontos-10ad-400c-88d9-fc32e2371e36",
        "api_access_token":        "4e82abb4-2718-4d65-bcd4-c4e147c3404f",
        "mobile_campaign_endpoint":     "https://api.appvivopontos.com.br/adserver/campaign/v3/99f9c90a-b13e-419a-b53d-f47f6f2dea35",
        "respescagem_campaign_endpoint": "https://api.appvivopontos.com.br/adserver/campaign/v3/dbf70686-e31a-11ef-bb8e-0680334bb059",
        "withdraw_endpoint":       "https://api.appvivopontos.com.br/withdraw",
        # 2026: token inicial Vivo – renegociado quando expirar no fluxo de login
        "initial_token": (
            "eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJBTkRST0lEIiwiWC1UT0tFTi1WRVJTSU9OIjoiMS4wLjAiL"
            "CJYLVVTRVItSUQiOiJlNjg5NDcxZGJlOTI2NjRmIiwiWC1XQUxMRVQtSUQiOiI2NmE1OTA1MTdhODc1IiwiZXhwI"
            "joxNzU2ODE3MzY0LCJpYXQiOjE3NDkwNDEzNjQsImlzcyI6ImNZNzhuM2hldWt5d2E0aHpQdThYeFBxTk1YaE1DQjI"
            "0Iiwic3ViIjoiZTY4OTQ3MWRiZTkyNjY0ZiJ9.gdkCFWBUtTf3m2a09P9n_mnkqyxzCIR0WNO_DOTsXrM"
        ),
    },
    "tim": {
        "name":  "TIM",
        "emoji": "🟡",
        # 2026: endpoint TIM – atualizar aqui quando configurar
        "api_base_url":            "https://api.tim.com.br/endpoint",
        "api_version":             "3.0.11",
        "api_channel":             "WEB",
        "api_artemis_channel_uuid": "tim-channel-uuid",
        "api_access_token":        "tim-access-token",
    },
}

DEFAULT_OPERATOR = "claro"
