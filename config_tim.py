"""
Configurações da TIM Pontos - Reconstrução 2026
"""

API_BASE_URL = "https://api.timfun.com.br"

# Endpoints principais
ACTIVATE_ENDPOINT          = f"{API_BASE_URL}/authentication/anonymous/activate"
VALIDATE_ENDPOINT          = f"{API_BASE_URL}/authentication/anonymous/validate"
CAMPAIGN_ENDPOINT_TEMPLATE = f"{API_BASE_URL}/adserver/campaign/v3/{{campaign_uuid}}"
TRACKER_ENDPOINT           = f"{API_BASE_URL}/adserver/tracker"
