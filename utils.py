"""Utilitários para o bot - 2026"""
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import telebot


def configure_http_session():
    """Configura uma sessão HTTP com retry automático"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        # 2026: 'allowed_methods' substituiu 'method_whitelist' no urllib3>=2.0
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def patch_telebot_session():
    """Substitui a sessão HTTP do telebot pela nossa sessão com retry"""
    try:
        telebot.apihelper.SESSION_TIME_TO_LIVE = 5 * 60
        telebot.apihelper.RETRY_ON_ERROR = True
        telebot.apihelper.CONNECT_TIMEOUT = 15
        telebot.apihelper.READ_TIMEOUT = 30
        # 2026: telebot >= 4.22 suporta session customizada
        telebot.apihelper.session = configure_http_session()
        return True
    except Exception as e:
        print(f"[WARN] patch_telebot_session: {e}")
        return False
