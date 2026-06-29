"""
Módulo de pagamento PIX - Reconstrução 2026
Adaptações: mercadopago SDK 2.2.x, tratamento de erros modernizado
"""
import mercadopago
import json
import time
import traceback
from datetime import datetime, timedelta
from config import PIX_ACTUAL_PRICE, TRIAL_DAYS, SUBSCRIPTION_DAYS, MERCADO_PAGO_ACCESS_TOKEN


class PixPayment:
    def __init__(self, access_token):
        # 2026: mercadopago >= 2.2.1 — SDK instanciado normalmente
        self.mp = mercadopago.SDK(access_token)
        self.default_token = access_token

    def create_pix_payment(self, user_id, phone, amount=None, description=None):
        """Cria um pagamento PIX"""
        try:
            custom_token = None
            custom_price = None

            is_credit_payment = description and (
                "crédito" in description.lower() or "credito" in description.lower()
            )

            if is_credit_payment:
                custom_token = None
                print(f"Gerando pagamento para compra de créditos: {description}")
            else:
                from database import Database
                db = Database()
                reseller_id = db.get_client_reseller(user_id)
                if reseller_id:
                    reseller_data = db.get_reseller_data(reseller_id)
                    custom_token = reseller_data.get('mercado_pago_token')
                    custom_price = db.get_reseller_custom_price(reseller_id)
                    print(f"Token do revendedor: {custom_token is not None}")
                    print(f"Preço personalizado: {custom_price}")

            if amount is None:
                amount = custom_price if custom_price is not None else PIX_ACTUAL_PRICE

            if description is None:
                description = f"Assinatura Bot - {SUBSCRIPTION_DAYS} dias"

            payment_data = {
                "transaction_amount": float(amount),
                "description": description,
                "payment_method_id": "pix",
                "payer": {
                    "email": f"user{user_id}@bot.com"
                },
                "external_reference": f"USER_{user_id}_{'CREDIT' if is_credit_payment else 'BOT'}_PAY",
                # 2026: date_of_expiration no formato ISO 8601 com timezone
                "date_of_expiration": (
                    datetime.utcnow() + timedelta(minutes=15)
                ).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
            }

            if custom_token:
                mp_instance = mercadopago.SDK(custom_token)
                print(f"Usando token personalizado do revendedor para pagamento de {amount}")
            else:
                mp_instance = self.mp
                print(f"Usando token padrão para pagamento de {amount}")

            result = mp_instance.payment().create(payment_data)

            if result["status"] == 201:
                payment = result["response"]
                payment_id = payment["id"]
                pix_data = (
                    payment.get("point_of_interaction", {})
                    .get("transaction_data", {})
                )
                qr_code      = pix_data.get("qr_code", "")
                qr_code_base64 = pix_data.get("qr_code_base64", "")

                print(f"Pagamento PIX criado com sucesso. ID: {payment_id}")
                return {
                    "success": True,
                    "payment_id": payment_id,
                    "qr_code": qr_code,
                    "qr_code_base64": qr_code_base64,
                    "amount": amount,
                    "custom_token_used": custom_token is not None,
                }
            else:
                error_msg = result.get("response", {}).get("message", "Erro desconhecido")
                print(f"Erro ao criar pagamento PIX: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            print(f"Exceção ao criar pagamento PIX: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    def check_payment_status(self, payment_id, custom_token=None):
        """Verifica o status de um pagamento"""
        try:
            if custom_token:
                mp_instance = mercadopago.SDK(custom_token)
            else:
                mp_instance = self.mp

            result = mp_instance.payment().get(payment_id)

            if result["status"] == 200:
                payment = result["response"]
                status  = payment.get("status", "")
                paid    = status == "approved"
                return {
                    "success": True,
                    "paid": paid,
                    "status": status,
                    "payment": payment,
                }
            else:
                return {
                    "success": False,
                    "paid": False,
                    "error": f"Status HTTP {result['status']}",
                }

        except Exception as e:
            print(f"Exceção ao verificar pagamento {payment_id}: {traceback.format_exc()}")
            return {"success": False, "paid": False, "error": str(e)}

    def activate_subscription(self, user_id, db, days=None):
        """Ativa a assinatura do usuário"""
        try:
            if days is None:
                days = SUBSCRIPTION_DAYS
            end_date = datetime.now() + timedelta(days=days)
            db.set_subscription(user_id, end_date)
            return {"success": True, "end_date": end_date}
        except Exception as e:
            return {"success": False, "error": str(e)}
