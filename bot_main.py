#!/usr/bin/env python
"""
Bot da Claro Prezão - Ponto de entrada
"""
import signal
import sys
import time
import warnings
from utils import patch_telebot_session
from bot_core import BotSession

# Ignorar avisos de requisição HTTPS não verificada
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

def signal_handler(sig, frame):
    """Handler para interrupção limpa"""
    print("\n⚠️ Encerrando o bot...")
    sys.exit(0)

def main():
    """Função principal"""
    # Registra manipuladores de sinal para saída limpa
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Aplica patch na sessão HTTP do telebot
    patch_result = patch_telebot_session()
    print(f"Patch de sessão HTTP: {'✅ Sucesso' if patch_result else '❌ Falha'}")
    
    # Inicia o bot
    print("🔄 Inicializando bot...")
    bot_session = BotSession()
    
    try:
        bot_session.run()
    except KeyboardInterrupt:
        print("\n⚠️ Bot interrompido pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro fatal: {str(e)}")
        print("⏳ Reiniciando em 10 segundos...")
        time.sleep(10)
        main()  # Tenta reiniciar o bot

if __name__ == "__main__":
    main()