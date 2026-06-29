"""Utilitários para o bot"""
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
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def patch_telebot_session():
    """Substitui a sessão HTTP do telebot pela nossa sessão com retry"""
    try:
        # Tenta substituir a sessão padrão do telebot
        telebot.apihelper.session = configure_http_session()
        return True
    except:
        return False