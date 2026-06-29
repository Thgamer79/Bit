"""Bot principal com lógica de negócios"""
import telebot
import threading
import time
import json
import os
import schedule
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
import qrcode
from telebot.storage.memory_storage import StateMemoryStorage
import requests
from uuid import uuid4
from revenda import RevendaModule
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="urllib3")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="requests")
import random
import uuid
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

from config import (BOT_TOKEN, API_BASE_URL, CAMPAIGN_IDS, MAX_THREADS, MAINTENANCE_MODE,
                   MERCADO_PAGO_ACCESS_TOKEN, PIX_PRICE, TRIAL_DAYS, AUTO_COLLECT_TIME,
                   MENU_TYPES, MESSAGES, BUTTON_COOLDOWN, CAMPAIGN_COOLDOWN,
                   PIX_VALIDITY_MINUTES, PIX_BUTTON_TEXT, PIX_RENEWAL_MIN_DAYS,
                   SUBSCRIPTION_DAYS, API_ARTEMIS_CHANNEL_UUID, API_ACCESS_TOKEN)
from database import Database
from api_client import APIClient
from pix_payment import PixPayment
from admin import AdminModule
from states import UserStates
from webhook_server import WebhookServer
from api_vivo import APIClientVivo
from telebot.types import ReplyKeyboardRemove
from mensagem_start import get_mensagem_start

