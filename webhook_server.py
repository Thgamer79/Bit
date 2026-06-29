"""
Módulo de webhook para o bot - Reconstrução 2026
Adaptações: Flask 3.x (jsonify mantido), threading daemon, porta configurável
"""
from flask import Flask, request, jsonify
import threading
import socket
import json
import time
import mercadopago
import traceback

webhook_running = False


class WebhookServer:
    """Classe para gerenciar o servidor webhook"""

    def __init__(self, db, pix, bot_instance):
        self.app = Flask(__name__)
        self.db = db
        self.pix = pix
        self.bot = bot_instance
        self.setup_routes()
        self.thread = None
        self.port = 80

    def setup_routes(self):
        @self.app.route('/webhook', methods=['POST'])
        def mercadopago_webhook():
            try:
                data = request.get_json(silent=True)  # 2026: silent=True evita raise em JSON inválido
                print(f"Webhook recebido: {json.dumps(data, indent=2)}")

                if data and 'type' in data and data['type'] == 'payment':
                    payment_id = data['data']['id']

                    def process_payment():
                        try:
                            print(f"Processando pagamento {payment_id}...")
                            payment_info = self.db.get_payment_info(payment_id)

                            if not payment_info:
                                print(f"Pagamento {payment_id} não encontrado na base de dados")
                                reseller_id, credits = self.db.get_reseller_by_credit_payment(payment_id)
                                if reseller_id:
                                    print(f"Identificado como pagamento de créditos para revendedor {reseller_id}")
                                    custom_token = self.db.get_payment_token(payment_id)
                                    payment_status = self.pix.check_payment_status(payment_id, custom_token)
                                    print(f"Status do pagamento de créditos: {json.dumps(payment_status)}")
                                    if payment_status["success"] and payment_status["paid"]:
                                        print(f"Pagamento de créditos confirmado. Adicionando {credits} créditos para {reseller_id}")
                                        self.db.update_credit_payment_status(payment_id, "approved")
                                        try:
                                            self.bot.send_message(int(reseller_id),
                                                f"🎉 Seu pagamento foi confirmado!\n"
                                                f"✅ {credits} créditos foram adicionados à sua conta.\n"
                                                f"Obrigado por usar nosso bot!")
                                        except Exception as e:
                                            print(f"Erro ao enviar mensagem: {e}")
                                return

                            if payment_info['processed']:
                                print(f"Pagamento {payment_id} já foi processado anteriormente")
                                return

                            custom_token = self.db.get_payment_token(payment_id)
                            print(f"Token recuperado do banco para pagamento {payment_id}: {custom_token is not None}")

                            if not custom_token and payment_info['custom_token_used'] and payment_info['reseller_id']:
                                reseller_data = self.db.get_reseller_data(payment_info['reseller_id'])
                                if reseller_data and 'mercado_pago_token' in reseller_data:
                                    custom_token = reseller_data['mercado_pago_token']
                                    print(f"Token recuperado do revendedor {payment_info['reseller_id']}: {custom_token is not None}")

                            if custom_token:
                                print(f"Verificando pagamento {payment_id} usando token personalizado do revendedor")
                                try:
                                    mp_instance = mercadopago.SDK(custom_token)
                                    result = mp_instance.payment().get(payment_id)
                                    if result["status"] == 200:
                                        payment = result["response"]
                                        status = payment["status"]
                                        print(f"Status do pagamento verificado com token do revendedor: {status}")
                                        if status == "approved":
                                            self._process_approved_payment(payment_id, payment_info, payment)
                                        else:
                                            self.db.update_payment_status(payment_id, status)
                                            print(f"Status atualizado para: {status}")
                                    else:
                                        print(f"Erro ao verificar com token do revendedor: {result}")
                                        self._verify_with_default_token(payment_id, payment_info)
                                except Exception as e:
                                    print(f"Exceção ao verificar com token do revendedor: {e}")
                                    self._verify_with_default_token(payment_id, payment_info)
                            else:
                                self._verify_with_default_token(payment_id, payment_info)

                        except Exception as e:
                            print(f"Erro ao processar pagamento {payment_id}: {e}")
                            print(f"Traceback completo: {traceback.format_exc()}")

                    thread = threading.Thread(target=process_payment, daemon=True)
                    thread.start()

                return jsonify({"status": "success"}), 200

            except Exception as e:
                print(f"Erro no webhook: {e}")
                print(f"Traceback completo: {traceback.format_exc()}")
                return jsonify({"status": "error", "message": str(e)}), 500

        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Verifica se o webhook está funcionando"""
            return jsonify({"status": "ok", "service": "webhook"}), 200

    def _verify_with_default_token(self, payment_id, payment_info):
        """Verifica o pagamento usando o token padrão"""
        print(f"Verificando pagamento {payment_id} com token PADRÃO do sistema")
        try:
            payment_status = self.pix.check_payment_status(payment_id, None)
            if payment_status["success"]:
                if payment_status["paid"]:
                    self._process_approved_payment(payment_id, payment_info, payment_status)
                else:
                    self.db.update_payment_status(payment_id, payment_status["status"])
                    print(f"Status atualizado para: {payment_status['status']}")
            else:
                print(f"Falha ao verificar pagamento com token padrão: {payment_status.get('error')}")
        except Exception as e:
            print(f"Exceção ao verificar com token padrão: {e}")

    def _process_approved_payment(self, payment_id, payment_info, payment_data):
        """Processa um pagamento aprovado"""
        user_id = payment_info['user_id']
        print(f"Processando pagamento APROVADO para usuário {user_id}")

        self.db.update_payment_status(payment_id, "approved")
        self.db.mark_payment_as_processed(payment_id)

        reseller_id = payment_info['reseller_id'] or self.db.get_client_reseller(user_id)
        extend_subscription = True

        if reseller_id:
            try:
                credits = self.db.get_reseller_credits(reseller_id)
                if credits < 1:
                    extend_subscription = False
                    try:
                        self.bot.send_message(int(reseller_id),
                            f"⚠️ ATENÇÃO: Seu cliente (ID: {user_id}) tentou renovar a assinatura, "
                            f"mas você não tem créditos suficientes.\n"
                            f"Compre mais créditos para permitir a renovação deste cliente.")
                    except Exception as e:
                        print(f"Erro ao enviar mensagem de alerta para revendedor: {e}")
                    try:
                        self.bot.send_message(int(user_id),
                            f"⚠️ Seu pagamento foi confirmado, mas a renovação não pôde ser processada "
                            f"porque seu revendedor está sem créditos.\n"
                            f"Por favor, entre em contato com seu revendedor para resolver esta situação.")
                    except Exception as e:
                        print(f"Erro ao enviar mensagem para cliente: {e}")
                else:
                    self.db.deduct_reseller_credits(reseller_id, 1)
                    try:
                        self.bot.send_message(int(reseller_id),
                            f"✅ Seu cliente (ID: {user_id}) renovou a assinatura!\n"
                            f"Foi deduzido 1 crédito da sua conta.")
                    except Exception as e:
                        print(f"Erro ao enviar mensagem para revendedor: {e}")
            except Exception as e:
                print(f"Erro ao processar revendedor {reseller_id}: {e}")

        if extend_subscription:
            self.db.extend_subscription(user_id, 30)
            try:
                self.bot.send_message(int(user_id),
                    "🎉 Seu pagamento foi confirmado!\n"
                    "✅ Sua assinatura foi renovada por 30 dias.\n"
                    "Obrigado por usar nosso bot!")
                print(f"✅ Cliente {user_id} notificado com sucesso")
            except Exception as e:
                print(f"❌ Erro ao notificar cliente {user_id}: {e}")
        else:
            print(f"⚠️ Assinatura do cliente {user_id} não foi estendida — revendedor {reseller_id} sem créditos")

    def is_port_in_use(self):
        """Verifica se a porta já está em uso"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', self.port)) == 0

    def start(self):
        """Inicia o servidor webhook em uma thread separada"""
        global webhook_running

        if webhook_running or self.is_port_in_use():
            print("🌐 Webhook já está rodando, não iniciando outro servidor")
            return False

        def run_app():
            print("🌐 Iniciando webhook do Mercado Pago...")
            print(f"   URL: http://localhost:{self.port}/webhook")
            print("   Configure esta URL no painel do Mercado Pago")
            global webhook_running
            webhook_running = True
            # 2026: Flask 3.x — use_reloader=False obrigatório em thread secundária
            self.app.run(
                host='0.0.0.0',
                port=self.port,
                debug=False,
                use_reloader=False,
            )

        self.thread = threading.Thread(target=run_app, daemon=False)
        self.thread.start()
        return True
