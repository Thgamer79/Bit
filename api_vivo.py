#!/usr/bin/env python3
"""
API Client para Vivo Pontos
Versão simplificada - apenas saldo, campanhas e pacotes
"""

import requests
import time
import random
from uuid import uuid4
from typing import Dict, Any, Optional, List
import jwt
from config import OPERATORS, PROXY_ENABLED, PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASS, PROXY_MAX_ATTEMPTS, PROXY_TIMEOUT

# Importar configurações da VIVO (será criado em config_vivo.py)
try:
    from config_vivo import *
except ImportError:
    print("❌ config_vivo.py não encontrado!")
    exit()

# Função utilitária para consultar saldo da carteira (Vivo)
def get_wallet_balance(user_token):
    """Consulta saldo da carteira"""
    url = f"{API_BASE_URL}/hmld"
    headers = MOBILE_HEADERS_BASE.copy()
    headers["x-authorization"] = user_token
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        balance = data.get("wallet", {}).get("balance", 0)
        return True, balance
    except Exception as e:
        # Adiciona log detalhado para depuração
        try:
            print(f"[DEBUG][VIVO] Erro ao consultar saldo: status={getattr(response, 'status_code', 'N/A')}, body={getattr(response, 'text', 'N/A')}")
        except Exception:
            pass
        print(f"[DEBUG][VIVO] Exception: {str(e)}")
        return False, f"Erro ao consultar saldo: {str(e)}"

# Função utilitária para obter campanhas (Vivo)
def get_campaigns_generic(wallet_id, user_token, endpoint_url):
    """Obtém campanhas de um endpoint específico (Vivo)"""
    headers = {
        "Accept-Encoding": "gzip",
        "Connection": "Keep-Alive",
        "Content-Type": "application/json; charset=UTF-8",
        "Host": "api.appvivopontos.com.br",
        "User-Agent": "okhttp/4.11.0",
        "x-access-token": API_ACCESS_TOKEN,
        "X-APP-VERSION": "3.1.02",
        "X-ARTEMIS-CHANNEL-UUID": API_ARTEMIS_CHANNEL_UUID,
        "X-AUTHORIZATION": user_token,
        "X-CHANNEL": "ANDROID"
    }
    payload = {
        "context": {
            "appVersion": "3.1.02",
            "product": "windows_x86_64",
            "os": "ANDROID",
            "battery": str(random.randint(20, 90)),
            "deviceId": "e453414b1d0a66d4",
            "long": "-47.36887510309128",
            "manufacturer": "Microsoft Corporation",
            "carrier": "",
            "adId": str(uuid4()),
            "osVersion": "13",
            "appId": "com.movile.android.appsvivo",
            "sdkVersion": "3.3.0.4-rc1",
            "model": "Subsystem for Android(TM)",
            "brand": "Windows",
            "lat": "-21.48806475896287",
            "hardware": "windows_x86_64",
            "eventDate": str(int(time.time() * 1000))
        },
        "userId": wallet_id
    }
    params = {"size": "100"}
    try:
        response = requests.post(endpoint_url, json=payload, headers=headers, params=params, timeout=20)
        if response.status_code == 204:
            return False, "Nenhuma campanha disponível", user_token
        response.raise_for_status()
        new_token = response.headers.get('x-authorization')
        data = response.json()
        campaigns = data.get("campaigns", [])
        if campaigns:
            return True, {"campaigns": campaigns, "raw_data": data}, new_token or user_token
        else:
            return False, "Nenhuma campanha encontrada", new_token or user_token
    except Exception as e:
        return False, f"Erro ao obter campanhas: {str(e)}", user_token

