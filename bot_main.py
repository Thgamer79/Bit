#!/usr/bin/env python
"""
Bot Gigas 2026 - Ponto de entrada
Adaptações 2026: signal handlers, restart robusto, warnings modernos
"""
import signal
import sys
import time
import warnings
from utils import patch_telebot_session
from bot_core import BotSession

# 2026: ignora avisos SSL e urllib3 DeprecationWarning no Python 3.12+
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
warnings.filterwarnings('ignore', category=DeprecationWarning, module='urllib3')
warnings.filterwarnings('ignore', category=DeprecationWarning, module='requests')


def signal_handler(sig, frame):
    """Handler para interrupção limpa"""
    print("\n⚠️ Encerrando o bot...")
    sys.exit(0)


def main():
    """Função principal"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    patch_result = patch_telebot_session()
    print(f"Patch de sessão HTTP: {'✅ Sucesso' if patch_result else '❌ Falha'}")

    print("🔄 Inicializando bot...")
    bot_session = BotSession()

    restart_count = 0
    max_restarts = 50  # 2026: limite de restarts para evitar loop infinito

    while restart_count < max_restarts:
        try:
            bot_session.run()
        except KeyboardInterrupt:
            print("\n⚠️ Bot interrompido pelo usuário")
            break
        except Exception as e:
            restart_count += 1
            wait = min(60, 10 * restart_count)
            print(f"\n❌ Erro fatal ({restart_count}/{max_restarts}): {str(e)}")
            print(f"⏳ Reiniciando em {wait} segundos...")
            time.sleep(wait)
            # 2026: recria BotSession para limpar estado corrompido
            try:
                bot_session = BotSession()
            except Exception as init_err:
                print(f"❌ Erro ao reinicializar BotSession: {init_err}")

    print("🛑 Bot encerrado após limite de restarts.")


if __name__ == "__main__":
    main()