class BotSession:
    def __init__(self):
        # Configurações para melhorar a estabilidade
        telebot.apihelper.SESSION_TIME_TO_LIVE = 5 * 60  # 5 minutos de vida para uma sessão
        telebot.apihelper.RETRY_ON_ERROR = True
        telebot.apihelper.CONNECT_TIMEOUT = 10
        telebot.apihelper.READ_TIMEOUT = 30
        
        # Inicializar todos os objetos
        self.state_storage = StateMemoryStorage()
        self.bot = telebot.TeleBot(BOT_TOKEN, state_storage=self.state_storage, threaded=True)
        self.db = Database()
        self.api = APIClient(API_BASE_URL, self.db)
        self.pix = PixPayment(MERCADO_PAGO_ACCESS_TOKEN)
        self.admin = AdminModule(self.db)
        self.revenda = RevendaModule(self.db, self.pix, self.bot, self.admin)  # Nova instância do módulo de revenda
        self.active_tasks = {}
        self.auto_collect_running = True
        self.button_locks = {}  # Para controle anti-autoclick
        self.active_payment_checks = {}  # Para controlar verificações ativas de pagamento
        self.proxy_setup_done = False  # Flag para controlar configuração do proxy
        self.admin_users = set()  # Conjunto para rastrear usuários no modo admin
        # Status de conexão
        self.connection_attempts = 0
        self.last_connection_time = time.time()
        
        # Inicializa o servidor webhook
        self.webhook_server = WebhookServer(self.db, self.pix, self.bot)
        
        self.setup_handlers()
        self.setup_scheduler()
        self.setup_payment_checker()  # Inicializa o verificador automático de pagamentos
        self.affiliate_codes = {}  # Salva códigos de afiliado temporários por usuário
        self.revenda_uids = {}  # Mapeia user_id do Telegram para revenda_uid
        self.login_step = {}  # user_id: step_name
    
    def rotate_proxy_with_feedback(self, chat_id):
        """Rotaciona o proxy e envia feedback ao usuário"""
        loading_msg = self.bot.send_message(
            chat_id, 
            MESSAGES.get('proxy_connecting', "🔒 Aguarde, conectando a um ambiente seguro e rotacionando IP...")
        )
        
        # Animação de carregamento
        def update_loading_message():
            emojis = ["⏳", "⌛", "🔄", "🔐"]
            for i in range(20):
                try:
                    if not self.proxy_setup_done:
                        self.bot.edit_message_text(
                            f"{emojis[i % 4]} Rotacionando endereço IP... Por favor aguarde.",
                            chat_id, loading_msg.message_id
                        )
                    else:
                        break
                    time.sleep(0.7)
                except Exception as e:
                    print(f"Erro na animação de carregamento: {e}")
                    break
        
        # Inicia a animação em uma thread separada
        self.proxy_setup_done = False
        loading_thread = threading.Thread(target=update_loading_message, daemon=True)
        loading_thread.start()
        
        # Rotaciona o proxy para obter um novo IP
        success, proxy_message, new_ip, new_country = self.api.rotate_proxy()
        self.proxy_setup_done = True
        
        # Pequena pausa
        time.sleep(0.7)
        
        # Atualiza a mensagem com o resultado
        try:
            if success:
                city = self.api.proxy_info.get('city', 'desconhecida')
                region = self.api.proxy_info.get('region', 'desconhecida')
                ip = self.api.proxy_info.get('ip', 'desconhecido')
                
                self.bot.edit_message_text(
                    f"🔐 BYPASS ATIVADO COM SUCESSO! 🚀\n\n"
                    f"🌐 Seu novo endereço IP: {ip}\n"
                    f"📍 Localização atual: {city}/{region}\n\n"
                    f"✅ Sua conexão está segura e anônima!\n"
                    f"🛡️ Pronto para operar com máxima proteção.",
                    chat_id, loading_msg.message_id
                )
            else:
                self.bot.edit_message_text(
                    f"⚠️ {proxy_message}",
                    chat_id, loading_msg.message_id
                )
        except Exception as e:
            print(f"Erro ao atualizar mensagem de proxy: {e}")
        
        # Pausa para o usuário ler a mensagem
        time.sleep(1.5)
        
        return success

    def update_proxy_location(self):
        """Atualiza cidade e região do IP do proxy usando ip-api.com"""
        ip = self.api.proxy_info.get('ip')
        if not ip:
            return
        try:
            resp = requests.get(f'http://ip-api.com/json/{ip}', timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self.api.proxy_info['city'] = data.get('city', 'desconhecida')
                self.api.proxy_info['region'] = data.get('regionName', 'desconhecida')
        except Exception as e:
            print(f'Erro ao buscar localização do proxy: {e}')

    def create_welcome_message(self, user_data):
        """Cria mensagem de boas-vindas com informações de moedas, internet e data/hora atuais usando método nativo"""
        from datetime import datetime, timedelta
        
        # Dias da semana em português
        dias_semana = {
            0: "segunda-feira",
            1: "terça-feira",
            2: "quarta-feira",
            3: "quinta-feira",
            4: "sexta-feira",
            5: "sábado",
            6: "domingo"
        }
        
        # Meses em português
        meses = {
            1: "janeiro",
            2: "fevereiro",
            3: "março",
            4: "abril",
            5: "maio",
            6: "junho",
            7: "julho",
            8: "agosto",
            9: "setembro",
            10: "outubro",
            11: "novembro",
            12: "dezembro"
        }
        
        # Obtém data e hora UTC do servidor
        now_utc = datetime.now()
        
        # Ajusta para o fuso horário do Brasil (UTC-3)
        time_difference = timedelta(hours=-3)
        now_brazil = now_utc + time_difference
        
        # Formata a data e hora em português
        dia_semana = dias_semana[now_brazil.weekday()]
        dia = now_brazil.day
        mes = meses[now_brazil.month]
        ano = now_brazil.year
        hora = now_brazil.strftime("%H:%M")
        
        data_hora_str = f"Hoje é {dia_semana}, {dia} de {mes} de {ano} e horário {hora}"
        
        # Obter saldo de moedas
        operator = user_data.get('operator')
        # Compatibilidade: se não existir bloco da operadora, usa raiz
        authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
        balance_response = self.api.get_balance(authorization)
        balance = balance_response['balance'] if balance_response['success'] else 0
        
        # Obter informações de internet
        internet_response = self.api.get_internet_quota(authorization)
        
        # Descobrir operadora do usuário
        user_operator = user_data.get('operator', None)
        if not user_operator and hasattr(self.db, 'get_user_operator'):
            user_operator = self.db.get_user_operator(user_data.get('user_id', None))
        
        # Só mostra barra de internet para Claro
        if user_operator == 'claro':
            if internet_response['success']:
                internet_remaining = internet_response['remaining']
                internet_total = internet_response['total']
                try:
                    remaining_value = float(''.join(filter(lambda x: x.isdigit() or x == '.', internet_remaining)))
                    total_value = float(''.join(filter(lambda x: x.isdigit() or x == '.', internet_total)))
                    internet_percent = min(100, int((remaining_value / total_value) * 100)) if total_value > 0 else 0
                    progress_blocks = int(internet_percent / 10)
                    progress_bar = '🟦' * progress_blocks + '⬜' * (10 - progress_blocks)
                except:
                    internet_percent = 0
                    progress_bar = '⬜' * 10
            else:
                internet_remaining = "N/A"
                internet_total = "N/A"
                internet_percent = 0
                progress_bar = '⬜' * 10
            internet_msg = (
                f"📱 SEU PACOTE DE INTERNET:\n"
                f"{progress_bar} {internet_percent}%\n\n"
                f"📊 {internet_remaining} de {internet_total}\n\n"
            )
        else:
            internet_msg = ""
        
        message = (
            f"🎉 LOGIN REALIZADO COM SUCESSO! 🎉\n\n"
            f"📅 {data_hora_str}\n\n"  # Nova linha com data e hora
            f"💎 SEU SALDO: {balance} MOEDAS 💰\n\n"
            f"{internet_msg}"
            f"✨ DICA: Use os comandos abaixo para conseguir mais moedas e internet!\n\n"
            f"👇 NAVEGUE PELOS MENUS PARA COMEÇAR! 👇"
        )
        return message

    def run(self):
        """Inicia o bot com recuperação automática de erros e tratamento de desconexões"""
        # Inicia o webhook se ainda não estiver rodando
        self.webhook_server.start()
        
        # Configurações de reconexão
        max_retries = 10  # Máximo de tentativas antes de aguardar mais tempo
        retry_count = 0
        min_retry_delay = 5  # Tempo mínimo entre tentativas (segundos)
        max_retry_delay = 60  # Tempo máximo entre tentativas (segundos)
        
        while True:
            try:
                print("🚀 Bot iniciado com sucesso!")
                # Limpa os dados antigos na inicialização
                self.db.cleanup_old_data()
                
                # Configurações mais robustas para o polling
                self.bot.polling(
                    none_stop=True,           # Não pare em caso de erros
                    interval=2,               # Intervalo entre solicitações
                    timeout=30,               # Timeout da conexão
                    allowed_updates=None,     # Receber todos os tipos de atualizações
                    long_polling_timeout=20   # Timeout do long polling
                )
                
                # Se chegou aqui, resetamos a contagem de tentativas
                retry_count = 0
                
            except (ConnectionError, ConnectionResetError, ConnectionAbortedError,
                    ConnectionRefusedError, OSError) as network_error:
                # Erros específicos de rede
                retry_count += 1
                # Cálculo de backoff exponencial (tempo aumenta gradualmente)
                delay = min(max_retry_delay, min_retry_delay * (2 ** (retry_count // 3)))
                
                print(f"⚠️ Erro de conexão: {str(network_error)}")
                print(f"🔄 Tentativa {retry_count}... reconectando em {delay} segundos")
                time.sleep(delay)
                
            except Exception as e:
                # Outros erros não relacionados à rede
                print(f"❌ Erro no polling: {str(e)}")
                print(f"[DEBUG] Tipo do erro: {type(e)}")
                import traceback
                traceback.print_exc()
                print(f"🔄 Reconectando em 10 segundos...")
                time.sleep(10) 

        # Modifique o método setup_scheduler em bot_core.py
    def setup_scheduler(self):
            """Configura o agendador para coleta automática apenas 1x por dia no horário do config.py"""
            from datetime import datetime, timedelta
            
            def adjust_to_brazil_timezone(time_str):
                hour, minute = map(int, time_str.split(':'))
                now_utc = datetime.now()
                time_difference = timedelta(hours=-3)
                now_brazil = now_utc + time_difference
                target_time_brazil = now_brazil.replace(
                    hour=hour, 
                    minute=minute, 
                    second=0, 
                    microsecond=0
                )
                target_time_utc = target_time_brazil - time_difference
                if target_time_utc < now_utc:
                    target_time_utc += timedelta(days=1)
                return target_time_utc.strftime("%H:%M")
            
            # Apenas o horário do config
            original_server_time = adjust_to_brazil_timezone(AUTO_COLLECT_TIME)
            schedule.every().day.at(original_server_time).do(self.run_auto_collect)
            print(f"🕐 Coleta automática agendada para: {AUTO_COLLECT_TIME} (Brasil) -> {original_server_time} (Servidor)")
            
            def run_scheduler():
                while True:
                    schedule.run_pending()
                    time.sleep(1)
            
            scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
            scheduler_thread.start()
            
            print("✅ Agendador configurado com 1 horário de coleta automática por dia!")
            
    def setup_payment_checker(self):
        """
        Configuração modificada - apenas marca os pagamentos, não realiza verificações automáticas
        já que o webhook cuida dessa parte
        """
        def check_pending_payments():
            # Função vazia - o webhook fará todo o trabalho de verificação
            pass
        
        # Não registramos mais a verificação no agendador
        # schedule.every(5).seconds.do(check_pending_payments)
        
        print("✅ Verificador automático desativado - usando webhook para pagamentos")

    def check_payment_frequently(self, payment_id, user_id, message_info=None):
        """
        Função mantida apenas para compatibilidade, não faz verificações
        O webhook cuidará de todas as verificações de pagamento
        """
        # Apenas registra o pagamento no dicionário, mas não inicia verificações
        self.active_payment_checks[payment_id] = False
        
        print(f"✅ Pagamento {payment_id} registrado. O webhook processará quando confirmado.")


    def handle_admin_menu(self, message):
        """Handler central para menu admin"""
        # Primeiro verificamos se o usuário está no modo admin
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            # Se não estiver no modo admin, ignoramos o comando
            return
            
        if message.text == "📋 Listar Usuários":
            users = self.admin.list_all_users()
            
            if not users:
                self.bot.reply_to(message, "Nenhum usuário encontrado")
                return
                
            # Agrupa usuários em mensagens menores
            msg = "📋 LISTA DE USUÁRIOS\n\n"
            user_blocks = []
            current_block = []
            
            for user in users:
                user_text = (
                    f"ID: {user['user_id']}\n"
                    f"📱 Telefone: {user['phone']}\n"
                    f"⏳ Dias: {user['days_left']}\n"
                    f"🗓 Criado em: {user['created_at']}\n"
                    f"🕒 Último login: {user['last_login']}\n"
                    f"📶 Operadora: {user['operator']}\n"
                    f"🤖 Auto Coleta: {'✅' if user['auto_collect'] else '❌'}\n"
                    f"➖➖➖➖➖➖➖➖\n"
                )
                
                if len(msg + ''.join(current_block) + user_text) > 3800:
                    user_blocks.append(msg + ''.join(current_block))
                    current_block = [user_text]
                    msg = "📋 LISTA DE USUÁRIOS (continuação)\n\n"
                else:
                    current_block.append(user_text)
            
            if current_block:
                user_blocks.append(msg + ''.join(current_block))
            
            # Envia as mensagens
            for block in user_blocks:
                self.bot.reply_to(message, block)
                
        elif message.text == "📊 Usuários Vencidos":
            users = self.admin.list_expired_users()
            
            if not users:
                self.bot.reply_to(message, "Nenhum usuário vencido")
                return
                
            msg = "📊 USUÁRIOS VENCIDOS\n\n"
            expired_blocks = []
            current_block = []
            
            for user in users:
                user_text = (
                    f"ID: {user['user_id']}\n"
                    f"📱 Telefone: {user['phone']}\n"
                    f"📅 Vencimento: {user['subscription_end']}\n"
                    f"🕒 Último login: {user['last_login']}\n"
                    f"➖➖➖➖➖➖➖➖\n"
                )
                
                if len(msg + ''.join(current_block) + user_text) > 3800:
                    expired_blocks.append(msg + ''.join(current_block))
                    current_block = [user_text]
                    msg = "📊 USUÁRIOS VENCIDOS (continuação)\n\n"
                else:
                    current_block.append(user_text)
            
            if current_block:
                expired_blocks.append(msg + ''.join(current_block))
            
            for block in expired_blocks:
                self.bot.reply_to(message, block)
            
        elif message.text == "✅ Renovar Usuário":
            msg = self.bot.reply_to(message, 
                "💡 Digite o ID do usuário e quantidade de dias\n\n"
                "Formato: ID DIAS\n"
                "Exemplo: 123456789 30")
            self.bot.register_next_step_handler(msg, self.process_renew_user)
            
        elif message.text == "❌ Remover Dias":
            msg = self.bot.reply_to(message, 
                "💡 Digite o ID do usuário e dias a remover\n\n"
                "Formato: ID DIAS\n"
                "Exemplo: 123456789 10")
            self.bot.register_next_step_handler(msg, self.process_remove_days)
            
        elif message.text == "🗑 Excluir Usuário":
            msg = self.bot.reply_to(message, 
                "⚠️ Digite o ID do usuário para excluir\n\n"
                "⚡️ Esta ação não pode ser desfeita!")
            self.bot.register_next_step_handler(msg, self.process_delete_user)
            
        elif message.text.startswith("🔛 Trocar Número:"):
            # Verifica o status atual
            current_status = self.db.is_phone_change_enabled()
            
            # Inverte o status
            new_status = not current_status
            self.admin.toggle_phone_change(new_status)
            
            # Mostra o novo status
            status_text = "✅ ON" if new_status else "❌ OFF"
            self.bot.reply_to(message, f"🔄 Troca de número: {status_text}")
            
            # Atualiza o menu admin
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("📋 Listar Usuários", "📊 Usuários Vencidos")
            markup.row("✅ Renovar Usuário", "❌ Remover Dias")
            markup.row("🗑 Excluir Usuário", "🚫 Suspender Usuário", "✅ Ativar Usuário")
            markup.row("🔛 Trocar Número: " + ("✅ ON" if self.db.is_phone_change_enabled() else "❌ OFF"))
            markup.row("👥 Listar Revendedores", "➕ Adicionar Revendedor")
            markup.row("💰 Dar Créditos", "🗑️ Remover Revendedor")
            markup.row("❌ Remover Revenda e Subs", "🔙 Voltar ao Menu")
            self.bot.reply_to(message, "🔓 Painel Admin:", reply_markup=markup)
        
        elif message.text == "👥 Listar Revendedores":
            # Implementar listagem de revendedores
            revendedores = self.admin.list_all_resellers()
            if not revendedores:
                self.bot.reply_to(message, "Nenhum revendedor encontrado")
                return
                
            msg = "👥 LISTA DE REVENDEDORES\n\n"
            for rev in revendedores:
                msg += f"ID: {rev['user_id']}\n"
                msg += f"📱 Telefone: {rev['phone']}\n"
                msg += f"💰 Créditos: {rev['credits']}\n"
                msg += f"👥 Clientes: {rev['total_clients']}\n"
                msg += f"➖➖➖➖➖➖➖➖\n"
                
                if len(msg) > 3500:  # Limite do Telegram
                    self.bot.reply_to(message, msg)
                    msg = "👥 LISTA DE REVENDEDORES (continuação)\n\n"
                    
            if msg:
                self.bot.reply_to(message, msg)
                
        elif message.text == "➕ Adicionar Revendedor":
            msg = self.bot.reply_to(message, 
                "💡 Digite o ID do usuário e (opcionalmente) créditos iniciais\n\n"
                "Formato: ID [CREDITOS]\n"
                "Exemplo: 123456789 50")
            self.bot.register_next_step_handler(msg, self.process_add_reseller)
                
        elif message.text == "💰 Dar Créditos":
            msg = self.bot.reply_to(message, 
                "💡 Digite o ID do revendedor e quantidade de créditos\n\n"
                "Formato: ID CREDITOS\n"
                "Exemplo: 123456789 100")
            self.bot.register_next_step_handler(msg, self.process_add_credits)
                
        elif message.text == "🗑️ Remover Revendedor":
            msg = self.bot.reply_to(message, 
                "⚠️ Digite o ID do revendedor para remover\n\n"
                "⚡️ Esta ação não pode ser desfeita!")
            self.bot.register_next_step_handler(msg, self.process_remove_reseller)
                
        elif message.text == "❌ Remover Revenda e Subs":
            msg = self.bot.reply_to(message, 
                "⚠️ ATENÇÃO! Esta ação removerá o revendedor e TODAS as assinaturas de seus clientes!\n\n"
                "Digite o ID do revendedor para confirmar:")
            self.bot.register_next_step_handler(msg, self.process_remove_reseller_and_subs)

        elif message.text == "🚫 Suspender Usuário":
            msg = self.bot.reply_to(message, 
                "⚠️ Digite o ID do usuário para suspender\n\n"
                "⚡️ O usuário ficará suspenso e não poderá acessar até ser ativado pelo admin!")
            self.bot.register_next_step_handler(msg, self.process_suspend_user)
        elif message.text == "✅ Ativar Usuário":
            msg = self.bot.reply_to(message, 
                "⚠️ Digite o ID do usuário para ativar\n\n"
                "⚡️ O usuário voltará a ter acesso normalmente!")
            self.bot.register_next_step_handler(msg, self.process_activate_user)




    def run_auto_collect(self):
        """Executa a coleta automática para todos os usuários ativos com relatório aprimorado"""
        if not self.auto_collect_running:
            return
                
        print("🤖 Iniciando coleta automática...")
        users = self.db.load_users()
        
        for user_id, user_data in users.items():
            if not user_data.get('auto_collect_enabled', False):
                continue
            
            subscription = self.db.check_subscription(user_id)
            if not subscription["active"]:
                continue
                    
            try:
                # Notificar o início do processo
                try:
                    self.bot.send_message(
                        int(user_id), 
                        "🤖 COLETA AUTOMÁTICA INICIANDO...\n\n"
                        "⏳ Aguarde enquanto eu:\n"
                        "1️⃣ Coletamos suas moedas de campanhas\n"
                        "2️⃣ Compramos os melhores pacotes disponíveis\n"
                        "3️⃣ Priorizamos pacotes de 500MB e pacotes de voz\n\n"
                        "⚡ Este processo pode levar alguns minutos!"
                    )
                except Exception as e:
                    print(f"Erro ao enviar mensagem inicial: {str(e)}")
                
                # Prepara objetos para campanhas
                class FakeMessage:
                    def __init__(self, user_id):
                        self.from_user = type('obj', (object,), {'id': int(user_id)})()
                        self.chat = type('obj', (object,), {'id': int(user_id)})()
                        self.text = None
                
                fake_message = FakeMessage(user_id)
                
                # Obtém saldo inicial
                initial_balance_response = None
                try:
                    operator = user_data.get('operator')
                    authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                    initial_balance_response = self.api.get_balance(authorization)
                except:
                    pass
                
                initial_balance = initial_balance_response['balance'] if initial_balance_response and initial_balance_response['success'] else 0
                
                # Executa as campanhas
                self.start_campaigns(fake_message, silent_mode=True)
                time.sleep(5)  # Aguarda um pouco para campanhas processarem
                
                # Obtém saldo após campanhas
                after_campaigns_response = None
                try:
                    operator = user_data.get('operator')
                    authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                    after_campaigns_response = self.api.get_balance(authorization)
                except:
                    pass
                
                after_campaigns = after_campaigns_response['balance'] if after_campaigns_response and after_campaigns_response['success'] else 0
                coins_earned = after_campaigns - initial_balance
                
                # Compra os pacotes e obtém relatório
                purchased_packages, coins_spent = self.auto_buy_packages(fake_message)
                
                # Prepara relatório visual de pacotes comprados
                packages_report = ""
                if purchased_packages:
                    packages_report = "📦 PACOTES COMPRADOS:\n\n"
                    for i, pkg in enumerate(purchased_packages, 1):
                        packages_report += f"{i}. {pkg['name']} - {pkg['price']} moedas\n"
                        
                    packages_report += f"\n💰 Total gasto: {coins_spent} moedas"
                else:
                    packages_report = "❌ Nenhum pacote foi comprado"
                
                # Envia relatório final
                try:
                    self.bot.send_message(
                        int(user_id), 
                        f"✅ COLETA AUTOMÁTICA CONCLUÍDA!\n\n"
                        f"📊 RELATÓRIO COMPLETO:\n\n"
                        f"💎 Moedas antes: {initial_balance}\n"
                        f"⭐ Moedas coletadas: {coins_earned}\n"
                        f"💸 Moedas gastas: {coins_spent}\n"
                        f"💰 Saldo atual: {after_campaigns - coins_spent}\n\n"
                        f"{packages_report}\n\n"
                        f"⏰ Próxima coleta automática: {AUTO_COLLECT_TIME}"
                    )
                except Exception as e:
                    print(f"Erro ao enviar relatório final: {str(e)}")
                    try:
                        self.bot.send_message(
                            int(user_id), 
                            "✅ Coleta automática concluída!\n"
                            "❌ Não foi possível gerar o relatório completo."
                        )
                    except:
                        pass
                
            except Exception as e:
                print(f"Erro na coleta automática para usuário {user_id}: {str(e)}")
                try:
                    self.bot.send_message(
                        int(user_id), 
                        "❌ Erro na coleta automática.\n"
                        "Por favor, tente executar manualmente."
                    )
                except:
                    pass


    def process_remove_reseller_and_subs(self, message):
        """Processa remoção de um revendedor e todas as assinaturas"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
        
        # Verifica se o usuário está no modo admin
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
                
        # Verifica se a mensagem é um botão do menu admin
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
                            
        # Qualquer botão que inicie com 🔛 Trocar Número
        if message.text and message.text.startswith("🔛 Trocar Número:"):
            admin_menu_buttons.append(message.text)
                            
        if message.text in admin_menu_buttons:
            # Redireciona para o handler do menu admin
            self.handle_admin_menu(message)
            return
            
        try:
            user_id_to_remove = message.text.strip()
            
            # Verificar se é realmente um revendedor
            if not self.db.is_reseller(user_id_to_remove):
                self.bot.reply_to(message, "❌ ID fornecido não é de um revendedor válido.")
                return
                
            # Obter contagem de clientes para confirmação
            client_count = self.db.count_reseller_clients(user_id_to_remove)
            
            # Pedir confirmação adicional
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("✅ Sim, remover tudo", callback_data=f"confirm_remove_all_{user_id_to_remove}"),
                telebot.types.InlineKeyboardButton("❌ Cancelar", callback_data="cancel_remove_all")
            )
            
            self.bot.reply_to(message, 
                f"⚠️ CONFIRMAÇÃO FINAL\n\n"
                f"Revendedor: {user_id_to_remove}\n"
                f"Total de clientes: {client_count}\n\n"
                f"⚠️ Esta ação removerá o revendedor e TODAS as assinaturas de seus clientes!\n"
                f"⚠️ Esta ação não pode ser desfeita!\n\n"
                f"Tem certeza que deseja continuar?",
                reply_markup=markup)
                
        except Exception as e:
            self.bot.reply_to(message, 
                f"❌ Erro: {str(e)}\n\n"
                f"💡 Digite apenas o ID do revendedor\n"
                f"Exemplo: 123456789")

            # Método auto_buy_packages atualizado
    def auto_buy_packages(self, message):
            """Compra pacotes automaticamente - usando IDs específicos: VOZ (12) + 4x 500MB (7)"""
            user_id = str(message.from_user.id)
            users = self.db.load_users()
            
            if user_id not in users:
                return None, 0
                    
            user_data = users[user_id]
            operator = user_data.get('operator')
            authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
            response = self.api.get_packages(authorization)
            
            if not response['success']:
                return None, 0
            
            # Verifica o saldo inicial
            balance_response = self.api.get_balance(authorization)
            if not balance_response['success']:
                return None, 0
                    
            initial_balance = balance_response['balance']
            current_balance = initial_balance
            packages = response['packages']
            
            # Prepara relatório de compras
            purchased_packages = []
            total_spent = 0
            
            # CORREÇÃO: Usar IDs específicos dos pacotes
            package_500mb = None  # ID 7 - Receba 500 MB
            package_voz = None    # ID 12 - Receba 5 dias de Voz
            
            # Busca os pacotes pelos IDs específicos
            for package in packages:
                package_id = str(package.get('id', ''))
                if package_id == '7':  # Pacote 500MB
                    package_500mb = package
                    print(f"✅ Encontrado pacote 500MB: {package.get('description', '')} - {package.get('fullPrice', 0)} moedas")
                elif package_id == '12':  # Pacote VOZ
                    package_voz = package
                    print(f"✅ Encontrado pacote VOZ: {package.get('description', '')} - {package.get('fullPrice', 0)} moedas")
            
            # Preparar lista de compras: 1 VOZ primeiro, depois 4x 500MB
            shopping_list = []
            
            # Adiciona 1 pacote de voz primeiro (ID 12)
            if package_voz:
                shopping_list.append(package_voz)
                print(f"✅ Adicionado à lista: 1x VOZ - {package_voz.get('description', '')}")
            else:
                print("⚠️ Pacote de VOZ (ID 12) não encontrado!")
            
            # Adiciona 4 pacotes de 500MB (ID 7)
            if package_500mb:
                for i in range(4):
                    shopping_list.append(package_500mb)
                print(f"✅ Adicionado à lista: 4x 500MB - {package_500mb.get('description', '')}")
            else:
                print("⚠️ Pacote de 500MB (ID 7) não encontrado!")
            
            # Se não encontrou os pacotes específicos, usa fallback
            if not shopping_list:
                print("⚠️ Pacotes específicos não encontrados, usando fallback...")
                # Fallback para outros pacotes de internet disponíveis
                other_packages = []
                for package in packages:
                    description = package.get('description', '').lower()
                    if ('mb' in description or 'internet' in description) and 'sms' not in description:
                        other_packages.append(package)
                
                if other_packages:
                    # Ordena por preço e pega o mais barato
                    other_packages.sort(key=lambda x: x.get('fullPrice', 0))
                    best_package = other_packages[0]
                    for i in range(4):  # Compra 4 do mais barato disponível
                        shopping_list.append(best_package)
                    print(f"✅ Fallback: usando 4x {best_package.get('description', '')}")
            
            if not shopping_list:
                print(f"❌ Nenhum pacote adequado encontrado para o usuário {user_id}")
                return None, 0
            
            # Compra os pacotes na ordem da lista
            for i, package in enumerate(shopping_list):
                package_price = package.get('fullPrice', 0)
                package_desc = package.get('description', 'Pacote')
                package_id = package.get('id', '')
                
                # Só tenta comprar se tiver saldo suficiente
                if current_balance >= package_price:
                    print(f"🛒 Tentando comprar: {package_desc} (ID: {package_id}) - {package_price} moedas")
                    
                    # Tenta comprar o pacote
                    redeem_response = self.api.redeem_package(authorization, package_id, user_id)
                    
                    if redeem_response['success']:
                        # Registra a compra bem-sucedida
                        current_balance -= package_price
                        total_spent += package_price
                        purchased_packages.append({
                            'name': package_desc,
                            'price': package_price,
                            'id': package_id
                        })
                        
                        print(f"✅ Comprado: {package_desc} (ID: {package_id}) - {package_price} moedas")
                        
                        # Pausa entre compras
                        time.sleep(1.5)
                    
                    # Se atingir o limite diário, para
                    elif 'limit_reached' in redeem_response:
                        print(f"⚠️ Limite diário atingido para usuário {user_id}")
                        break
                    else:
                        print(f"❌ Erro ao comprar {package_desc}: {redeem_response.get('error', 'Erro desconhecido')}")
                else:
                    print(f"💰 Saldo insuficiente: {package_desc} custa {package_price}, saldo atual: {current_balance}")
            
            # Saldo final
            final_balance_response = self.api.get_balance(authorization)
            final_balance = final_balance_response['balance'] if final_balance_response['success'] else current_balance
            
            print(f"📊 Resumo da compra: {len(purchased_packages)} pacotes, {total_spent} moedas gastas")
            
            return purchased_packages, initial_balance - final_balance
            
        
    def process_add_reseller(self, message):
        """Processa a adição de um revendedor"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
        
        # Verifica se o usuário está no modo admin
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
                
        # Verifica se a mensagem é um botão do menu admin
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
                            
        # Qualquer botão que inicie com 🔛 Trocar Número
        if message.text and message.text.startswith("🔛 Trocar Número:"):
            admin_menu_buttons.append(message.text)
                            
        if message.text in admin_menu_buttons:
            # Redireciona para o handler do menu admin
            self.handle_admin_menu(message)
            return
            
        try:
            parts = message.text.split()
            if len(parts) == 1:
                # Se forneceu apenas o ID do usuário, adiciona sem créditos iniciais
                user_id_to_add = parts[0].strip()
                initial_credits = 0
            elif len(parts) == 2:
                # Se forneceu ID e créditos
                user_id_to_add = parts[0].strip()
                initial_credits = int(parts[1])
            else:
                raise ValueError("Formato inválido")
            
            if initial_credits < 0:
                self.bot.reply_to(message, "❌ Quantidade de créditos inválida")
                return
                
            if self.admin.add_reseller(user_id_to_add, initial_credits):
                self.bot.reply_to(message, 
                    f"✅ Revendedor adicionado com sucesso!\n\n"
                    f"👤 ID: {user_id_to_add}\n"
                    f"💰 Créditos iniciais: {initial_credits}")
            else:
                self.bot.reply_to(message, "❌ Erro ao adicionar revendedor. Verifique o ID.")
                
        except ValueError:
            self.bot.reply_to(message, 
                "❌ Formato inválido!\n\n"
                "💡 Use: ID_USUARIO [CREDITOS_INICIAIS]\n"
                "Exemplo: 123456789 50")
                
    def process_add_credits(self, message):
        """Processa adição de créditos a um revendedor"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
        
        # Verifica se o usuário está no modo admin
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
                
        # Verifica se a mensagem é um botão do menu admin
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
                            
        # Qualquer botão que inicie com 🔛 Trocar Número
        if message.text and message.text.startswith("🔛 Trocar Número:"):
            admin_menu_buttons.append(message.text)
                            
        if message.text in admin_menu_buttons:
            # Redireciona para o handler do menu admin
            self.handle_admin_menu(message)
            return
            
        try:
            parts = message.text.split()
            if len(parts) != 2:
                raise ValueError("Formato incorreto")
                
            user_id_to_credit = parts[0]
            credits = int(parts[1])
            
            if credits <= 0:
                self.bot.reply_to(message, "❌ Número de créditos deve ser maior que 0")
                return
                
            if self.admin.add_credits_to_reseller(user_id_to_credit, credits):
                self.bot.reply_to(message, 
                    f"✅ Créditos adicionados com sucesso!\n\n"
                    f"👤 Revendedor: {user_id_to_credit}\n"
                    f"💰 Adicionado: {credits} créditos")
            else:
                self.bot.reply_to(message, "❌ Erro ao adicionar créditos. Verifique o ID.")
                
        except ValueError:
            self.bot.reply_to(message, 
                "❌ Formato inválido!\n\n"
                "💡 Use: ID_USUARIO CREDITOS\n"
                "Exemplo: 123456789 100")

    def process_remove_reseller(self, message):
        """Processa remoção de um revendedor"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
        
        # Verifica se o usuário está no modo admin
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
                
        # Verifica se a mensagem é um botão do menu admin
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
                            
        # Qualquer botão que inicie com 🔛 Trocar Número
        if message.text and message.text.startswith("🔛 Trocar Número:"):
            admin_menu_buttons.append(message.text)
                            
        if message.text in admin_menu_buttons:
            # Redireciona para o handler do menu admin
            self.handle_admin_menu(message)
            return
            
        try:
            user_id_to_remove = message.text.strip()
            
            if not user_id_to_remove:
                raise ValueError("ID vazio")
                
            if self.admin.remove_reseller(user_id_to_remove):
                self.bot.reply_to(message, 
                    f"✅ Revendedor removido com sucesso!\n\n"
                    f"🗑 ID: {user_id_to_remove}")
            else:
                self.bot.reply_to(message, "❌ Erro ao remover revendedor. Verifique o ID.")
                
        except ValueError:
            self.bot.reply_to(message, 
                "❌ Formato inválido!\n\n"
                "💡 Digite apenas o ID do revendedor\n"
                "Exemplo: 123456789")

    def check_button_spam(self, user_id, button_type):
        """Verifica se o usuário está fazendo spam de botões"""
        # Verificar cooldown no banco de dados
        if self.db.check_button_cooldown(user_id, button_type):
            return True
            
        return False
        
            
    def start_campaigns(self, message, silent_mode=False):
        """Inicia campanhas com melhor visualização de progresso e relatório"""
        # Verifica sessão antes de continuar
        def _start_campaigns(message):
            user_id = str(message.from_user.id)
            chat_id = message.chat.id

            # Proteção anti-autoclick (desativada em modo silencioso)
            if not silent_mode and self.check_button_spam(user_id, "campaigns"):
                self.bot.send_message(chat_id, MESSAGES.get('too_many_clicks', "⚠️ Muitos cliques detectados!"))
                return

            users = self.db.load_users()
            
            if user_id not in users:
                if not silent_mode:
                    self.bot.send_message(chat_id, "🔐 Você precisa fazer login primeiro.")
                return

            # Verificar se a assinatura está ativa antes de permitir campanha
            if not self.check_subscription_access(user_id):
                if not silent_mode:
                    self.show_expired_message(message)
                return

            if self.active_tasks.get(user_id):
                if not silent_mode:
                    self.bot.send_message(chat_id, "🏃‍♂️ Já tem uma campanha rolando!")
                return

            # Obtém o saldo inicial
            user_data = users[user_id]
            initial_balance_response = None
            try:
                operator = user_data.get('operator')
                authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                initial_balance_response = self.api.get_balance(authorization)
            except:
                pass
            
            initial_balance = initial_balance_response['balance'] if initial_balance_response and initial_balance_response['success'] else 0

            def process_video(campaign_info, media_info, user_data, completed_campaigns, status_msg):
                success = False  # Garante valor inicial
                token = None     # Garante valor inicial
                if not self.active_tasks.get(user_id):
                    return

                operator = user_data.get('operator')
                user_operator = self.db.get_user_operator(user_id)
                authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                # --- NOVO FLUXO PARA CLARO ---
                if user_operator == "claro":
                    # Busca o wallet.id do /hmld
                    hmld = self.api._make_request('GET', 'hmld', headers={'x-authorization': authorization})
                    wallet_id = ''
                    if hmld.get('success') and 'wallet' in hmld.get('body', {}):
                        wallet_id = hmld['body']['wallet'].get('id', '')
                    campaign_id = campaign_info.get('campaignUuid') or campaign_info.get('id')
                    request_id = campaign_info.get('trackingId') or media_info.get('uuid')
                    media_uuid = media_info.get('uuid')
                    print(f"[CLARO][DEBUG] Parâmetros para tracking: campaign_id={campaign_id}, wallet_id={wallet_id}, request_id={request_id}, media_uuid={media_uuid}")
                    # Saldo antes
                    saldo_antes = self.api.get_balance(authorization)
                    print(f"[CLARO][DEBUG] Saldo ANTES do vídeo: {saldo_antes}")
                    # Envia evento impression
                    response = self.api.track_campaign_claro(
                        authorization,
                        'impression',
                        campaign_id,
                        wallet_id,
                        request_id
                    )
                    print(f"[CLARO][TRACK] Enviando impression: camp={campaign_id}, wallet={wallet_id}, req={request_id}, resp={response}")
                    success = response.get('success', False)
                    # Definir token para Claro (usa authorization)
                    token = authorization
                    # Aguarda um tempo simulando visualização do vídeo
                    time.sleep(random.uniform(1, 2))
                    # Envia evento complete
                    response_complete = self.api.track_campaign_claro(
                        authorization,
                        'complete',
                        campaign_id,
                        wallet_id,
                        request_id,
                        media_uuid
                    )
                    print(f"[CLARO][TRACK] Enviando complete: camp={campaign_id}, wallet={wallet_id}, req={request_id}, resp={response_complete}")
                    if not response_complete.get('success', False):
                        success = False
                    # Saldo depois
                    saldo_depois = self.api.get_balance(authorization)
                    print(f"[CLARO][DEBUG] Saldo DEPOIS do vídeo: {saldo_depois}")
                else:
                    # ... fluxo original Vivo/Tim ...
                    events = ['start', 'complete']
                    campaign_id = campaign_info.get('campaignUuid')
                    if user_operator == "vivo":
                        wallet_id = user_data.get(operator, {}).get('wallet_id', user_data.get('wallet_id', ''))
                    else:
                        wallet_id = user_data.get('wallet_id', '')
                    for event in events:
                        if not self.active_tasks.get(user_id):
                            return
                        response = self.api.track_campaign(
                            authorization,
                            event,
                            campaign_id,
                            wallet_id,
                            campaign_info['trackingId'],
                            media_info['uuid']
                        )
                        if response.get('new_token'):
                            token = response['new_token']
                            operator = user_data.get('operator')
                            if operator:
                                if operator not in user_data:
                                    user_data[operator] = {}
                                user_data[operator]['authorization'] = token
                            else:
                                user_data['authorization'] = token
                        if not response['success']:
                            success = False
                            break
                        if event == 'start':
                            time.sleep(random.uniform(1, 2))
                        else:
                            time.sleep(random.uniform(0.2, 0.5))

                if success:
                    with completed_campaigns['lock']:
                        completed_campaigns['count'] += 1
                        progress = int((completed_campaigns['count'] / completed_campaigns['total']) * 100)
                        current_balance = self.api.get_balance(token)
                        print(f"[TIM][DEBUG] Saldo após vídeo: {current_balance}")
                        balance = current_balance['balance'] if current_balance['success'] else 0
                        coins_earned = balance - initial_balance
                        progress_bars = ['⬜' * 10, '��' + '⬜' * 9, '🟦' * 2 + '⬜' * 8, '🟦' * 3 + '⬜' * 7, 
                                        '🟦' * 4 + '⬜' * 6, '🟦' * 5 + '⬜' * 5, '🟦' * 6 + '⬜' * 4, 
                                        '🟦' * 7 + '⬜' * 3, '🟦' * 8 + '⬜' * 2, '🟦' * 9 + '⬜', '🟦' * 10]
                        progress_bar = progress_bars[int(progress/10)]
                        text = (f"🚀 COLETANDO MOEDAS...\n\n"
                            f"🎮 Progresso: {progress}%\n"
                            f"{progress_bar}\n\n"
                            f"💎 Moedas iniciais: {initial_balance}\n"
                            f"⭐ Moedas coletadas: +{coins_earned}\n"
                            f"💰 Saldo atual: {balance}\n\n"
                            f"📺 Campanhas: {completed_campaigns['count']}/{completed_campaigns['total']}")
                        if not silent_mode:
                            try:
                                self.bot.edit_message_text(text, chat_id, status_msg.message_id)
                            except:
                                pass

                # Após todos os vídeos de uma campanha, envia success_impression (apenas uma vez)
                if user_operator == "tim":
                    # Verifica se todos os vídeos da campanha foram assistidos
                    camp_videos = [v for v in all_videos if v['campaign']['campaign_id'] == campaign_id]
                    done_videos = [v for v in camp_videos if v['media']['uuid'] in seen_media_ids]
                    if len(done_videos) == len(camp_videos):
                        print(f"[TIM][DEBUG] Enviando evento success_impression para campanha {campaign_id}")
                        response = self.api.track_campaign(
                            "success_impression",
                            campaign_id,
                            user_data.get(operator, {}).get('tim_user_id', user_data.get('tim_user_id')),
                            campaign_info['trackingId'],
                            None,
                            token
                        )
                        print(f"[TIM][DEBUG] Resposta evento success_impression: {response}")
                return success

            def process_batch(video_batch, user_data, completed_campaigns, status_msg):
                for video in video_batch:
                    if not self.active_tasks.get(user_id):
                        return
                    process_video(video['campaign'], video['media'], user_data, completed_campaigns, status_msg)

            try:
                self.active_tasks[user_id] = True
                
                status_msg = None
                if not silent_mode:
                    status_msg = self.bot.send_message(chat_id, "🔍 Procurando campanhas disponíveis...")

                # Inicialização das campanhas
                user_operator = self.db.get_user_operator(user_id)
                campaign_videos = {}
                all_videos = []
                seen_media_ids = set()

                if user_operator == "vivo":
                    from config_vivo import MOBILE_CAMPAIGN_ENDPOINT, RESPESCAGEM_CAMPAIGN_ENDPOINT
                    vivo_campaigns = [
                        ("camp1", MOBILE_CAMPAIGN_ENDPOINT),
                        ("camp2", RESPESCAGEM_CAMPAIGN_ENDPOINT)
                    ]
                    for camp_name, endpoint in vivo_campaigns:
                        campaign_videos[camp_name] = 0
                        print(f"Processando {camp_name} (Vivo) com endpoint: {endpoint}")
                        operator = user_data.get('operator')
                        authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                        wallet_id = user_data.get(operator, {}).get('wallet_id', user_data.get('wallet_id'))
                        response = self.api.get_campaigns(authorization, wallet_id, endpoint)
                        campaigns = []
                        if response['success']:
                            if 'data' in response and 'campaigns' in response['data']:
                                campaigns = response['data']['campaigns']
                            elif 'campaigns' in response:
                                campaigns = response['campaigns']
                        if campaigns:
                            print(f"✅ {len(campaigns)} campanhas encontradas para {camp_name}")
                            for campaign in campaigns:
                                media_list = campaign.get('mainData', {}).get('media', [])
                                for media in media_list:
                                    media_id = media.get('uuid')
                                    if media_id not in seen_media_ids:
                                        seen_media_ids.add(media_id)
                                        campaign_videos[camp_name] += 1
                                        all_videos.append({
                                            'campaign': campaign,
                                            'media': media
                                        })
                            print(f"{camp_name} tem {campaign_videos[camp_name]} vídeos")
                        else:
                            print(f"Erro ao obter {camp_name}: {response.get('error', 'Erro desconhecido')}")
                elif user_operator == "claro":
                    for i in range(len(CAMPAIGN_IDS)):
                        camp_name = f"camp{i+1}"
                        campaign_videos[camp_name] = 0
                    for i, campaign_id in enumerate(CAMPAIGN_IDS):
                        camp_name = f"camp{i+1}"
                        print(f"Processando {camp_name} (Claro) com ID: {campaign_id}")
                        from config import OPERATORS
                        base_url = OPERATORS["claro"]["api_base_url"]
                        endpoint = f"{base_url}/adserver/campaign/v3/{campaign_id}"
                        operator = user_data.get('operator')
                        authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                        # Busca o wallet.id do /hmld para usar como userId
                        hmld = self.api._make_request('GET', 'hmld', headers={'x-authorization': authorization})
                        claro_wallet_id = ''
                        if hmld.get('success') and 'wallet' in hmld.get('body', {}):
                            claro_wallet_id = hmld['body']['wallet'].get('id', '')
                        headers = {
                            'x-authorization': authorization,
                            'x-artemis-channel-uuid': API_ARTEMIS_CHANNEL_UUID,
                            'x-access-token': API_ACCESS_TOKEN,
                            'x-channel': 'WEB',
                            'X-APP-ID': 'akross_rewardapps',
                            'X-APP-VERSION': '3.1.01'
                        }
                        
                        context_info = {
                            'os': 'WEB',
                            'brand': self.api.user_agent,
                            'manufacturer': 'Win32',
                            'osVersion': 'Win32',
                            'eventDate': str(int(time.time() * 1000)),
                            'battery': '63',
                            'lat': 'Unknown',
                            'long': 'Unknown'
                        }
                        response = self.api._make_request(
                            'POST',
                            f'adserver/campaign/v3/{campaign_id}',
                            headers=headers,
                            data={
                                'userId': claro_wallet_id,
                                'contextInfo': context_info
                            },
                            params={'size': '100'}
                        )
                        if response.get('success') and 'campaigns' in response.get('body', {}):
                            for campaign in response['body']['campaigns']:
                                media_list = campaign.get('mainData', {}).get('media', [])
                                for media in media_list:
                                    media_id = media.get('uuid')
                                    if media_id not in seen_media_ids:
                                        seen_media_ids.add(media_id)
                                        campaign_videos[camp_name] += 1
                                        all_videos.append({
                                            'campaign': campaign,
                                            'media': media
                                        })
                            print(f"{camp_name} tem {campaign_videos[camp_name]} vídeos")
                        else:
                            print(f"Erro ao obter {camp_name}: {response.get('error', 'Erro desconhecido')}")
                elif user_operator == "tim":
                    print("Processando campanhas (TIM)...")
                    operator = user_data.get('operator')
                    authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                    tim_user_id = user_data.get(operator, {}).get('tim_user_id', user_data.get('tim_user_id'))
                    if not tim_user_id:
                        self.bot.send_message(chat_id, "❌ Erro: Não foi possível identificar seu acesso TIM. Por favor, reinicie o login e tente novamente.")
                        self.active_tasks[user_id] = False
                        return
                    response = self.api.get_campaigns(authorization, tim_user_id)
                    if response['success'] and 'campaigns' in response:
                        campaigns = response['campaigns']
                        print(f"✅ {len(campaigns)} campanhas encontradas para TIM")
                        camp_name = "tim_campaigns"
                        campaign_videos[camp_name] = 0
                        for campaign in campaigns:
                            # Agora, cada campaign['medias'] já contém só vídeos válidos
                            for media in campaign.get('medias', []):
                                media_id = media.get('uuid')
                                if media_id not in seen_media_ids:
                                    seen_media_ids.add(media_id)
                                    campaign_videos[camp_name] += 1
                                    all_videos.append({
                                        'campaign': campaign,
                                        'media': media
                                    })
                        print(f"TIM tem {campaign_videos[camp_name]} vídeos")
                    else:
                        print(f"Erro ao obter campanhas TIM: {response.get('error', 'Erro desconhecido')}")
                else:
                    # Se não for a operadora logada, ignora
                    pass

                if not all_videos:
                    if not silent_mode:
                        self.bot.edit_message_text("😢 Nenhuma campanha disponível no momento.", 
                                                chat_id, status_msg.message_id)
                    self.active_tasks[user_id] = False
                    return

                summary = "📋 CAMPANHAS ENCONTRADAS:\n\n"
                total_videos = 0
                for camp_name, count in campaign_videos.items():
                    summary += f"📺 {camp_name}: {count} vídeos\n"
                    total_videos += count
                summary += f"\n🎯 Total: {total_videos} vídeos\n\n"
                summary += "🚀 Iniciando coleta de moedas!"
                
                if not silent_mode:
                    self.bot.edit_message_text(summary, chat_id, status_msg.message_id)
                    time.sleep(2)
                    status_msg = self.bot.send_message(chat_id, "🎮 Processando campanhas...")

                completed_campaigns = {
                    'count': 0,
                    'total': len(all_videos),
                    'lock': threading.Lock()
                }

                # Processamento em batches
                if len(all_videos) <= 10:
                    video_batches = [all_videos]
                else:
                    batch_size = max(1, len(all_videos) // 10)
                    video_batches = [all_videos[i:i + batch_size] for i in range(0, len(all_videos), batch_size)]
                
                threads = []
                for i, batch in enumerate(video_batches):
                    if not self.active_tasks.get(user_id):
                        break
                        
                    print(f"Iniciando batch {i+1}/{len(video_batches)} com {len(batch)} vídeos")
                        
                    thread = threading.Thread(
                        target=process_batch,
                        args=(batch, user_data, completed_campaigns, status_msg)
                    )
                    thread.daemon = True
                    threads.append(thread)
                    thread.start()
                    
                    time.sleep(0.5)

                for i, thread in enumerate(threads):
                    thread.join(timeout=300)
                    print(f"Thread {i+1} finalizada")

                # Obtém o saldo final
                operator = user_data.get('operator')
                authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
                final_balance_response = self.api.get_balance(authorization)
                final_balance = final_balance_response['balance'] if final_balance_response['success'] else 0
                
                # Calcula moedas ganhas
                coins_earned = final_balance - initial_balance
                
                if not silent_mode:
                    # Relatório final aprimorado
                    final_text = (f"🎉 COLETA DE MOEDAS CONCLUÍDA!\n\n"
                                f"✅ Progresso: 100%\n"
                                f"🟦🟦🟦🟦🟦🟦🟦🟦🟦🟦\n\n"
                                f"📊 RELATÓRIO:\n"
                                f"💎 Moedas iniciais: {initial_balance}\n"
                                f"⭐ Moedas coletadas: +{coins_earned}\n"
                                f"💰 Saldo atual: {final_balance}\n\n"
                                f"📺 Campanhas: {completed_campaigns['count']}/{completed_campaigns['total']}\n\n"
                                f"💡 Dica: Use o menu de Pacotes para gastar suas moedas!")
                    
                    self.bot.edit_message_text(final_text, chat_id, status_msg.message_id)
                
                self.db.update_stats('campaigns_completed', completed_campaigns['count'])

            except Exception as e:
                print(f"Erro nas campanhas: {str(e)}")
                if not silent_mode:
                    try:
                        self.bot.edit_message_text("😔 Ocorreu um erro nas campanhas.", chat_id, status_msg.message_id)
                    except:
                        pass
                
            finally:
                self.active_tasks[user_id] = False
                # Aplica cooldown para evitar spam de cliques
                if not silent_mode:
                    time.sleep(CAMPAIGN_COOLDOWN)
                
        # Valida sessão antes de executar a ação
        if silent_mode:
            # Em modo silencioso, executa diretamente
            return _start_campaigns(message)
        else:
            # Em modo normal, valida sessão primeiro
            return self.validate_session_before_action(message, _start_campaigns)           
             
      
    def create_menu(self, menu_type):
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        if menu_type == "pix":
            # Substitui o valor do PIX no texto do botão
            menus = MENU_TYPES.copy()
            menus["pix"] = [
                [f"💳 Pagar R$ {PIX_PRICE:.2f}", "📱 Status da Assinatura"],
                ["📋 Histórico", "🔙 Voltar ao Menu"]
            ]
        elif menu_type == "main":
            # Adiciona apenas o botão Sair no menu principal
            menus = MENU_TYPES.copy()
            main_menu = menus.get(menu_type, []).copy()
            main_menu.append(["🚪 Sair"])
            menus[menu_type] = main_menu
        else:
            menus = MENU_TYPES
        
        for row in menus.get(menu_type, []):
            markup.row(*[telebot.types.KeyboardButton(item) for item in row])
        return markup

    def create_operator_menu(self):
        """Cria menu de seleção de operadora"""
        from config import OPERATORS
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        # Cria botões para cada operadora
        for operator_key, operator_data in OPERATORS.items():
            button_text = f"{operator_data['emoji']} {operator_data['name']}"
            markup.row(telebot.types.KeyboardButton(button_text))
        
        return markup

    def create_menu_with_price(self, menu_type, price, show_back_button=True):
        """Cria menu com preço personalizado para revendedores. Se show_back_button=False, não inclui o botão 'Voltar ao Menu' no menu PIX."""
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        if menu_type == "pix":
            # Substitui o valor do PIX no texto do botão com o valor personalizado
            if show_back_button:
                menus = MENU_TYPES.copy()
                menus["pix"] = [
                    [f"💳 Pagar R$ {price:.2f}", "📱 Status da Assinatura"],
                    ["📋 Histórico", "🔙 Voltar ao Menu"]
                ]
            else:
                menus = MENU_TYPES.copy()
                menus["pix"] = [
                    [f"💳 Pagar R$ {price:.2f}", "📱 Status da Assinatura"],
                    ["📋 Histórico"]
                ]
        else:
            menus = MENU_TYPES
        
        for row in menus.get(menu_type, []):
            markup.row(*[telebot.types.KeyboardButton(item) for item in row])
        return markup

    # Substitua o método show_pix_menu pelo código abaixo na classe BotSession
    def show_pix_menu(self, message):
        """Mostra menu PIX com preço personalizado se cliente tiver revendedor"""
        user_id = str(message.from_user.id)
        subscription = self.db.check_subscription(user_id)
        
        # Busca o revendedor do cliente e o preço personalizado
        reseller_id = self.db.get_client_reseller(user_id)
        display_price = PIX_PRICE  # Valor padrão
        
        # Se tiver revendedor, busca o preço personalizado
        if reseller_id:
            custom_price = self.db.get_reseller_custom_price(reseller_id)
            if custom_price is not None:
                display_price = custom_price
        
        # Busca o telefone do usuário para exibir no status
        phone = self.db.get_user_phone(user_id)
        
        msg = "💰 Pagamento\n\n"
        msg += f"🆔 ID: {user_id}\n"
        msg += f"📱 Telefone: {phone if phone else 'Não cadastrado'}\n\n"
        if subscription["active"]:
            msg += f"✅ Sua assinatura está ATIVA!\n"
            msg += f"⏳ Expira em {subscription['days_left']} dias\n"
            if subscription["is_trial"]:
                msg += f"🎁 (Período de teste)\n"
            # Se assinatura está ativa, pode mostrar o botão voltar
            markup = self.create_menu_with_price("pix", display_price, show_back_button=True)
        else:
            msg += f"❌ Assinatura EXPIRADA\n"
            msg += f"💵 Valor: R$ {display_price:.2f}\n"
            msg += f"📅 Duração: {SUBSCRIPTION_DAYS} dias\n"
            # Se assinatura está expirada, NÃO mostra o botão voltar
            markup = self.create_menu_with_price("pix", display_price, show_back_button=False)
        
        self.bot.send_message(message.chat.id, msg, reply_markup=markup)

    # Modifique também o método process_pix_payment para usar o preço personalizado
    def process_pix_payment(self, message):
        """Processa pagamento PIX com o preço personalizado do revendedor"""
        # Proteção anti-autoclick
        user_id = str(message.from_user.id)
        if self.check_button_spam(user_id, "pix_payment"):
            self.bot.send_message(message.chat.id, MESSAGES.get('too_many_clicks', "⚠️ Aguarde um momento..."))
            return
            
        phone = self.db.get_user_phone(user_id)
        
        if not phone:
            self.bot.send_message(message.chat.id, "❌ Erro ao buscar seus dados.")
            return
        
        subscription = self.db.check_subscription(user_id)
        if subscription["active"] and subscription["days_left"] > PIX_RENEWAL_MIN_DAYS:
            self.bot.send_message(
                message.chat.id, 
                f"⚠️ Você ainda tem {subscription['days_left']} dias de assinatura!\n\n"
                f"📅 Você só pode renovar quando tiver {PIX_RENEWAL_MIN_DAYS} dias ou menos restantes.\n\n"
                f"💡 Volte em breve para renovar sua assinatura!",
                reply_markup=self.create_menu("pix")
            )
            return
        
        msg = self.bot.send_message(message.chat.id, "⏳ Gerando PIX...")
        
        # Verificar se o cliente tem um revendedor associado antes de gerar o pagamento
        reseller_id = self.db.get_client_reseller(user_id)

        user_operator = self.db.get_user_operator(user_id)  # <-- Correção: define user_operator antes do uso

        # O valor específico não é passado, para que o método create_pix_payment
        # busque o valor personalizado do revendedor se aplicável
        payment = self.pix.create_pix_payment(user_id, phone)
        
        if payment["success"]:
            payment_id = payment["payment_id"]
            
            # CORREÇÃO: Armazenar se o token personalizado foi usado e o ID do revendedor
            self.db.add_payment(
                user_id, 
                payment_id, 
                payment["amount"], 
                payment.get("custom_token_used", False),
                reseller_id
            )
            
            # Armazenar o código PIX temporariamente no objeto users
            users = self.db.load_users()
            if user_id not in users:
                users[user_id] = {}
            users[user_id]['temp_pix_code'] = payment["qr_code"]
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(payment["qr_code"])
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            bio = BytesIO()
            img.save(bio, 'PNG')
            bio.seek(0)
            
            # Adiciona o código diretamente na caption com o valor correto
            caption = f"💳 PIX para Pagamento\n"
            caption += f"💰 Valor: R$ {payment['amount']:.2f}\n"
            caption += f"⏱ Este PIX é válido por {PIX_VALIDITY_MINUTES} minutos\n\n"
            caption += f"📋 Código PIX:\n<code>{payment['qr_code']}</code>\n\n"
            
            # CORREÇÃO: Informar se o token do revendedor foi usado
            if payment.get("custom_token_used", False) and reseller_id:
                caption += f"💼 Pagamento processado pelo revendedor\n\n"
                
            caption += f"✅ O pagamento será verificado automaticamente."
            
            # Envia QR code com o código PIX na legenda
            sent_message = self.bot.send_photo(
                message.chat.id, 
                bio, 
                caption=caption, 
                parse_mode="HTML"
            )
            
            # Armazena informações da mensagem para referência futura
            message_info = {
                'chat_id': message.chat.id,
                'message_id': sent_message.message_id,
                'caption': caption
            }
            users[user_id]['pix_message'] = message_info
                    
        if user_operator == "tim" and 'user_id' in response['data'] and response['data']['user_id']:
            users[user_id]['tim_user_id'] = response['data']['user_id']
                        
            self.db.save_users(users)
            self.bot.delete_message(message.chat.id, msg.message_id)
            
            # Apenas registra o pagamento - o webhook cuidará da verificação
            self.active_payment_checks[payment_id] = False
            
        else:
            self.bot.edit_message_text(f"❌ Erro: {payment.get('error', 'Erro desconhecido')}", 
                                    message.chat.id, msg.message_id)
            
        # Limpar o ID da mensagem PIX anterior
        if user_id in users and 'pix_message_id' in users[user_id]:
            del users[user_id]['pix_message_id']
            self.db.save_users(users)

    def check_subscription_access(self, user_id):
        """Verifica se usuário tem acesso (assinatura ativa e não suspenso)"""
        subscription = self.db.check_subscription(user_id)
        return subscription["active"] and not subscription.get("suspenso", False)

    def show_expired_message(self, message):
        """Mostra mensagem de assinatura expirada"""
        msg = MESSAGES.get('subscription_expired', "⚠️ Sua assinatura expirou!").format(
            PIX_PRICE, SUBSCRIPTION_DAYS
        )
        self.bot.send_message(message.chat.id, msg)
        
        # Mostra menu de pagamento após mensagem de expiração
        self.show_pix_menu(message)

    def show_payment_history(self, message):
        """Mostra histórico de pagamentos"""
        user_id = str(message.from_user.id)
        history = self.db.get_payment_history(user_id, 5)
        
        if not history:
            self.bot.send_message(message.chat.id, "📭 Sem histórico de pagamentos")
            return
        
        msg = "📋 Histórico de Pagamentos\n\n"
        for p in history:
            date = datetime.fromisoformat(p['date']).strftime("%d/%m/%Y %H:%M")
            status = "✅" if p['status'] == 'approved' else "⏳" if p['status'] == 'pending' else "❌"
            msg += f"{status} R$ {p['amount']:.2f} - {date}\n"
        
        self.bot.send_message(message.chat.id, msg)

    def process_first_phone(self, message):
        """Processa telefone para primeiro acesso ou mudança de número"""
        # Ignora comandos do menu enquanto espera número
        menu_commands = [
            "💎 Ver Moedas", "🚀 Começar Campanhas", "🎁 Pacotes Disponíveis", "🤖 Coleta Automática", "📊 Status", "💰 Pagamento",
            "📱 Status da Assinatura", "📋 Histórico", "✅ Ativar Coleta", "❌ Desativar Coleta", "🔙 Voltar ao Menu"
        ]
        if message.text in menu_commands:
            msg = self.bot.send_message(message.chat.id, "❌ Digite seu número de telefone para continuar:")
            self.bot.register_next_step_handler(msg, self.process_first_phone)
            return
        
        if not message.text:
            self.bot.send_message(message.chat.id, "❌ Digite um número válido:")
            self.bot.register_next_step_handler(message, self.process_first_phone)
            return
        
        # Limpeza e log do número recebido
        raw_phone = message.text.strip()
        phone_number = ''.join(filter(str.isdigit, raw_phone))
        print(f"[DEBUG] Número recebido do usuário: '{raw_phone}' | Limpo: '{phone_number}'")
        
        if phone_number.startswith('55') and len(phone_number) > 11:
            phone_number = phone_number[2:]
        
        if not phone_number.isdigit() or len(phone_number) != 11:
            self.bot.send_message(message.chat.id, 
                MESSAGES.get('phone_invalid', "⚠️ Número inválido '{}'. Deve ter 11 dígitos.").format(raw_phone))
            # Reinicia sessão: volta para seleção de operadora
            markup = self.create_operator_menu()
            self.bot.send_message(message.chat.id, "🔄 Sessão reiniciada. Selecione sua operadora:", reply_markup=markup)
            self.bot.register_next_step_handler(message, self.process_operator_selection)
            return
        
        self.db.save_user_phone(str(message.from_user.id), phone_number)
        
        # Configura a API com a operadora do usuário
        user_id = str(message.from_user.id)
        user_operator = self.db.get_user_operator(user_id)
        self.api.configure_for_operator(user_operator)
        print(f"[BOT] Chamando request_pin da API para operadora: {user_operator}, número: {phone_number}")
        response = self.api.request_pin(phone_number)
        print(f"[BOT] Resposta do request_pin: {response}")
        # CORREÇÃO: Aceitar sucesso da TIM (code PINCODE_SENDED)
        if response.get('success') or response.get('code') == "PINCODE_SENDED":
            msg_text = response.get('message', MESSAGES.get('pin_required', "💌 Digite o código recebido:"))
            import telebot.types
            markup = telebot.types.InlineKeyboardMarkup()
            msg = self.bot.send_message(message.chat.id, msg_text, reply_markup=markup)
            self.bot.register_next_step_handler(msg, self.process_first_pin_code, phone_number)
        else:
            # Tenta extrair mensagem amigável do JSON de resposta
            error_msg = (
                response.get('error') or
                (response.get('body', {}).get('message') if isinstance(response.get('body'), dict) else None) or
                None
            )
            # Se vier um JSON na resposta, tenta extrair a mensagem
            if not error_msg and response.get('response'):
                import json
                try:
                    resp_json = json.loads(response['response'])
                    error_msg = resp_json.get('message')
                except Exception:
                    error_msg = None
            if not error_msg:
                error_msg = 'Erro desconhecido'
            # NOVO FLUXO: Se for erro da Claro sobre aguardar 24 horas, volta para seleção de operadora
            claro_erro_24h = "é necessário aguardar 24 horas para utilizar o Prezão Free"
            suspenso_erro = "As atividades relacionadas a sua conta foram temporariamente suspensas, tente novamente mais tarde."
            if error_msg and (claro_erro_24h in error_msg or suspenso_erro in error_msg):
                markup = self.create_operator_menu()
                self.bot.send_message(message.chat.id, f"😔 Erro ao enviar código: {error_msg}\n\nVoltando para seleção de operadora...", reply_markup=markup)
                self.bot.register_next_step_handler(message, self.process_operator_selection)
                return
            # Fluxo padrão para outros erros
            self.bot.send_message(message.chat.id, f"😔 Erro ao enviar código: {error_msg}\nDigite seu número novamente:")
            self.bot.register_next_step_handler(message, self.process_first_phone)
            

    
    def process_change_phone(self, message):
        """Processa a troca de número para um usuário já logado"""
        # Primeiro rotaciona o proxy
        self.rotate_proxy_with_feedback(message.chat.id)
        
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
                
        if not message.text:
            self.bot.send_message(message.chat.id, "❌ Digite um número válido:")
            self.bot.register_next_step_handler(message, self.process_change_phone)
            return
            
        phone_number = message.text.strip()
        phone_number = ''.join(filter(str.isdigit, phone_number))
        
        if phone_number.startswith('55') and len(phone_number) > 11:
            phone_number = phone_number[2:]
        
        if not phone_number.isdigit() or len(phone_number) != 11:
            self.bot.send_message(message.chat.id, 
                                 MESSAGES.get('phone_invalid', "⚠️ Número inválido {}. Deve ter 11 dígitos.").format(phone_number))
            # Reinicia sessão: volta para seleção de operadora
            markup = self.create_operator_menu()
            self.bot.send_message(message.chat.id, "🔄 Sessão reiniciada. Selecione sua operadora:", reply_markup=markup)
            self.bot.register_next_step_handler(message, self.process_operator_selection)
            return
        
        user_id = str(message.from_user.id)
        users = self.db.load_users()
        
        # Salva o novo número e mantém os outros dados
        if user_id in users:
            old_number = users[user_id].get('phone_number', 'não cadastrado')
            users[user_id]['phone_number'] = phone_number
            self.db.save_users(users)
            
            self.bot.send_message(message.chat.id, 
                               f"📱 Número alterado com sucesso!\n\n"
                               f"Antigo: {old_number}\n"
                               f"Novo: {phone_number}\n\n"
                               f"✅ Enviando código de verificação...")
            
            # Configura a API com a operadora do usuário
            user_operator = self.db.get_user_operator(user_id)
            self.api.configure_for_operator(user_operator)
            
            response = self.api.request_pin(phone_number)
            if response.get('success'):
                msg = self.bot.send_message(message.chat.id, MESSAGES.get('pin_required', "💌 Digite o código recebido:"))
                self.bot.register_next_step_handler(msg, self.process_existing_pin_code, phone_number)
            else:
                error_msg = (
                    response.get('error') or
                    (response.get('body', {}).get('message') if isinstance(response.get('body'), dict) else None) or
                    'Erro desconhecido'
                )
                self.bot.send_message(message.chat.id, f"😔 Erro ao enviar código: {error_msg}")
                import telebot.types
                markup = telebot.types.InlineKeyboardMarkup()
                msg = self.bot.send_message(message.chat.id, "🔄 Digite seu celular novamente ou reinicie a sessão:", reply_markup=markup)
                self.bot.register_next_step_handler(msg, self.process_change_phone)
        else:
            # Se por algum motivo o usuário não estiver no banco, trata como primeiro acesso
            self.db.save_user_phone(user_id, phone_number)
            
            self.bot.send_message(message.chat.id, MESSAGES.get('phone_sending', "📱 Enviando código para {}...").format(phone_number))
            
            response = self.api.request_pin(phone_number)
            if response.get('success'):
                msg = self.bot.send_message(message.chat.id, MESSAGES.get('pin_required', "💌 Digite o código recebido:"))
                self.bot.register_next_step_handler(msg, self.process_first_pin_code, phone_number)
            else:
                error_msg = (
                    response.get('error') or
                    (response.get('body', {}).get('message') if isinstance(response.get('body'), dict) else None) or
                    'Erro desconhecido'
                )
                self.bot.send_message(message.chat.id, f"😔 Erro ao enviar código: {error_msg}\nDigite seu número novamente:")
                self.bot.register_next_step_handler(message, self.process_change_phone)


    def process_first_pin_code(self, message, phone_number):
        """Processa PIN para primeiro acesso"""
        from config import TRIAL_DAYS
        # Ignora comandos do menu enquanto espera código
        menu_commands = [
            "💎 Ver Moedas", "🚀 Começar Campanhas", "🎁 Pacotes Disponíveis", "🤖 Coleta Automática", "📊 Status", "💰 Pagamento",
            "📱 Status da Assinatura", "📋 Histórico", "✅ Ativar Coleta", "❌ Desativar Coleta", "🔙 Voltar ao Menu"
        ]
        if message.text in menu_commands:
            msg = self.bot.send_message(message.chat.id, "❌ Digite o código recebido para continuar:")
            self.bot.register_next_step_handler(msg, self.process_first_pin_code, phone_number)
            return
                
        if not message.text:
            self.bot.send_message(message.chat.id, "❌ Digite o código:")
            self.bot.register_next_step_handler(message, self.process_first_pin_code, phone_number)
            return
                
        # Verifica se o usuário quer trocar o número
        if message.text.lower() in ["trocar número", "trocar numero", "mudar numero", "mudar número"]:
            markup = self.create_operator_menu()
            msg = self.bot.send_message(message.chat.id, "🔄 Selecione sua operadora:", reply_markup=markup)
            self.bot.register_next_step_handler(msg, self.process_operator_selection)
            return
                
        pin_code = message.text.strip()

        # Se o usuário digitar um telefone (11 dígitos), oriente a trocar número
        if pin_code.isdigit() and len(pin_code) == 11:
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(telebot.types.KeyboardButton("Trocar número"))
            msg = self.bot.send_message(
                message.chat.id,
                "📱 Parece que você digitou um número de telefone, mas o bot está esperando o código PIN.\n\nClique em 'Trocar número' para voltar ao início.",
                reply_markup=markup
            )
            self.bot.register_next_step_handler(msg, self.process_first_pin_code, phone_number)
            return

        # Se não for PIN de 6 dígitos, continue pedindo o PIN normalmente
        if not pin_code.isdigit() or len(pin_code) != 6:
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(telebot.types.KeyboardButton("Trocar número"))
            msg = self.bot.send_message(
                message.chat.id,
                "⚠️ Código inválido. Digite novamente ou escolha trocar número:",
                reply_markup=markup
            )
            self.bot.register_next_step_handler(msg, self.process_first_pin_code, phone_number)
            return

        # Configura a API com a operadora do usuário
        user_id = str(message.from_user.id)
        user_operator = self.db.get_user_operator(user_id)
        self.api.configure_for_operator(user_operator)

        response = self.api.verify_pin(phone_number, pin_code)
        if response['success']:
            users = self.db.load_users()
            user_id = str(message.from_user.id)
            user_operator = self.db.get_user_operator(user_id)
            # Adiciona log para depuração do wallet_id da Vivo
            if user_operator == "vivo":
                wallet_id = response['data'].get('wallet_id', '')
                print(f"[DEBUG] wallet_id retornado da Vivo: {wallet_id}")
            # LOG ESPECIAL PARA CLARO
            if user_operator == "claro":
                print(f"[DEBUG][CLARO] Token recebido após login: {response['data'].get('authorization')}")
            # Se o usuário já existe, apenas atualiza o operador e o número, mantendo saldo e assinatura
            if user_id in users:
                users[user_id]['phone_number'] = phone_number
                users[user_id]['operator'] = user_operator
                users[user_id]['user_id'] = user_id  # Garante consistência
                # Bloco por operadora
                if user_operator not in users[user_id]:
                    users[user_id][user_operator] = {}
                # --- AJUSTE: Sempre sincroniza o token da raiz e da operadora ---
                users[user_id][user_operator]['authorization'] = response['data']['authorization']
                users[user_id]['authorization'] = response['data']['authorization']
                # -------------------------------------------------------------
                users[user_id][user_operator]['transaction_id'] = response['data']['transaction_id']
                if user_operator == "vivo":
                    users[user_id][user_operator]['wallet_id'] = response['data'].get('wallet_id', '')
                if user_operator == "tim" and 'user_id' in response['data'] and response['data']['user_id']:
                    users[user_id][user_operator]['tim_user_id'] = response['data']['user_id']
                # CORREÇÃO: Salvar identificador único da Claro
                if user_operator == "claro" and 'user_id' in response['data'] and response['data']['user_id']:
                    users[user_id][user_operator]['claro_user_id'] = response['data']['user_id']
                self.db.save_users(users)
                self.db.save_user_operator(user_id, user_operator)
                # NÃO CONCEDE TRIAL NOVAMENTE!
                if user_operator == "claro":
                    print(f"[DEBUG][CLARO] Dicionário do usuário após login: {users[user_id]}")
            else:
                users[user_id] = {
                    'phone_number': phone_number,
                    'operator': user_operator,
                    'user_id': user_id,
                    user_operator: {
                        # --- AJUSTE: Sempre sincroniza o token da raiz e da operadora ---
                        'authorization': response['data']['authorization'],
                        'transaction_id': response['data']['transaction_id'],
                        # -------------------------------------------------------------
                    },
                    # --- AJUSTE: Sempre sincroniza o token da raiz e da operadora ---
                    'authorization': response['data']['authorization']
                    # -------------------------------------------------------------
                }
                if user_operator == "vivo":
                    users[user_id][user_operator]['wallet_id'] = response['data'].get('wallet_id', '')
                if user_operator == "tim" and 'user_id' in response['data'] and response['data']['user_id']:
                    users[user_id][user_operator]['tim_user_id'] = response['data']['user_id']
                # CORREÇÃO: Salvar identificador único da Claro
                if user_operator == "claro" and 'user_id' in response['data'] and response['data']['user_id']:
                    users[user_id][user_operator]['claro_user_id'] = response['data']['user_id']
                self.db.save_users(users)
                self.db.save_user_operator(user_id, user_operator)
                import datetime as _dt
                trial_end = _dt.datetime.now() + _dt.timedelta(days=TRIAL_DAYS)
                self.db.set_trial(user_id, trial_end)
                if user_operator == "claro":
                    print(f"[DEBUG][CLARO] Dicionário do usuário novo após login: {users[user_id]}")
            print(f"[DEBUG][CLARO] Fluxo pós-login concluído para usuário {user_id}")
            # Limpa o estado do usuário após login/cadastro
            try:
                self.state_storage.reset_state(message.from_user.id, message.chat.id)
            except Exception:
                pass
            
            # CORREÇÃO: Processar associação pendente com revendedor
            # Verifica se há uma associação pendente com algum revendedor
            reseller_id = self.db.check_pending_association(user_id)
            if reseller_id:
                # Processa a associação pendente
                success, message_text = self.db.process_pending_association(user_id)
                if success:
                    self.db.increment_reseller_trial(reseller_id)  # Incrementa teste
                    self.bot.send_message(
                        message.chat.id,
                        "✅ Você foi associado ao revendedor com sucesso! Aproveite seu teste!"
                    )
                    try:
                        users = self.db.load_users()
                        nome_cliente = users.get(user_id, {}).get('phone_number', f'ID {user_id}')
                        self.revenda.bot.send_message(
                            int(reseller_id),
                            f"👤 Novo cliente entrou pelo seu link de revenda!\n\nID: <code>{user_id}</code>\nTelefone: {nome_cliente}\n\nAcompanhe seus clientes no painel de revenda.",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        print(f"Erro ao notificar revendedor: {e}")
                else:
                    self.bot.send_message(
                        message.chat.id,
                        f"❌ {message_text}"
                    )
            
            # Após o login bem-sucedido
            welcome_message = self.create_welcome_message(users[user_id])
            markup = self.create_menu("main")
            self.bot.send_message(message.chat.id, 
                welcome_message + f"\n\n🎁 Você ganhou {TRIAL_DAYS} dias grátis para testar!", 
                reply_markup=markup)
        else:
            error_msg = response.get('error', 'Erro desconhecido')
            
            # Cria teclado com opção para trocar número
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(telebot.types.KeyboardButton("Trocar número"))
            
            self.bot.send_message(message.chat.id, 
                                f"😔 Erro ao verificar código: {error_msg}\n\n"
                                f"Você pode tentar novamente ou trocar de número.",
                                reply_markup=markup)
            
            self.bot.register_next_step_handler(message, self.process_first_pin_code, phone_number)

    def process_existing_pin_code(self, message, phone_number):
        """Processa PIN para usuários existentes"""
        # Ignora comandos do menu enquanto espera código
        menu_commands = [
            "💎 Ver Moedas", "🚀 Começar Campanhas", "🎁 Pacotes Disponíveis", "🤖 Coleta Automática", "📊 Status", "💰 Pagamento",
            "📱 Status da Assinatura", "📋 Histórico", "✅ Ativar Coleta", "❌ Desativar Coleta", "🔙 Voltar ao Menu"
        ]
        if message.text in menu_commands:
            msg = self.bot.send_message(message.chat.id, "❌ Digite o código recebido para continuar:")
            self.bot.register_next_step_handler(msg, self.process_existing_pin_code, phone_number)
            return
                
        if not message.text:
            self.bot.send_message(message.chat.id, "❌ Digite o código:")
            self.bot.register_next_step_handler(message, self.process_existing_pin_code, phone_number)
            return
            
        # Verifica se o usuário quer trocar o número
        if message.text.lower() in ["trocar número", "trocar numero", "mudar numero", "mudar número"]:
            markup = self.create_operator_menu()
            msg = self.bot.send_message(message.chat.id, "🔄 Selecione sua operadora:", reply_markup=markup)
            self.bot.register_next_step_handler(msg, self.process_operator_selection)
            return
                
        pin_code = message.text.strip()
        if not pin_code.isdigit() or len(pin_code) != 6:
            # Cria teclado com opção para trocar número
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(telebot.types.KeyboardButton("Trocar número"))
            
            msg = self.bot.send_message(message.chat.id, 
                                    "⚠️ Código inválido. Digite novamente ou escolha trocar número:", 
                                    reply_markup=markup)
            self.bot.register_next_step_handler(msg, self.process_existing_pin_code, phone_number)
            return

        # Configura a API com a operadora do usuário
        user_id = str(message.from_user.id)
        user_operator = self.db.get_user_operator(user_id)
        self.api.configure_for_operator(user_operator)

        response = self.api.verify_pin(phone_number, pin_code)
        if response['success']:
            users = self.db.load_users()
            user_id = str(message.from_user.id)
            # Certifica-se de que o dicionário do usuário existe
            if user_id not in users:
                users[user_id] = {}
            users[user_id].update({
                'phone_number': phone_number,  # Atualiza ou define o número
                'transaction_id': response['data']['transaction_id'],
                'authorization': response['data']['authorization'],
                'user_id': user_id,  # Corrigir: sempre o ID do Telegram
                'wallet_id': response['data'].get('wallet_id', '')
            })
            # Salva o tim_user_id se for TIM
            if user_operator == "tim" and 'user_id' in response['data'] and response['data']['user_id']:
                users[user_id]['tim_user_id'] = response['data']['user_id']
            # --- CORREÇÃO: Salva o authorization na raiz também ---
            users[user_id]['authorization'] = response['data']['authorization']
            # ---------------------------------------------------
            self.db.save_users(users)
            # Limpa o estado do usuário após login/cadastro
            try:
                self.state_storage.reset_state(message.from_user.id, message.chat.id)
            except Exception:
                pass
            
            # CORREÇÃO: Processar associação pendente com revendedor
            # Verifica se há uma associação pendente com algum revendedor
            reseller_id = self.db.check_pending_association(user_id)
            if reseller_id:
                # Processa a associação pendente
                success, message_text = self.db.process_pending_association(user_id)
                if success:
                    self.db.increment_reseller_trial(reseller_id)  # Incrementa teste
                    self.bot.send_message(
                        message.chat.id,
                        "✅ Você foi associado ao revendedor com sucesso! Aproveite seu teste!"
                    )
                    
                    # REMOVIDO: Não adiciona mais crédito, agora deduz na função process_pending_association
                else:
                    self.bot.send_message(
                        message.chat.id,
                        f"❌ {message_text}"
                    )
            
            # Após o login bem-sucedido
            welcome_message = self.create_welcome_message(users[user_id])
            markup = self.create_menu("main")
            
            subscription = self.db.check_subscription(user_id)
            if subscription["active"]:
                self.bot.send_message(message.chat.id, welcome_message, reply_markup=markup)
            else:
                self.bot.send_message(message.chat.id, 
                                    welcome_message + "\n\n⚠️ Sua assinatura expirou.", 
                                    reply_markup=markup)
        else:
            error_msg = response.get('error', 'Erro desconhecido')
            
            # Cria teclado com opção para trocar número
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(telebot.types.KeyboardButton("Trocar número"))
            
            self.bot.send_message(message.chat.id, 
                                f"😔 Erro ao verificar código: {error_msg}\n\n"
                                f"Você pode tentar novamente ou trocar de número.",
                                reply_markup=markup)
            
            self.bot.register_next_step_handler(message, self.process_existing_pin_code, phone_number)

           
    def check_balance(self, message):
        """Verifica saldo de moedas"""
        def _check_balance(message):
            # Proteção anti-autoclick
            user_id = str(message.from_user.id)
            if self.check_button_spam(user_id, "check_balance"):
                self.bot.send_message(message.chat.id, MESSAGES.get('too_many_clicks', "⚠️ Aguarde um momento..."))
                return
                
            users = self.db.load_users()
            
            if user_id not in users:
                self.bot.send_message(message.chat.id, "🔐 Você precisa fazer login primeiro!")
                return
            
            if not self.check_subscription_access(user_id):
                self.show_expired_message(message)
                return
                
            user_data = users[user_id]
            
            # Configura a API com a operadora do usuário
            user_operator = self.db.get_user_operator(user_id)
            self.api.configure_for_operator(user_operator)
            
            operator = user_data.get('operator')
            authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
            response = self.api.get_balance(authorization)
            
            if response['success']:
                markup = self.create_menu("main")
                self.bot.send_message(message.chat.id, 
                                    f"💎 Suas moedas: {response['balance']}", 
                                    reply_markup=markup)
            else:
                error_msg = response.get('error', 'Erro desconhecido')
                self.bot.send_message(message.chat.id, f"😔 Erro ao verificar moedas: {error_msg}")
                
        # Valida sessão antes de executar a ação
        return self.validate_session_before_action(message, _check_balance)

    def list_packages(self, message):        
        """Lista pacotes disponíveis"""
        def _list_packages(message):
            # Proteção anti-autoclick
            user_id = str(message.from_user.id)
            if self.check_button_spam(user_id, "list_packages"):
                self.bot.send_message(message.chat.id, MESSAGES.get('too_many_clicks', "⚠️ Aguarde um momento..."))
                return
                
            users = self.db.load_users()
            
            if user_id not in users:
                self.bot.send_message(message.chat.id, "🔐 Você precisa fazer login primeiro!")
                return
            
            if not self.check_subscription_access(user_id):
                self.show_expired_message(message)
                return
                
            user_data = users[user_id]
            
            # Configura a API com a operadora do usuário
            user_operator = self.db.get_user_operator(user_id)
            self.api.configure_for_operator(user_operator)
            
            operator = user_data.get('operator')
            authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
            response = self.api.get_packages(authorization)
            
            if response['success']:
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
                for package in response['packages']:
                    package_text = f"🎁 {package['fullPrice']} moedas: {package['description']} - {package['id']}"
                    markup.row(telebot.types.KeyboardButton(package_text))
                markup.row(telebot.types.KeyboardButton("🔙 Voltar ao Menu"))
                self.bot.send_message(message.chat.id, "🎁 Pacotes Disponíveis:", reply_markup=markup)
            else:
                error_msg = response.get('error', 'Erro desconhecido')
                self.bot.send_message(message.chat.id, f"😔 Erro ao carregar pacotes: {error_msg}")
                
        # Valida sessão antes de executar a ação
        return self.validate_session_before_action(message, _list_packages)


# Método redeem_package atualizado
    def redeem_package(self, message):        
        """Resgata pacote"""
        def _redeem_package(message):
            # Proteção anti-autoclick
            user_id = str(message.from_user.id)
            if self.check_button_spam(user_id, "redeem_package"):
                self.bot.send_message(message.chat.id, MESSAGES.get('too_many_clicks', "⚠️ Aguarde um momento..."))
                return
                
            users = self.db.load_users()
            
            if user_id not in users:
                self.bot.send_message(message.chat.id, "🔐 Você precisa fazer login primeiro!")
                return
            
            if not self.check_subscription_access(user_id):
                self.show_expired_message(message)
                return
                
            user_data = users[user_id]
            # Extrai o package_id corretamente e converte para int
            package_id = int(message.text.split(" - ")[-1].strip())
            
            # Configura a API com a operadora do usuário
            user_operator = self.db.get_user_operator(user_id)
            self.api.configure_for_operator(user_operator)
            
            operator = user_data.get('operator')
            authorization = user_data.get(operator, {}).get('authorization', user_data.get('authorization'))
            
            # Corrigir apenas para Vivo: passar o número de telefone como segundo parâmetro
            if user_operator == "vivo":
                phone_number = user_data.get('phone_number')
                phone_number = self.api.format_phone_number(phone_number)
                response = self.api.redeem_package(authorization, phone_number, package_id)
            else:
                response = self.api.redeem_package(authorization, package_id, user_id)
            
            if response['success']:
                self.bot.send_message(message.chat.id, "🎉 Pacote resgatado com sucesso!")
            else:
                error_msg = response.get('error', 'Erro desconhecido')
                
                # Verifica se é um erro de limite diário
                if 'limit_reached' in response:
                    self.bot.send_message(message.chat.id, "⚠️ Limite diário de resgate atingido. Você já resgatou todos os pacotes permitidos hoje. Tente novamente amanhã.")
                else:
                    self.bot.send_message(message.chat.id, f"😔 Erro ao resgatar pacote: {error_msg}")
        
        # Valida sessão antes de executar a ação
        return self.validate_session_before_action(message, _redeem_package)

    def show_auto_collect_menu(self, message):
        """Mostra menu de coleta automática"""
        def _show_auto_collect_menu(message):
            user_id = str(message.from_user.id)
            users = self.db.load_users()
            
            if user_id not in users:
                self.bot.send_message(message.chat.id, "🔐 Você precisa fazer login primeiro!")
                return
            
            if not self.check_subscription_access(user_id):
                self.show_expired_message(message)
                return
                
            user_data = users[user_id]
            auto_collect_status = "✅ Ativado" if user_data.get('auto_collect_enabled', False) else "❌ Desativado"
            
            markup = self.create_menu("auto_collect")
            self.bot.send_message(message.chat.id, 
                                f"🤖 Coleta Automática\n\n"
                                f"Status: {auto_collect_status}\n"
                                f"⏰ Horário: {AUTO_COLLECT_TIME}\n\n"
                                f"A coleta automática fará suas campanhas e comprará pacotes automaticamente todos os dias!", 
                                reply_markup=markup)
        
        # Valida sessão antes de executar a ação
        return self.validate_session_before_action(message, _show_auto_collect_menu)

    def toggle_auto_collect(self, message, enable=True):
        """Ativa/desativa coleta automática"""
        def _toggle_auto_collect(message):
            # Proteção anti-autoclick
            user_id = str(message.from_user.id)
            if self.check_button_spam(user_id, "toggle_auto_collect"):
                self.bot.send_message(message.chat.id, MESSAGES.get('too_many_clicks', "⚠️ Aguarde um momento..."))
                return
                
            users = self.db.load_users()
            
            if user_id not in users:
                self.bot.send_message(message.chat.id, "🔐 Você precisa fazer login primeiro!")
                return
            
            if not self.check_subscription_access(user_id):
                self.show_expired_message(message)
                return
                
            users[user_id]['auto_collect_enabled'] = enable
            self.db.save_users(users)
            self.db.set_auto_collect(user_id, enable)
            
            if enable:
                self.auto_collect_running = True
                self.bot.send_message(message.chat.id, f"🤖 Coleta automática ativada! ✅\n"
                                                    f"Suas campanhas serão executadas às {AUTO_COLLECT_TIME} todos os dias!")
            else:
                self.bot.send_message(message.chat.id, "🤖 Coleta automática desativada! ❌")
        
        # Valida sessão antes de executar a ação
        return self.validate_session_before_action(message, _toggle_auto_collect)

    def show_status(self, message):
        """Mostra status do usuário"""
        user_id = str(message.from_user.id)
        users = self.db.load_users()
        
        if user_id not in users:
            self.bot.send_message(message.chat.id, "🔐 Você precisa fazer login primeiro!")
            return
            
        user_data = users[user_id]
        auto_collect = "✅ Ativo" if user_data.get('auto_collect_enabled', False) else "❌ Inativo"
        
        phone_display = user_data.get('phone_number', 'Não cadastrado')

        
        subscription = self.db.check_subscription(user_id)
        sub_status = "✅ Ativa" if subscription["active"] else "❌ Expirada"
        
        status_text = (f"📊 STATUS DA CONTA\n\n"
                      f"📱 Telefone: {phone_display}\n"
                      f"👑 Assinatura: {sub_status}\n"
                      f"⏳ Dias restantes: {subscription['days_left']}\n"
                      f"🤖 Coleta Automática: {auto_collect}\n"
                      f"⏰ Próxima coleta: {AUTO_COLLECT_TIME}\n\n"
                      f"💰 Clique em 'Pagamento' para renovar")
        
        markup = self.create_menu("main")
        self.bot.send_message(message.chat.id, status_text, reply_markup=markup)

    # MÉTODOS DE PROCESSAMENTO ADMIN
    def process_renew_user(self, message):
        """Processa renovação de usuário"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
                
        try:
            user_id, days = message.text.split()
            days = int(days)
            
            if days <= 0:
                self.bot.reply_to(message, "❌ Número de dias deve ser maior que 0")
                return
                
            if self.admin.renew_user(user_id, days):
                self.bot.reply_to(message, 
                    f"✅ Usuário {user_id} renovado!\n\n"
                    f"📅 Adicionado: {days} dias")
            else:
                self.bot.reply_to(message, "❌ Erro ao renovar usuário. Verifique o ID.")
                
        except ValueError:
            self.bot.reply_to(message, 
                "❌ Formato inválido!\n\n"
                "💡 Use: ID_USUARIO DIAS\n"
                "Exemplo: 123456789 30")


    def process_remove_days(self, message):
        """Processa remoção de dias"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
        
        # Verifica se o usuário está no modo admin
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
                
        # Verifica se a mensagem é um botão do menu admin
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
                            
        # Qualquer botão que inicie com 🔛 Trocar Número
        if message.text and message.text.startswith("🔛 Trocar Número:"):
            admin_menu_buttons.append(message.text)
                            
        if message.text in admin_menu_buttons:
            # Redireciona para o handler do menu admin
            self.handle_admin_menu(message)
            return
            
        try:
            parts = message.text.split()
            if len(parts) != 2:
                raise ValueError("Formato incorreto")
                
            user_id = parts[0]
            days = int(parts[1])
            
            if days <= 0:
                self.bot.reply_to(message, "❌ Número de dias deve ser maior que 0")
                return
                
            if self.admin.remove_days(user_id, days):
                self.bot.reply_to(message, 
                    f"✅ Dias removidos com sucesso!\n\n"
                    f"👤 Usuário: {user_id}\n"
                    f"📅 Removido: {days} dias")
            else:
                self.bot.reply_to(message, "❌ Erro ao remover dias. Verifique o ID.")
                
        except ValueError:
            self.bot.reply_to(message, 
                "❌ Formato inválido!\n\n"
                "💡 Use: ID DIAS\n"
                "Exemplo: 123456789 10")

    def process_delete_user(self, message):
        """Processa exclusão de usuário"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
        
        # Verifica se o usuário está no modo admin
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
                
        # Verifica se a mensagem é um botão do menu admin
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
                            
        # Qualquer botão que inicie com 🔛 Trocar Número
        if message.text and message.text.startswith("🔛 Trocar Número:"):
            admin_menu_buttons.append(message.text)
                            
        if message.text in admin_menu_buttons:
            # Redireciona para o handler do menu admin
            self.handle_admin_menu(message)
            return
            
        try:
            user_id_to_delete = message.text.strip()
            
            if not user_id_to_delete:
                raise ValueError("ID vazio")
                
            if self.admin.delete_user(user_id_to_delete):
                self.bot.reply_to(message, 
                    f"✅ Usuário excluído com sucesso!\n\n"
                    f"🗑 ID: {user_id_to_delete}")
            else:
                self.bot.reply_to(message, "❌ Erro ao excluir usuário. Verifique o ID.")
                
        except ValueError:
            self.bot.reply_to(message, 
                "❌ Formato inválido!\n\n"
                "💡 Digite apenas o ID do usuário\n"
                "Exemplo: 123456789")


    def has_valid_session(self, user_id):
        """Verifica se o usuário possui uma sessão válida"""
        users = self.db.load_users()
        if user_id not in users:
            return False
        operator = users[user_id].get('operator')
        # Pega o token da operadora atual, se existir, senão usa o da raiz
        auth = users[user_id].get(operator, {}).get('authorization', users[user_id].get('authorization'))
        if not auth:
            return False
        return self.api.check_auth_validity(auth)['success']
        
    def validate_session_before_action(self, message, action_function, *args, **kwargs):
        """Verifica a sessão antes de executar qualquer ação"""
        user_id = str(message.from_user.id)
        
        if not self.has_valid_session(user_id):
            # Sessão inválida, redireciona para login
            users = self.db.load_users()
            # Sempre pede o número, não mostra mais opções
            self.bot.send_message(message.chat.id, 
                                "🔐 Você precisa fazer login primeiro!\n\n" + 
                                MESSAGES.get('phone_required', "Digite seu celular (ex: 69993752505):"),
                                reply_markup=ReplyKeyboardRemove())
            self.bot.register_next_step_handler(message, self.process_first_phone)
            return False
        # Sessão válida, continuar com a ação
        return action_function(message, *args, **kwargs) if action_function else True

    def setup_handlers(self):
        # Garantir que comandos administrativos e de interrupção sempre funcionem
        @self.bot.message_handler(commands=['admin', 'stop', 'cancel'], func=lambda message: True, priority=1)
        def handle_priority_commands(message):
            """Handler para comandos prioritários que sempre devem funcionar"""
            if message.text.startswith('/admin'):
                # Processa comando administrativo imediatamente
                if message.text == '/admin':
                    self.bot.reply_to(message, "Digite /admin seguido da senha")
                    return
                    
                try:
                    _, password = message.text.split()
                except:
                    self.bot.reply_to(message, "Formato inválido. Use /admin senha")
                    return
                    
                if not self.admin.check_admin_password(password):
                    self.bot.reply_to(message, "❌ Senha incorreta!")
                    return
                    
                # Cria teclado admin
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.row("📋 Listar Usuários", "📊 Usuários Vencidos")
                markup.row("✅ Renovar Usuário", "❌ Remover Dias")
                markup.row("🗑 Excluir Usuário", "🔙 Voltar ao Menu")
                
                self.bot.reply_to(message, "🔓 Painel Admin:", reply_markup=markup)
                
            elif message.text == '/stop' or message.text == '/cancel':
                # Interrompe qualquer operação em andamento do usuário
                user_id = str(message.from_user.id)
                
                # Cancela campanhas em andamento
                if self.active_tasks.get(user_id):
                    self.active_tasks[user_id] = False
                    self.bot.send_message(message.chat.id, "🛑 Operação interrompida!")
                
                # Retorna para o menu principal, se o usuário estiver logado
                if self.has_valid_session(user_id):
                    markup = self.create_menu("main")
                    self.bot.send_message(message.chat.id, "🏠 Menu principal:", reply_markup=markup)
                else:
                    # Se não estiver logado, mostra opções de login
                    self.bot.send_message(message.chat.id, 
                                        "Operação cancelada. Use /start para iniciar novamente.",
                                        reply_markup=ReplyKeyboardRemove())
        

        @self.bot.message_handler(func=lambda m: m.text == "🔙 Voltar ao Menu")
        def handle_back_button(message):
            """Handler especial para o botão 'Voltar ao Menu'"""
            user_id = str(message.from_user.id)
            # Verifica se o usuário está no modo admin
            if user_id in self.admin_users:
                # Se estava no modo admin, remove do conjunto e mostra o menu principal
                self.admin_users.remove(user_id)
                markup = self.create_menu("main")
                self.bot.send_message(message.chat.id, "🏠 Menu principal:", reply_markup=markup)
            else:
                # Verifica status da assinatura
                subscription = self.db.check_subscription(user_id)
                if not subscription["active"]:
                    self.bot.send_message(
                        message.chat.id,
                        "❌ Sua assinatura está vencida ou suspensa! Sessão será reiniciada.\n\nDigite seu número de telefone para fazer login novamente:",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    self.bot.register_next_step_handler(message, self.process_first_phone)
                    return
                # Se ativa, libera menu normalmente
                markup = self.create_menu("main")
                self.bot.send_message(message.chat.id, "🏠 Menu principal:", reply_markup=markup)



        @self.bot.message_handler(func=lambda m: m.text == "⚙️ Configurações")
        def handle_settings_menu(message):
            """Handler para menu de configurações"""
            if MAINTENANCE_MODE:
                self.bot.reply_to(message, MESSAGES.get('maintenance', "🛠 Bot em manutenção. Tente depois! 💤"))
                return
                
            user_id = str(message.from_user.id)
            
            # IMPORTANTE: Verificar primeiro se é um revendedor e mostrar as configurações de revendedor
            if self.revenda.is_reseller(user_id):
                # Se for revendedor, mostra o menu de configurações de revendedor
                self.revenda.show_reseller_settings(message)
                return
            
            # Se não for revendedor, mostra menu de configurações padrão
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("🔄 Trocar Número", "🚫 Desativar Coleta Automática")
            markup.row("✅ Ativar Coleta Automática", "🔙 Voltar ao Menu")
            
            self.bot.send_message(message.chat.id, 
                            "⚙️ CONFIGURAÇÕES\n\n"
                            "Escolha uma opção abaixo:", 
                            reply_markup=markup)



        @self.bot.message_handler(commands=['revenda'])
        def handle_revenda(message):
            """Comando para painel de revendedor"""
            if MAINTENANCE_MODE:
                self.bot.reply_to(message, MESSAGES.get('maintenance', "🛠 Bot em manutenção. Tente depois! 💤"))
                return
                
            user_id = str(message.from_user.id)
            
            # Verifica se é revendedor
            if not self.revenda.is_reseller(user_id):
                self.bot.reply_to(message, "❌ Você não é um revendedor autorizado.")
                return
            
            # Exibe o painel de revendedor
            self.revenda.show_reseller_panel(message)

        # Certifique-se de que este handler esteja ANTES do handler geral no arquivo bot_core.py
        @self.bot.message_handler(func=lambda m: m.text in ["👥 Meus Clientes", "🔗 Gerar Link", 
                                                        "💳 Comprar Créditos", "⚙️ Configurações", 
                                                        "📊 Estatísticas"])
        def handle_reseller_menu(message):
            """Handler para menu do revendedor"""
            if MAINTENANCE_MODE:
                self.bot.reply_to(message, MESSAGES.get('maintenance', "🛠 Bot em manutenção. Tente depois! 💤"))
                return
                
            user_id = str(message.from_user.id)
            
            # Verifica se é revendedor
            if not self.revenda.is_reseller(user_id):
                return  # Ignora se não for revendedor
            
            # Mapeia para as funções corretas
            if message.text == "👥 Meus Clientes":
                self.revenda.show_clients_list(message)
            elif message.text == "🔗 Gerar Link":
                self.revenda.show_affiliate_link(message)
            elif message.text == "💳 Comprar Créditos":
                self.revenda.show_credit_purchase(message)
            elif message.text == "⚙️ Configurações":
                self.revenda.show_reseller_settings(message)
            elif message.text == "📊 Estatísticas":
                self.revenda.show_reseller_stats(message)


        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("renew_"))
        def handle_renew_client(call):
            """Handler para confirmar renovação de cliente"""
            self.revenda.confirm_renew_client(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "cancel_renewal")
        def handle_cancel_renewal(call):
            """Handler para cancelar renovação de cliente"""
            self.revenda.cancel_renewal(call)

        # Adicione ao método setup_handlers() em bot_core.py
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_remove_all_") or call.data == "cancel_remove_all")
        def handle_confirm_remove_all(call):
            """Handler para confirmar remoção completa de revendedor"""
            if call.data == "cancel_remove_all":
                self.bot.answer_callback_query(call.id, "Operação cancelada.", show_alert=True)
                self.bot.edit_message_text("❌ Operação cancelada.", call.message.chat.id, call.message.message_id)
                return
                
            # Extrai o ID do revendedor
            reseller_id = call.data.replace("confirm_remove_all_", "")
            
            # Responde ao callback
            self.bot.answer_callback_query(call.id, "Processando...", show_alert=False)
            
            try:
                # Remove o revendedor e todas as assinaturas
                if self.db.remove_reseller(reseller_id):
                    self.bot.edit_message_text(
                        f"✅ REMOÇÃO COMPLETA\n\n"
                        f"O revendedor {reseller_id} e todas as assinaturas de seus clientes foram removidos com sucesso.",
                        call.message.chat.id, call.message.message_id
                    )
                else:
                    self.bot.edit_message_text(
                        "❌ Erro ao remover revendedor. Tente novamente.",
                        call.message.chat.id, call.message.message_id
                    )
            except Exception as e:
                self.bot.edit_message_text(
                    f"❌ Erro: {str(e)}",
                    call.message.chat.id, call.message.message_id
                )

        # Adicione ao método setup_handlers() em bot_core.py
        @self.bot.message_handler(func=lambda m: m.text == "❌ Remover Revenda e Subs")
        def handle_remove_reseller_and_subs(message):
            """Handler para remover revendedor e todas as assinaturas associadas"""
            msg = self.bot.reply_to(message, 
                "⚠️ ATENÇÃO! Esta ação removerá o revendedor e TODAS as assinaturas de seus clientes!\n\n"
                "Digite o ID do revendedor para confirmar:")
            self.bot.register_next_step_handler_by_chat_id(msg.chat.id, self.process_remove_reseller_and_subs)



        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("clients_"))
        def handle_clients_navigation(call):
            """Handler para navegação na lista de clientes"""
            action = call.data.split("_")[1]
            
            if action == "prev":
                self.revenda.navigate_clients(call, "prev")
            elif action == "next":
                self.revenda.navigate_clients(call, "next")
            elif action == "add_days":
                self.revenda.start_add_days(call)
            # CORREÇÃO: Adicionar tratamento para o botão "Renovar Cliente"
            elif action == "renew":
                self.revenda.start_renew_client(call)
            # CORREÇÃO: Garantir tratamento para o botão "Deletar Cliente"
            elif action == "delete":
                self.revenda.start_delete_client(call)
            else:
                print(f"Callback não tratado: {call.data}")


        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_days_"))
        def handle_confirm_days(call):
            """Handler para confirmar adição de dias"""
            self.revenda.confirm_add_days(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "clients_delete")
        def handle_delete_client(call):
            """Handler para deletar cliente"""
            self.revenda.start_delete_client(call)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"))
        def handle_confirm_delete_client(call):
            """Handler para confirmar exclusão de cliente"""
            self.revenda.confirm_delete_client(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
        def handle_cancel_delete_client(call):
            """Handler para cancelar exclusão de cliente"""
            self.revenda.cancel_delete_client(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "cancel_days")
        def handle_cancel_days(call):
            """Handler para cancelar adição de dias"""
            self.revenda.cancel_add_days(call)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("buy_credits_"))
        def handle_buy_credits(call):
            """Handler para compra de créditos"""
            self.revenda.process_credit_purchase(call)
    
        @self.bot.callback_query_handler(func=lambda call: call.data == "clients_add_days")
        def handle_add_days_specific(call):
            """Handler dedicado para o botão 'Adicionar Dias'"""
            print(f"Callback recebido: {call.data}")
            try:
                self.revenda.start_add_days(call)
            except Exception as e:
                print(f"Erro ao processar adição de dias: {str(e)}")
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Erro ao processar solicitação. Tente novamente.",
                    show_alert=True
                )
    
        @self.bot.callback_query_handler(func=lambda call: call.data == "config_price")
        def handle_config_price(call):
            """Handler para configurar valor da assinatura"""
            self.revenda.start_price_config(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "config_mp")
        def handle_config_mp(call):
            """Handler para configurar Mercado Pago"""
            self.revenda.start_mp_config(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "test_mp")
        def handle_test_mp(call):
            """Handler para testar integração com Mercado Pago"""
            self.revenda.test_mp_integration(call)

        # Corrigindo o método handle_start para processar links de afiliados
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            if MAINTENANCE_MODE:
                self.bot.reply_to(message, MESSAGES.get('maintenance', "🛠 Bot em manutenção. Tente depois! 💤"))
                return
            user_id = str(message.from_user.id)
            users = self.db.load_users()
            # NOVO: Captura o código de afiliado se vier no /start
            affiliate_code = None
            if message.text and len(message.text.split()) > 1:
                command_parts = message.text.split()
                if command_parts[1].startswith('aff_'):
                    affiliate_code = command_parts[1].replace('aff_', '')
                    self.affiliate_codes[user_id] = affiliate_code  # Salva para uso posterior
                    print(f"[LOG] /start recebido com código de afiliado: {affiliate_code} para user_id={user_id}")
                    # Só UMA mensagem clara
                    self.bot.send_message(
                        message.chat.id,
                        "🔗 Você está entrando através de um link de revenda! Ao finalizar o cadastro, será automaticamente associado ao revendedor."
                    )
            # Só mostra painel se tiver sessão válida
            if user_id in users and self.has_valid_session(user_id):
                subscription = self.db.check_subscription(user_id)
                welcome_message = self.create_welcome_message(users[user_id])
                if subscription["active"]:
                    self.bot.send_message(
                        message.chat.id,
                        f"✅ Sua assinatura está ativa!\n⏳ Dias restantes: {subscription['days_left']}\n\n{welcome_message}"
                    )
                    markup = self.create_menu("main")
                    self.bot.send_message(message.chat.id, "🏠 Menu principal:", reply_markup=markup)
                    self.db.update_last_login(user_id)
                    return
                else:
                    self.bot.send_message(
                        message.chat.id,
                        f"❌ Sua assinatura expirou ou está suspensa!\n\nClique em 'Pagamento' abaixo para renovar.",
                    )
                    self.show_pix_menu(message)
                    return
            # Se não tem sessão válida, força fluxo de login/operadora
            import telebot.types
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("✅ Continuar", callback_data="start_continue"))
            self.bot.send_message(message.chat.id, get_mensagem_start(), reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data == "start_continue")
        def handle_start_continue(call):
            message = call.message
            user_id = str(call.from_user.id)
            users = self.db.load_users()
            affiliate_code = self.affiliate_codes.get(user_id)
            revenda_uid = self.revenda_uids.get(user_id, user_id)
            current_reseller = self.db.get_client_reseller(user_id)
            if affiliate_code:
                if not current_reseller:
                    if user_id in users:
                        associado = self.db.associate_client_to_reseller(user_id, self.db.get_reseller_by_affiliate(affiliate_code))
                        if associado:
                            reseller_id = self.db.get_reseller_by_affiliate(affiliate_code)
                            self.db.increment_reseller_trial(reseller_id)
                            self.bot.send_message(
                                message.chat.id,
                                "🔗 Você entrou através de um link de revenda! Você já está associado ao revendedor."
                            )
                            try:
                                nome_cliente = users[user_id].get('phone_number', f'ID {user_id}')
                                self.revenda.bot.send_message(
                                    int(reseller_id),
                                    f"👤 Novo cliente entrou pelo seu link de revenda!\n\nID: <code>{user_id}</code>\nTelefone: {nome_cliente}\n\nAcompanhe seus clientes no painel de revenda.",
                                    parse_mode="HTML"
                                )
                            except Exception as e:
                                print(f"Erro ao notificar revendedor: {e}")
                    else:
                        is_valid = self.revenda.handle_affiliate_start(message, affiliate_code)
                        if is_valid:
                            # Salva pendência usando revenda_uid
                            self.db.save_pending_association(user_id, self.db.get_reseller_by_affiliate(affiliate_code), revenda_uid=revenda_uid)
                            self.bot.send_message(
                                message.chat.id,
                                "🔗 Você entrou através de um link de revenda! Ao finalizar o cadastro, será associado ao revendedor."
                            )
                        else:
                            return
            if user_id in users and self.has_valid_session(user_id):
                subscription = self.db.check_subscription(user_id)
                markup = self.create_menu("main")
                welcome_message = self.create_welcome_message(users[user_id])
                if subscription["active"]:
                    self.bot.send_message(
                        message.chat.id,
                        f"{welcome_message}\n\n✅ Bem-vindo! Sua assinatura vence em {subscription['days_left']} dias.",
                        reply_markup=markup
                    )
                    self.db.update_last_login(user_id)
                    return
                else:
                    self.bot.send_message(
                        message.chat.id,
                        f"❌ Sua assinatura expirou ou está suspensa!\n\nClique em 'Pagamento' abaixo para renovar."
                    )
                    self.show_pix_menu(message)
                    return
            # --- Fluxo original do /start a partir daqui ---
            affiliate_code = None
            if call.message.text and len(call.message.text.split()) > 1:
                command_parts = call.message.text.split()
                if command_parts[1].startswith('aff_'):
                    affiliate_code = command_parts[1].replace('aff_', '')
            has_resellers = self.db.has_resellers()
            is_new_user = user_id not in users
            # Se entrou por link de afiliado, processa normalmente
            if is_new_user and affiliate_code:
                is_valid = self.revenda.handle_affiliate_start(message, affiliate_code)
                if not is_valid:
                    return
            # Somente novos usuários passam pelo proxy
            loading_msg = self.bot.send_message(
                message.chat.id, 
                MESSAGES.get('proxy_connecting', "🔒 Aguarde, conectando a um ambiente seguro e rotacionando IP...")
            )
            def update_loading_message():
                emojis = ["⏳", "⌛", "🔄", "🔐"]
                for i in range(20):
                    try:
                        if not self.proxy_setup_done:
                            self.bot.edit_message_text(
                                f"{emojis[i % 4]} Rotacionando endereço IP... Por favor aguarde.",
                                message.chat.id, loading_msg.message_id
                            )
                        else:
                            break
                        time.sleep(0.7)
                    except Exception as e:
                        print(f"Erro na animação de carregamento: {e}")
                        break
            self.proxy_setup_done = False
            import threading
            loading_thread = threading.Thread(target=update_loading_message, daemon=True)
            loading_thread.start()
            success, proxy_message, new_ip, new_country = self.api.rotate_proxy()
            self.proxy_setup_done = True
            self.update_proxy_location()
            time.sleep(0.7)
            try:
                if success:
                    city = self.api.proxy_info.get('city', 'desconhecida')
                    region = self.api.proxy_info.get('region', 'desconhecida')
                    ip = self.api.proxy_info.get('ip', 'desconhecido')
                    self.bot.edit_message_text(
                        f"🔐 BYPASS ATIVADO COM SUCESSO! 🚀\n\n"
                        f"🌐 Seu novo endereço IP: {ip}\n"
                        f"📍 Localização atual: {city}/{region}\n\n"
                        f"✅ Sua conexão está segura e anônima!\n"
                        f"🛡️ Pronto para operar com máxima proteção.",
                        message.chat.id, loading_msg.message_id
                    )
                else:
                    self.bot.edit_message_text(
                        f"⚠️ {proxy_message}",
                        message.chat.id, loading_msg.message_id
                    )
            except Exception as e:
                print(f"Erro ao atualizar mensagem de proxy: {e}")
            time.sleep(1.5)
            if user_id in users and self.has_valid_session(user_id):
                subscription = self.db.check_subscription(user_id)
                welcome_message = self.create_welcome_message(users[user_id])
                if subscription["active"]:
                    self.bot.send_message(
                        message.chat.id,
                        f"{welcome_message}\n\n✅ Bem-vindo! Sua assinatura vence em {subscription['days_left']} dias."
                    )
                else:
                    self.bot.send_message(
                        message.chat.id,
                        f"❌ Sua assinatura expirou ou está suspensa!\n\nClique em 'Pagamento' abaixo para renovar."
                    )
                    self.show_pix_menu(message)
                self.db.update_last_login(user_id)
                return
            if user_id not in users:
                self.db.update_stats('total_users', 1)
                markup = self.create_operator_menu()
                self.bot.send_message(
                    message.chat.id, 
                    MESSAGES.get('welcome', "🎉 Bem-vindo!") + "\n\n"
                    "📱 Selecione sua operadora:",
                    reply_markup=markup
                )
                self.bot.register_next_step_handler(message, self.process_operator_selection)
            else:
                markup = self.create_operator_menu()
                self.bot.send_message(
                    message.chat.id,
                    "Bem-vindo de volta!\n\n"
                    "📱 Selecione sua operadora:",
                    reply_markup=markup
                )
                self.bot.register_next_step_handler(message, self.process_operator_selection)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
        def handle_payment_check(call):
            # Informa ao usuário que os pagamentos são verificados automaticamente
            self.bot.answer_callback_query(
                call.id, 
                "✅ Os pagamentos são verificados automaticamente pelo webhook. Aguarde a confirmação.",
                show_alert=True
            )

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
        def handle_copy_pix(call):
            # Extrai o ID do pagamento
            payment_id = call.data.replace("copy_", "")
            user_id = str(call.from_user.id)
            
            # Recupera o código PIX armazenado temporariamente
            users = self.db.load_users()
            
            # Verifica se já existe um ID de mensagem do código PIX armazenado
            if 'pix_message_id' in users.get(user_id, {}):
                # Se já tiver enviado o código antes, apenas mostra uma notificação
                self.bot.answer_callback_query(call.id, "✅ O código PIX já foi enviado abaixo!", show_alert=True)
                return
            
            pix_code = users.get(user_id, {}).get('temp_pix_code', '')
            
            if not pix_code:
                self.bot.answer_callback_query(call.id, "❌ Código PIX não encontrado. Tente gerar novamente.", show_alert=True)
                return
            
            try:
                # Notifica o usuário
                self.bot.answer_callback_query(call.id, "✅ Código PIX copiado!", show_alert=True)
                
                # Envia código PIX como mensagem separada para fácil cópia
                msg = self.bot.send_message(
                    call.message.chat.id, 
                    f"<code>{pix_code}</code>\n\n👆 Clique no código acima para copiar\n\n"
                    f"✅ O pagamento será verificado automaticamente pelo webhook.",
                    parse_mode="HTML"
                )
                
                # Armazena o ID da mensagem para evitar duplicação
                if user_id not in users:
                    users[user_id] = {}
                users[user_id]['pix_message_id'] = msg.message_id
                self.db.save_users(users)
                
            except Exception as e:
                print(f"Erro ao copiar código PIX: {str(e)}")
                self.bot.answer_callback_query(call.id, "❌ Falha ao copiar. Tente novamente.")
            
        
        @self.bot.message_handler(func=lambda m: m.text and m.text.startswith("🔛 Trocar Número:"))
        def handle_toggle_phone_change(message):
            """Handler para ativar/desativar troca de número"""
            # Verifica o status atual
            current_status = self.db.is_phone_change_enabled()
            
            # Inverte o status
            new_status = not current_status
            self.admin.toggle_phone_change(new_status)
            
            # Mostra o novo status
            status_text = "✅ ON" if new_status else "❌ OFF"
            self.bot.reply_to(message, f"🔄 Troca de número: {status_text}")
            
            # Atualiza o menu admin
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("📋 Listar Usuários", "📊 Usuários Vencidos")
            markup.row("✅ Renovar Usuário", "❌ Remover Dias")
            markup.row("🗑 Excluir Usuário", "🚫 Suspender Usuário", "✅ Ativar Usuário")
            markup.row("🔛 Trocar Número: " + ("✅ ON" if self.db.is_phone_change_enabled() else "❌ OFF"))
            markup.row("👥 Listar Revendedores", "➕ Adicionar Revendedor")
            markup.row("💰 Dar Créditos", "🗑️ Remover Revendedor")
            markup.row("❌ Remover Revenda e Subs", "🔙 Voltar ao Menu")
            self.bot.reply_to(message, "🔓 Painel Admin atualizado:", reply_markup=markup)
    
        @self.bot.message_handler(commands=['admin'])
        def handle_admin(message):
            """Comando de administração"""
            if message.text == '/admin':
                self.bot.reply_to(message, "Digite /admin seguido da senha")
                return
                
            try:
                _, password = message.text.split()
            except:
                self.bot.reply_to(message, "Formato inválido. Use /admin senha")
                return
                
            if not self.admin.check_admin_password(password):
                self.bot.reply_to(message, "❌ Senha incorreta!")
                return
            
            # Adiciona o usuário ao conjunto de administradores
            self.admin_users.add(str(message.from_user.id))
                        
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("📋 Listar Usuários", "📊 Usuários Vencidos")
            markup.row("✅ Renovar Usuário", "❌ Remover Dias")
            markup.row("🗑 Excluir Usuário", "🚫 Suspender Usuário", "✅ Ativar Usuário")
            markup.row("🔛 Trocar Número: " + ("✅ ON" if self.db.is_phone_change_enabled() else "❌ OFF"))
            markup.row("👥 Listar Revendedores", "➕ Adicionar Revendedor")
            markup.row("💰 Dar Créditos", "🗑️ Remover Revendedor")
            markup.row("❌ Remover Revenda e Subs", "🔙 Voltar ao Menu")
            
            self.bot.reply_to(message, "🔓 Painel Admin:", reply_markup=markup)            
        

        @self.bot.message_handler(func=lambda m: m.text in ["👥 Listar Revendedores", "➕ Adicionar Revendedor", 
                                                        "💰 Dar Créditos", "🗑️ Remover Revendedor", 
                                                        "❌ Remover Revenda e Subs"])
        def handle_admin_reseller_menu(message):
            """Handler para menu admin de revendedores"""
            if message.text == "👥 Listar Revendedores":
                # Implementar listagem de revendedores
                revendedores = self.admin.list_all_resellers()
                if not revendedores:
                    self.bot.reply_to(message, "Nenhum revendedor encontrado")
                    return
                    
                msg = "👥 LISTA DE REVENDEDORES\n\n"
                for rev in revendedores:
                    msg += f"ID: {rev['user_id']}\n"
                    msg += f"📱 Telefone: {rev['phone']}\n"
                    msg += f"💰 Créditos: {rev['credits']}\n"
                    msg += f"👥 Clientes: {rev['total_clients']}\n"
                    msg += f"➖➖➖➖➖➖➖➖\n"
                    
                    if len(msg) > 3500:  # Limite do Telegram
                        self.bot.reply_to(message, msg)
                        msg = "👥 LISTA DE REVENDEDORES (continuação)\n\n"
                        
                if msg:
                    self.bot.reply_to(message, msg)
                    
            elif message.text == "➕ Adicionar Revendedor":
                msg = self.bot.reply_to(message, 
                    "💡 Digite o ID do usuário e (opcionalmente) créditos iniciais\n\n"
                    "Formato: ID [CREDITOS]\n"
                    "Exemplo: 123456789 50")
                self.bot.register_next_step_handler_by_chat_id(msg.chat.id, self.process_add_reseller)
                    
            elif message.text == "💰 Dar Créditos":
                msg = self.bot.reply_to(message, 
                    "💡 Digite o ID do revendedor e quantidade de créditos\n\n"
                    "Formato: ID CREDITOS\n"
                    "Exemplo: 123456789 100")
                self.bot.register_next_step_handler_by_chat_id(msg.chat.id, self.process_add_credits)
                    
            elif message.text == "🗑️ Remover Revendedor":
                msg = self.bot.reply_to(message, 
                    "⚠️ Digite o ID do revendedor para remover\n\n"
                    "⚡️ Esta ação não pode ser desfeita!")
                self.bot.register_next_step_handler_by_chat_id(msg.chat.id, self.process_remove_reseller)
                    
            elif message.text == "❌ Remover Revenda e Subs":
                msg = self.bot.reply_to(message, 
                    "⚠️ ATENÇÃO! Esta ação removerá o revendedor e TODAS as assinaturas de seus clientes!\n\n"
                    "Digite o ID do revendedor para confirmar:")
                self.bot.register_next_step_handler_by_chat_id(msg.chat.id, self.process_remove_reseller_and_subs)        
            
        @self.bot.message_handler(func=lambda m: m.text in ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                                                    "✅ Renovar Usuário", "❌ Remover Dias", 
                                                    "🗑 Excluir Usuário", "🚫 Suspender Usuário", "🔛 Trocar Número: ✅ ON",
                                                    "🔛 Trocar Número: ❌ OFF", "👥 Listar Revendedores",
                                                    "➕ Adicionar Revendedor", "💰 Dar Créditos",
                                                    "🗑️ Remover Revendedor", "❌ Remover Revenda e Subs"])
        def handle_admin_menu_wrapper(message):
            """Wrapper para chamar o método handle_admin_menu da classe"""
            self.handle_admin_menu(message)
            
        # AQUI ESTÁ O HANDLER GERAL - ESTA É A PARTE MAIS IMPORTANTE
        # Esse é o handler que captura TODAS as mensagens que não foram tratadas pelos handlers acima
        @self.bot.message_handler(func=lambda m: True)
        def handle_all_messages(message):
            if MAINTENANCE_MODE:
                self.bot.reply_to(message, MESSAGES.get('maintenance', "🛠 Bot em manutenção. Tente depois! 💤"))
                return

            # Remove completamente os handlers para 'Usar número cadastrado' e 'Usar outro número'
            # O restante do handler permanece igual
            handlers = {
                "🚀 Começar Campanhas": self.start_campaigns,
                "💎 Ver Moedas": self.check_balance,
                "🎁 Pacotes Disponíveis": self.list_packages,
                "🤖 Coleta Automática": self.show_auto_collect_menu,
                "📊 Status": self.show_status,
                "💰 Pagamento": self.show_pix_menu,
                f"💳 Pagar R$ {PIX_PRICE:.2f}": self.process_pix_payment,
                "📱 Status da Assinatura": self.show_pix_menu,
                "📋 Histórico": self.show_payment_history,
                "✅ Ativar Coleta": lambda m: self.toggle_auto_collect(m, True),
                "❌ Desativar Coleta": lambda m: self.toggle_auto_collect(m, False),
                "🔙 Voltar ao Menu": lambda m: self.bot.send_message(
                    m.chat.id, "🏠 Menu principal:", 
                    reply_markup=self.create_menu("main")),
                "🚪 Sair": lambda m: (
                    self.bot.send_message(
                        m.chat.id,
                        "📱 Selecione sua operadora:",
                        reply_markup=self.create_operator_menu()
                    ),
                    self.bot.register_next_step_handler(m, self.process_operator_selection)
                )
            }
            # Verifica se o texto da mensagem está nos handlers
            if message.text in handlers:
                handlers[message.text](message)
            # Caso especial para pagamento PIX (para lidar com valores diferentes)
            elif message.text and message.text.startswith("💳 Pagar R$"):
                self.process_pix_payment(message)
            # Caso especial para pacotes
            elif message.text and message.text.startswith("🎁"):
                self.redeem_package(message)

        # Handler para o botão inline de reiniciar sessão
        @self.bot.callback_query_handler(func=lambda call: call.data == "restart_session")
        def handle_restart_session(call):
            # Remove o botão imediatamente para evitar duplo clique
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            self.bot.answer_callback_query(call.id, "Sessão reiniciada!", show_alert=False)
            # Limpa o estado do usuário para evitar duplicidade de handlers
            try:
                self.state_storage.reset_state(call.from_user.id, call.message.chat.id)
            except Exception:
                pass
            # Redireciona para a seleção de operadora
            markup = self.create_operator_menu()
            msg = self.bot.send_message(
                call.message.chat.id,
                "📱 Selecione sua operadora:",
                reply_markup=markup
            )
            # O próximo passo será tratado como seleção de operadora, não PIN!
            self.bot.register_next_step_handler(msg, self.process_operator_selection)

    def process_operator_selection(self, message):
        """Processa a seleção da operadora pelo usuário"""
        from config import OPERATORS
        # Limpa o estado do usuário ao iniciar seleção de operadora
        try:
            self.state_storage.reset_state(message.from_user.id, message.chat.id)
        except Exception:
            pass
        
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                # Redireciona para o handler de comandos prioritários
                self.bot.process_new_messages([message])
                return
        
        if not message.text:
            self.bot.send_message(message.chat.id, "❌ Selecione uma operadora válida:")
            self.bot.register_next_step_handler(message, self.process_operator_selection)
            return
        
        print(f"DEBUG: Texto recebido: '{message.text}'")
        
        # Identifica qual operadora foi selecionada
        selected_operator = None
        for operator_key, operator_data in OPERATORS.items():
            print(f"DEBUG: Verificando {operator_key}: emoji='{operator_data['emoji']}', name='{operator_data['name']}'")
            # Verifica se o texto contém o emoji OU o nome da operadora
            if (operator_data['emoji'] in message.text or 
                operator_data['name'].lower() in message.text.lower()):
                selected_operator = operator_key
                print(f"DEBUG: Operadora encontrada: {selected_operator}")
                break
        
        if not selected_operator:
            # Mostra as opções disponíveis para debug
            available_options = []
            for operator_key, operator_data in OPERATORS.items():
                available_options.append(f"{operator_data['emoji']} {operator_data['name']}")
            
            self.bot.send_message(
                message.chat.id, 
                f"❌ Operadora inválida. Selecione uma das opções disponíveis:\n\n" +
                "\n".join(available_options)
            )
            self.bot.register_next_step_handler(message, self.process_operator_selection)
            return
        
        # Salva a operadora selecionada
        user_id = str(message.from_user.id)
        self.db.save_user_operator(user_id, selected_operator)
        
        # Configura a API para a operadora selecionada
        self.api.configure_for_operator(selected_operator)
        
        # Troca a API conforme a operadora
        if selected_operator == "vivo":
            self.api = APIClientVivo(database=self.db)
        elif selected_operator == "tim":
            from api_tim import APIClientTim
            self.api = APIClientTim(database=self.db)
        else:
            self.api = APIClient(database=self.db)

        # Confirma a seleção
        operator_data = OPERATORS[selected_operator]
        msg = self.bot.send_message(
            message.chat.id, 
            f"✅ Operadora selecionada: {operator_data['emoji']} {operator_data['name']}\n\n"
            f"📱 Agora digite seu número de telefone (ex: 69993752505):",
            reply_markup=ReplyKeyboardRemove()
        )
        # Continua para o próximo passo (solicitar número do telefone)
        self.bot.register_next_step_handler(msg, self.process_first_phone)

        # Exibe mensagem de boas-vindas personalizada do mensagem_start.py
        # user_id = str(message.from_user.id)
        # users = self.db.load_users()
        # if user_id not in users:
        #     self.bot.send_message(message.chat.id, get_mensagem_start())

    def process_suspend_user(self, message):
        """Processa suspensão de usuário"""
        # Verifica comandos prioritários antes de processar
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                self.bot.process_new_messages([message])
                return
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🚫 Suspender Usuário", "✅ Ativar Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
        if message.text in admin_menu_buttons:
            self.handle_admin_menu(message)
            return
        user_id_to_suspend = message.text.strip()
        if not user_id_to_suspend:
            self.bot.reply_to(message, "❌ ID vazio. Digite apenas o ID do usuário.")
            return
        if self.admin.suspender_usuario(user_id_to_suspend):
            self.bot.reply_to(message, 
                f"🚫 Usuário suspenso com sucesso!\n\n🗑 ID: {user_id_to_suspend}")
        else:
            self.bot.reply_to(message, "❌ Erro ao suspender usuário. Verifique o ID.")

    def process_activate_user(self, message):
        """Processa ativação de usuário"""
        if message.text and message.text.startswith('/'):
            if message.text.startswith('/admin') or message.text == '/stop' or message.text == '/cancel':
                self.bot.process_new_messages([message])
                return
        user_id = str(message.from_user.id)
        if user_id not in self.admin_users:
            return
        admin_menu_buttons = ["📋 Listar Usuários", "📊 Usuários Vencidos", 
                            "✅ Renovar Usuário", "❌ Remover Dias", 
                            "🗑 Excluir Usuário", "🚫 Suspender Usuário", "✅ Ativar Usuário", "🔙 Voltar ao Menu",
                            "👥 Listar Revendedores", "➕ Adicionar Revendedor",
                            "💰 Dar Créditos", "🗑️ Remover Revendedor",
                            "❌ Remover Revenda e Subs"]
        if message.text in admin_menu_buttons:
            self.handle_admin_menu(message)
            return
        user_id_to_activate = message.text.strip()
        if not user_id_to_activate:
            self.bot.reply_to(message, "❌ ID vazio. Digite apenas o ID do usuário.")
            return
        if self.admin.ativar_usuario(user_id_to_activate):
            self.bot.reply_to(message, 
                f"✅ Usuário ativado com sucesso!\n\n🟢 ID: {user_id_to_activate}")
        else:
            self.bot.reply_to(message, "❌ Erro ao ativar usuário. Verifique o ID.")