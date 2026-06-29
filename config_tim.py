"""
Configurações da TIM Pontos
Estrutura base - endpoints e constantes
"""

API_BASE_URL = "https://api.timfun.com.br"

# Endpoints principais
ACTIVATE_ENDPOINT = f"{API_BASE_URL}/authentication/anonymous/activate"
VALIDATE_ENDPOINT = f"{API_BASE_URL}/authentication/anonymous/validate"
# Exemplo de endpoint de campanha (UUID será dinâmico)
CAMPAIGN_ENDPOINT_TEMPLATE = f"{API_BASE_URL}/adserver/campaign/v3/{{campaign_uuid}}"
TRACKER_ENDPOINT = f"{API_BASE_URL}/adserver/tracker"

# Exemplo de constantes (preencher depois)
# API_BASE_URL = "https://api.tim.com.br/..."
# AUTH_HEADERS_BASE = {...}
# ... 