# ============= CONFIGURAÇÕES DO BOT VIVO PONTOS - 2026 =============

WEBHOOK_SECRET = "vivo_bot_webhook_secret_2026"

# API VIVO PONTOS (NÃO ALTERAR)
API_BASE_URL             = "https://api.appvivopontos.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72"
API_ACCESS_TOKEN         = "4e82abb4-2718-4d65-bcd4-c4e147c3404f"
API_ARTEMIS_CHANNEL_UUID = "vivo-pontos-10ad-400c-88d9-fc32e2371e36"

# TOKEN INICIAL VIVO
# 2026: token com exp longo; renovado automaticamente no fluxo de login
INITIAL_TOKEN = (
    "eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJBTkRST0lEIiwiWC1UT0tFTi1WRVJTSU9OIjoiMS4wLjAiLCJYLVVTRVItSUQiOiJlNjg5NDcxZGJlOTI2NjRmIiwiWC1XQUxMRVQtSUQiOiI2NmE1OTA1MTdhODc1IiwiZXhwIjoxNzU2ODE3MzY0LCJpYXQiOjE3NDkwNDEzNjQsImlzcyI6ImNZNzhuM2hldWt5d2E0aHpQdThYeFBxTk1YaE1DQjI0Iiwic3ViIjoiZTY4OTQ3MWRiZTkyNjY0ZiJ9.gdkCFWBUtTf3m2a09P9n_mnkqyxzCIR0WNO_DOTsXrM"
)

# ENDPOINTS DA API (NÃO ALTERAR)
MOBILE_CAMPAIGN_ENDPOINT      = "https://api.appvivopontos.com.br/adserver/campaign/v3/99f9c90a-b13e-419a-b53d-f47f6f2dea35"
RESPESCAGEM_CAMPAIGN_ENDPOINT = "https://api.appvivopontos.com.br/adserver/campaign/v3/dbf70686-e31a-11ef-bb8e-0680334bb059"
WITHDRAW_ENDPOINT             = "https://api.appvivopontos.com.br/withdraw"

# HEADERS DA API
# 2026: okhttp/4.12.0 (versão atual do OkHttp no app Vivo 3.1.02)
MOBILE_HEADERS_BASE = {
    "x-access-token":         API_ACCESS_TOKEN,
    "x-channel":              "ANDROID",
    "x-app-version":          "2.5.95",
    "x-artemis-channel-uuid": API_ARTEMIS_CHANNEL_UUID,
    "content-type":           "application/json; charset=UTF-8",
    "host":                   "api.appvivopontos.com.br",
    "connection":             "Keep-Alive",
    "accept-encoding":        "gzip",
    "user-agent":             "okhttp/4.12.0",
}

# 2026: Dart/3.6 (versão atual do Flutter SDK no app Vivo)
AUTH_HEADERS_BASE = {
    "user-agent":      "Dart/3.6 (dart:io)",
    "x-channel":       "ANDROID",
    "accept-encoding": "gzip",
    "host":            "api.appvivopontos.com.br",
    "content-type":    "application/json",
    "x-app-version":   "2.5.95",
}

# DELAYS DE PROCESSAMENTO DE VÍDEO
VIDEO_PROCESSING_DELAYS = {
    "optimized_delay":    0.01,
    "between_videos":     0.5,
    "between_campaigns":  1.0,
}