class APIClientVivo:
    def __init__(self, base_url: str = None, database=None):
        self.proxy_info = {'ip': 'desconhecido', 'country': 'desconhecido'}
        # URL base da Vivo
        self.base_url = base_url or API_BASE_URL
        
        # User-agent atualizado
        self.user_agent = "okhttp/4.12.0"
        
        self.session = requests.Session()
        
        # Headers atualizados conforme a Vivo
        self.session.headers.update({
            'x-channel': 'ANDROID',
            'x-app-version': '2.5.95',
            'user-agent': self.user_agent,
            'x-artemis-channel-uuid': API_ARTEMIS_CHANNEL_UUID,
            'x-access-token': API_ACCESS_TOKEN,
            'content-type': 'application/json; charset=UTF-8',
            'host': 'api.appvivopontos.com.br',
            'connection': 'Keep-Alive',
            'accept-encoding': 'gzip'
        })
        
        self.database = database
        self.setup_proxy()
        
    def setup_proxy(self):
        if PROXY_ENABLED:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
            self.session.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            print(f"[VIVO] Proxy ativado: {proxy_url}")
        else:
            self.session.proxies = {}
            print("[VIVO] Proxy desativado.")

    def _make_request(self, method: str, endpoint: str, headers: Optional[Dict[str, str]] = None, 
                     data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Faz requisição HTTP com tratamento de erros"""
        url = endpoint if endpoint.startswith('http') else f"{self.base_url}{endpoint}"
        # Sempre usar headers completos
        base_headers = MOBILE_HEADERS_BASE.copy()
        if headers:
            base_headers.update(headers)
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, headers=base_headers, params=params, timeout=20)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=base_headers, json=data, params=params, timeout=20)
            else:
                return {"success": False, "error": f"Método {method} não suportado"}
            # Atualiza token e wallet_id se vier novo token
            new_token = response.headers.get('x-authorization')
            if new_token:
                self.session.headers['x-authorization'] = new_token
                try:
                    decoded = jwt.decode(new_token, options={"verify_signature": False})
                    wallet_id = decoded.get("X-WALLET-ID", "")
                    if wallet_id:
                        self.session.headers['wallet_id'] = wallet_id
                except Exception:
                    pass
            response.raise_for_status()
            try:
                return {"success": True, "data": response.json(), "new_token": new_token}
            except:
                return {"success": True, "data": response.text, "new_token": new_token}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Erro na requisição: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Erro inesperado: {str(e)}"}

    def format_phone_number(self, ddd_number):
        """
        Formata número automaticamente adicionando 55
        Input: 11999999999 (DDD + número)
        Output: 5511999999999 (55 + DDD + número)
        """
        # Remover espaços e caracteres especiais
        clean_number = ''.join(filter(str.isdigit, ddd_number))
        
        # Se já tem 55 no início, retornar como está
        if clean_number.startswith('55') and len(clean_number) >= 12:
            return clean_number
        
        # Se tem 11 dígitos (DDD + 9 dígitos), adicionar 55
        if len(clean_number) == 11:
            return f"55{clean_number}"
        
        # Se tem 10 dígitos (DDD + 8 dígitos), adicionar 55
        if len(clean_number) == 10:
            return f"55{clean_number}"
        
        # Retornar como recebido se não se encaixar nos padrões
        return clean_number

    def request_pin(self, phone: str) -> Dict[str, Any]:
        """Solicita envio de PIN via SMS"""
        # Formatar número automaticamente
        msisdn = self.format_phone_number(phone)
        
        url = "https://api.appvivopontos.com.br/authentication/anonymous/activate"
        headers = AUTH_HEADERS_BASE.copy()
        headers["x-authorization"] = INITIAL_TOKEN
        headers["x-msisdn"] = msisdn
        
        payload = {"msisdn": msisdn}
        
        try:
            print(f"📱 Enviando SMS para {msisdn} (formatado de {phone})...")
            response = self.session.post(url, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
            
            if response.status_code == 200:
                return {"success": True, "message": f"📱 SMS enviado para {msisdn}!", "msisdn": msisdn}
            
            return {"success": False, "error": f"Erro: Status {response.status_code}"}
            
        except Exception as e:
            return {"success": False, "error": f"Erro ao solicitar SMS: {str(e)}"}

    def verify_pin(self, phone: str, pin: str) -> Dict[str, Any]:
        """Valida PIN recebido por SMS - padrão igual ao código fornecido pelo usuário"""
        # Formatar número automaticamente
        msisdn = self.format_phone_number(phone)
        url = "https://api.appvivopontos.com.br/authentication/anonymous/validate"
        headers = AUTH_HEADERS_BASE.copy()
        headers["x-authorization"] = INITIAL_TOKEN
        headers["x-msisdn"] = msisdn
        headers["x-pincode"] = pin
        try:
            print(f"🔐 Validando PIN {pin} para {msisdn}...")
            response = self.session.post(url, headers=headers, timeout=20)
            response.raise_for_status()
            # Verificar token nos headers (case-insensitive)
            new_token = response.headers.get('x-authorization') or response.headers.get('X-Authorization')
            if not new_token:
                print("❌ Token de autenticação não recebido da Vivo!")
                return {"success": False, "error": "Token de autenticação não recebido da Vivo"}
            # --- NOVO FLUXO: tentar obter token válido para saldo ---
            try:
                saldo_url = f"{API_BASE_URL}/hmld"
                saldo_headers = MOBILE_HEADERS_BASE.copy()
                saldo_headers["x-authorization"] = new_token
                saldo_resp = requests.get(saldo_url, headers=saldo_headers, timeout=20)
                saldo_resp.raise_for_status()
                saldo_token = saldo_resp.headers.get('x-authorization')
                if saldo_token:
                    print(f"[DEBUG][VIVO] Token atualizado após saldo: {saldo_token}")
                    new_token = saldo_token  # Atualiza para o token válido
            except Exception as e:
                print(f"[DEBUG][VIVO] Não foi possível atualizar token após saldo: {e}")
            # --- FIM NOVO FLUXO ---
            try:
                decoded_token = jwt.decode(new_token, options={"verify_signature": False})
                user_id = decoded_token.get("X-USER-ID") or decoded_token.get("sub")
                wallet_id = decoded_token.get("X-WALLET-ID", "")
                print(f"✅ Token obtido: {new_token[:50]}...")
                print(f"[DEBUG] Token capturado do header: {new_token}")
                return {
                    "success": True,
                    "data": {
                        "message": "✅ Autenticação bem-sucedida!",
                        "user_id": user_id,
                        "wallet_id": wallet_id,
                        "token": new_token,
                        "authorization": new_token,
                        "transaction_id": None
                    }
                }
            except Exception as e:
                print(f"Erro ao decodificar token: {e}")
                return {
                    "success": True,
                    "data": {
                        "message": "✅ Autenticação bem-sucedida!",
                        "user_id": "",
                        "wallet_id": "",
                        "token": new_token,
                        "authorization": new_token,
                        "transaction_id": None
                    }
                }
        except Exception as e:
            return {"success": False, "error": f"Erro ao validar PIN: {str(e)}", "data": {}}

    def get_balance(self, authorization: str) -> Dict[str, Any]:
        """Consulta saldo da carteira (Vivo) usando função utilitária funcional"""
        success, balance = get_wallet_balance(authorization)
        if success:
            return {"success": True, "balance": balance, "data": {"balance": balance}}
        else:
            return {"success": False, "error": balance, "data": {}}

    def get_campaigns(self, authorization: str, wallet_id: str, campaign_endpoint: str) -> Dict[str, Any]:
        """Obtém campanhas (Vivo) usando função utilitária funcional"""
        success, data, updated_token = get_campaigns_generic(wallet_id, authorization, campaign_endpoint)
        if success:
            return {"success": True, "data": data, "new_token": updated_token}
        else:
            return {"success": False, "error": data, "new_token": updated_token}

    def track_campaign(self, authorization: str, event: str, campaign_uuid: str,
                      wallet_id: str, request_id: str, media_uuid: str = None) -> Dict[str, Any]:
        """Rastreia eventos de campanha"""
        url = f"{self.base_url}/adserver/tracker"
        headers = MOBILE_HEADERS_BASE.copy()
        headers["x-authorization"] = authorization
        
        params = {
            "e": event,
            "c": campaign_uuid,
            "u": wallet_id,
            "requestId": request_id
        }
        
        if event == "complete" and media_uuid:
            params["m"] = media_uuid
        
        try:
            response = self.session.post(url, headers=headers, json={}, params=params, timeout=20)
            
            # Verificar se há novo token nos headers
            new_token = response.headers.get('x-authorization')
            if new_token:
                headers["x-authorization"] = new_token
            
            response.raise_for_status()
            return {"success": True, "data": {"message": "Evento rastreado!"}, "new_token": new_token}
            
        except Exception as e:
            return {"success": False, "error": f"Erro ao rastrear evento {event}: {str(e)}", "data": {}}

    def redeem_package(self, authorization: str, destination_phone: str, api_package_id: int) -> Dict[str, Any]:
        """Resgata pacote (Vivo) usando a API oficial"""
        url = "https://api.appvivopontos.com.br/withdraw"
        headers = {
            "accept-encoding": "gzip",
            "content-type": "application/json",
            "host": "api.appvivopontos.com.br",
            "user-agent": "Dart/3.6 (dart:io)",
            "x-app-version": "3.1.02",
            "x-authorization": authorization,
            "x-channel": "ANDROID",
            "x-connectivity": "true"
        }
        payload = {
            "packageId": api_package_id,
            "destinationMsisdn": destination_phone  # Passe o número já formatado
        }
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "SUCCESS":
                return {"success": True, "data": {"message": data.get("message", "Pacote resgatado com sucesso")}, "new_token": authorization}
            else:
                # Retorna a mensagem de erro detalhada da API para o usuário final
                return {"success": False, "error": data.get("message", "Erro desconhecido ao resgatar pacote"), "new_token": authorization}
        except Exception as e:
            print(f"[DEBUG][VIVO] Erro ao resgatar pacote: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[DEBUG][VIVO] Status: {e.response.status_code}")
                print(f"[DEBUG][VIVO] Body: {e.response.text}")
                # Tenta extrair a mensagem do body para mostrar ao usuário
                try:
                    error_data = e.response.json()
                    error_message = error_data.get("message", str(e))
                except Exception:
                    error_message = str(e)
                return {"success": False, "error": error_message, "new_token": authorization}
            return {"success": False, "error": f"Erro ao resgatar pacote: {str(e)}", "new_token": authorization}

    def get_packages(self, authorization: str) -> Dict[str, Any]:
        """Obtém pacotes disponíveis da API oficial da Vivo"""
        url = "https://api.appvivopontos.com.br/prize-list/v2"
        headers = {
            "accept-encoding": "gzip",
            "host": "api.appvivopontos.com.br",
            "user-agent": "Dart/3.6 (dart:io)",
            "x-app-version": "3.1.02",
            "x-authorization": authorization,
            "x-channel": "ANDROID",
            "x-connectivity": "true"
        }
        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            # Retorna os pacotes no formato esperado pelo bot
            return {"success": True, "packages": data.get("packages", [])}
        except Exception as e:
            return {"success": False, "error": f"Erro ao buscar pacotes: {str(e)}"}

    def check_auth_validity(self, authorization: str) -> Dict[str, Any]:
        """Verifica se a autenticação ainda é válida"""
        try:
            # Tentar consultar saldo para verificar se o token ainda é válido
            result = self.get_balance(authorization)
            return {"success": result["success"], "data": {"valid": result["success"]}}
        except:
            return {"success": False, "data": {"valid": False}, "error": "Erro ao verificar autenticação"}

    def configure_for_operator(self, operator):
        pass

    def get_internet_quota(self, authorization: str) -> dict:
        """Retorna informação fictícia de quota de internet para compatibilidade."""
        # A Vivo não fornece quota de internet, então retorna um valor padrão
        return {
            'success': True,
            'remaining': 'N/A',
            'total': 'N/A',
            'message': 'Consulta de internet não disponível para Vivo.'
        }

    def rotate_proxy(self):
        """Método dummy para compatibilidade com o bot. Não faz rotação real de proxy para Vivo."""
        return True, "Proxy desativado para Vivo.", None, None 