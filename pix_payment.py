"""
Módulo simples de pagamento PIX
"""
import mercadopago
import json
import time
import traceback
from datetime import datetime, timedelta
from config import PIX_ACTUAL_PRICE, TRIAL_DAYS, SUBSCRIPTION_DAYS, MERCADO_PAGO_ACCESS_TOKEN

class PixPayment:
    def __init__(self, access_token):
        self.mp = mercadopago.SDK(access_token)
        self.default_token = access_token
            

    def create_pix_payment(self, user_id, phone, amount=None, description=None):
        """Cria um pagamento PIX"""
        try:
            # Busca token personalizado do revendedor e preço personalizado
            custom_token = None
            custom_price = None
            
            # CORREÇÃO: Melhoria na detecção de pagamentos de créditos
            is_credit_payment = description and ("crédito" in description.lower() or "credito" in description.lower())
            
            if is_credit_payment:
                # Para compra de créditos, sempre usar o token padrão
                custom_token = None
                print(f"Gerando pagamento para compra de créditos: {description}")
            else:
                # Verifica se cliente tem revendedor e se o revendedor tem token MP personalizado
                from database import Database
                db = Database()
                reseller_id = db.get_client_reseller(user_id)
                
                if reseller_id:
                    reseller_data = db.get_reseller_data(reseller_id)
                    custom_token = reseller_data.get('mercado_pago_token')
                    custom_price = db.get_reseller_custom_price(reseller_id)
                    
                    # Log para debug
                    print(f"Token do revendedor: {custom_token is not None}")
                    print(f"Preço personalizado: {custom_price}")
            
            # Se não definiu valor, usa o valor personalizado ou o padrão
            if amount is None:
                amount = custom_price if custom_price is not None else PIX_ACTUAL_PRICE
                    
            # Se não definiu descrição, usa a descrição padrão
            if description is None:
                description = f"Assinatura Bot - {SUBSCRIPTION_DAYS} dias"
            
            # CORREÇÃO: Adicionar informações externas para facilitar identificação
            payment_data = {
                "transaction_amount": amount,
                "description": description,
                "payment_method_id": "pix",
                "payer": {
                    "email": f"user{user_id}@bot.com"
                },
                # Referência para identificar melhor o pagamento
                "external_reference": f"USER_{user_id}_{'CREDIT' if is_credit_payment else 'BOT'}_PAY"
            }
            
            # Escolhe qual token usar
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
                
                # CORREÇÃO: Log do pagamento criado
                print(f"✅ Pagamento PIX criado: ID={payment_id}, Valor={amount}, Descrição='{description}'")
                
                # CORREÇÃO: Verifica se é pagamento de créditos e registra isso
                is_credit = "credit" in description.lower() or "crédito" in description.lower()
                if is_credit:
                    print(f"⭐ Identificado como pagamento de CRÉDITOS: ID={payment_id}")
                
                # CORREÇÃO CRÍTICA: Salvar token usado para verificação posterior
                used_token = custom_token if custom_token else self.default_token
                from database import Database
                db = Database()
                
                # Verificar se o token foi salvo com sucesso
                try:
                    # Salvar o token no banco de dados para usar na verificação
                    db.save_payment_token(payment_id, used_token)
                    print(f"Token salvo para pagamento {payment_id}")
                    print(f"✅ Token salvo com sucesso para pagamento {payment_id}")
                except Exception as e:
                    print(f"⚠️ Erro ao salvar token para pagamento {payment_id}: {e}")
                    # Segunda tentativa para garantir
                    try:
                        db.save_payment_token(payment_id, used_token)
                        print(f"✅ Token salvo na segunda tentativa")
                    except:
                        print(f"❌ Falha persistente ao salvar token")
                
                return {
                    "success": True,
                    "payment_id": payment_id,
                    "qr_code": payment["point_of_interaction"]["transaction_data"]["qr_code"],
                    "qr_code_base64": payment["point_of_interaction"]["transaction_data"]["qr_code_base64"],
                    "amount": payment["transaction_amount"],
                    "custom_token_used": bool(custom_token),
                    "is_credit_payment": is_credit_payment
                }
            else:
                print(f"❌ Erro ao criar pagamento PIX: {result}")
                return {"success": False, "error": f"Erro ao criar pagamento: {result}"}
                    
        except Exception as e:
            print(f"❌ Exceção ao criar pagamento PIX: {str(e)}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}

    def check_payment_status(self, payment_id, custom_token=None):
        """Verifica status de um pagamento com suporte a token personalizado"""
        try:
            # Verifica se foi fornecido um token personalizado
            if custom_token:
                print(f"Verificando pagamento {payment_id} com token personalizado")
                try:
                    mp_instance = mercadopago.SDK(custom_token)
                    result = mp_instance.payment().get(payment_id)
                    
                    if result["status"] == 200:
                        payment = result["response"]
                        status = payment["status"]
                        
                        print(f"✅ Status do pagamento {payment_id} com token personalizado: {status}")
                        
                        return {
                            "success": True,
                            "status": status,
                            "paid": status == "approved",
                            "description": payment.get("description", ""),
                            "external_reference": payment.get("external_reference", "")
                        }
                    else:
                        print(f"❌ Erro ao verificar com token personalizado: {result}")
                        # Retornamos falso para cair no fallback para token padrão
                        return {"success": False, "error": "Falha na verificação com token personalizado"}
                except Exception as e:
                    print(f"❌ Exceção ao verificar com token personalizado: {str(e)}")
                    return {"success": False, "error": str(e)}
            
            # Se não foi fornecido token personalizado ou se falhou, usa o token padrão
            print(f"Verificando pagamento {payment_id} com token padrão")
            result = self.mp.payment().get(payment_id)
            
            if result["status"] == 200:
                payment = result["response"]
                status = payment["status"]
                
                print(f"✅ Status do pagamento {payment_id} com token padrão: {status}")
                
                return {
                    "success": True,
                    "status": status,
                    "paid": status == "approved",
                    "description": payment.get("description", ""),
                    "external_reference": payment.get("external_reference", "")
                }
            else:
                print(f"❌ Erro ao verificar pagamento {payment_id} com token padrão: {result}")
                return {"success": False, "error": "Erro ao verificar pagamento"}
                
        except Exception as e:
            print(f"❌ Exceção ao verificar status do pagamento {payment_id}: {str(e)}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}             


    def calculate_trial_end(self):
        """Calcula fim do período de teste"""
        return datetime.now() + timedelta(days=TRIAL_DAYS)
    
    def calculate_subscription_end(self, current_end=None):
        """Calcula fim da assinatura"""
        if current_end and current_end > datetime.now():
            return current_end + timedelta(days=SUBSCRIPTION_DAYS)
        else:
            return datetime.now() + timedelta(days=SUBSCRIPTION_DAYS)