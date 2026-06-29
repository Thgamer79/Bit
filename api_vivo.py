#!/usr/bin/env python3
"""
API Client para Vivo Pontos - Reconstrução 2026
Adaptações: PyJWT>=2.9 (verify_signature sem algoritmo explícito), okhttp UA atualizado,
User-Agent Dart/3.6 mantido (Vivo app 2026), urllib3>=2.2 sem warnings
"""

import requests
import time
import random
import warnings
from uuid import uuid4
from typing import Dict, Any, Optional, List
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (OPERATORS, PROXY_ENABLED, PROXY_HOST, PROXY_PORT,
                    PROXY_USER, PROXY_PASS, PROXY_MAX_ATTEMPTS, PROXY_TIMEOUT)

# 2026: PyJWT>=2.9 — import condicional seguro
try:
    import jwt as _jwt
    _JWT_OK = True
except ImportError:
    _jwt = None
    _JWT_OK = False


def _decode_jwt_safe(token: str) -> dict:
    """Decodifica JWT sem verificar assinatura — compatível com PyJWT>=2.9"""
    if not _JWT_OK or not token:
        return {}
    try:
        # PyJWT>=2.9: algorithms obrigatório mesmo com verify_signature=False
        return _jwt.decode(token, options={"verify_signature": False}, algorithms=["HS256", "RS256"])
    except Exception:
        return {}


try:
    from config_vivo import *
except ImportError:
    print("❌ config_vivo.py não encontrado!")
    exit()


def get_wallet_balance(user_token):
    """Consulta saldo da carteira (Vivo)"""
    url = f"{API_BASE_URL}/hmld"
    headers = MOBILE_HEADERS_BASE.copy()
    headers["x-authorization"] = user_token
    try:
        response = requests.get(url, headers=headers, timeout=20, verify=False)
        response.raise_for_status()
        data = response.json()
        balance = data.get("wallet", {}).get("balance", 0)
        return True, balance
    except Exception as e:
        try:
            print(f"[DEBUG][VIVO] Erro ao consultar saldo: status={getattr(response, 'status_code', 'N/A')}, body={getattr(response, 'text', 'N/A')}")
        except Exception:
            pass
        print(f"[DEBUG][VIVO] Exception: {str(e)}")
        return False, f"Erro ao consultar saldo: {str(e)}"


def get_campaigns_generic(wallet_id, user_token, endpoint_url):
    """Obtém campanhas de um endpoint específico (Vivo)"""
    headers = {
        "Accept-Encoding": "gzip",
        "Connection":      "Keep-Alive",
        "Content-Type":    "application/json; charset=UTF-8",
        "Host":            "api.appvivopontos.com.br",
        # 2026: okhttp 4.12.0 — versão atual do app Vivo 3.1.02
        "User-Agent":      "okhttp/4.12.0",
        "x-access-token":  API_ACCESS_TOKEN,
        "X-APP-VERSION":   "3.1.02",
        "X-ARTEMIS-CHANNEL-UUID": API_ARTEMIS_CHANNEL_UUID,
        "X-AUTHORIZATION": user_token,
        "X-CHANNEL":       "ANDROID",
    }
    payload = {
        "context": {
            "appVersion":    "3.1.02",
            "product":       "windows_x86_64",
            "os":            "ANDROID",
            "battery":       str(random.randint(20, 90)),
            "deviceId":      "e453414b1d0a66d4",
            "long":          "-47.36887510309128",
            "manufacturer":  "Microsoft Corporation",
            "carrier":       "",
            "adId":          str(uuid4()),
            "osVersion":     "14",          # 2026: Android 14
            "appId":         "com.movile.android.appsvivo",
            "sdkVersion":    "3.3.0.4-rc1",
            "model":         "Subsystem for Android(TM)",
            "brand":         "Windows",
            "lat":           "-21.48806475896287",
            "hardware":      "windows_x86_64",
            "eventDate":     str(int(time.time() * 1000)),
        },
        "userId": wallet_id,
    }
    params = {"size": "100"}
    try:
        response = requests.post(endpoint_url, json=payload, headers=headers,
                                 params=params, timeout=20, verify=False)
        if response.status_code == 204:
            return False, "Nenhuma campanha disponível", user_token
        response.raise_for_status()
        new_token = response.headers.get("x-authorization")
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
        self.proxy_info = {"ip": "desconhecido", "country": "desconhecido"}
        self.base_url   = base_url or API_BASE_URL
        # 2026: okhttp 4.12.0
        self.user_agent = "okhttp/4.12.0"
        self.session    = requests.Session()
        self.session.verify = False

        self.session.headers.update({
            "x-channel":              "ANDROID",
            "x-app-version":          "2.5.95",
            "user-agent":             self.user_agent,
            "x-artemis-channel-uuid": API_ARTEMIS_CHANNEL_UUID,
            "x-access-token":         API_ACCESS_TOKEN,
            "content-type":           "application/json; charset=UTF-8",
            "host":                   "api.appvivopontos.com.br",
            "connection":             "Keep-Alive",
            "accept-encoding":        "gzip",
        })

        self.database = database
        self.setup_proxy()

    def setup_proxy(self):
        if PROXY_ENABLED:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
            print(f"[VIVO] Proxy ativado: {PROXY_HOST}:{PROXY_PORT}")
        else:
            self.session.proxies = {}
            print("[VIVO] Proxy desativado.")

    def _make_request(self, method: str, endpoint: str,
                      headers: Optional[Dict[str, str]] = None,
                      data: Optional[Dict[str, Any]] = None,
                      params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Faz requisição HTTP com tratamento de erros"""
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"
        base_headers = MOBILE_HEADERS_BASE.copy()
        if headers:
            base_headers.update(headers)
        try:
            if method.upper() == "GET":
                response = self.session.get(url, headers=base_headers, params=params, timeout=20)
            elif method.upper() == "POST":
                response = self.session.post(url, headers=base_headers, json=data, params=params, timeout=20)
            else:
                return {"success": False, "error": f"Método {method} não suportado"}

            new_token = response.headers.get("x-authorization")
            if new_token:
                self.session.headers["x-authorization"] = new_token
                decoded = _decode_jwt_safe(new_token)
                wallet_id = decoded.get("X-WALLET-ID", "")
                if wallet_id:
                    self.session.headers["wallet_id"] = wallet_id

            response.raise_for_status()
            try:
                return {"success": True, "data": response.json(), "new_token": new_token}
            except Exception:
                return {"success": True, "data": response.text, "new_token": new_token}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Erro na requisição: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Erro inesperado: {str(e)}"}

    def format_phone_number(self, ddd_number):
        """Formata número adicionando 55 se necessário"""
        clean = "".join(filter(str.isdigit, ddd_number))
        if clean.startswith("55") and len(clean) >= 12:
            return clean
        if len(clean) in (10, 11):
            return f"55{clean}"
        return clean

    def request_pin(self, phone: str) -> Dict[str, Any]:
        """Solicita envio de PIN via SMS"""
        msisdn = self.format_phone_number(phone)
        url     = "https://api.appvivopontos.com.br/authentication/anonymous/activate"
        headers = AUTH_HEADERS_BASE.copy()
        headers["x-authorization"] = INITIAL_TOKEN
        headers["x-msisdn"]        = msisdn
        payload = {"msisdn": msisdn}
        try:
            print(f"📱 Enviando SMS para {msisdn} (de {phone})...")
            response = self.session.post(url, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
            if response.status_code == 200:
                return {"success": True, "message": f"📱 SMS enviado para {msisdn}!", "msisdn": msisdn}
            return {"success": False, "error": f"Erro: Status {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Erro ao solicitar SMS: {str(e)}"}

    def verify_pin(self, phone: str, pin: str) -> Dict[str, Any]:
        """Valida PIN recebido por SMS"""
        msisdn  = self.format_phone_number(phone)
        url     = "https://api.appvivopontos.com.br/authentication/anonymous/validate"
        headers = AUTH_HEADERS_BASE.copy()
        headers["x-authorization"] = INITIAL_TOKEN
        headers["x-msisdn"]        = msisdn
        headers["x-pincode"]       = pin
        try:
            print(f"🔐 Validando PIN {pin} para {msisdn}...")
            response = self.session.post(url, headers=headers, timeout=20)
            response.raise_for_status()

            new_token = (response.headers.get("x-authorization") or
                         response.headers.get("X-Authorization"))
            if not new_token:
                print("❌ Token de autenticação não recebido da Vivo!")
                return {"success": False, "error": "Token de autenticação não recebido da Vivo"}

            # Tenta renovar token via saldo
            try:
                saldo_url     = f"{API_BASE_URL}/hmld"
                saldo_headers = MOBILE_HEADERS_BASE.copy()
                saldo_headers["x-authorization"] = new_token
                saldo_resp  = requests.get(saldo_url, headers=saldo_headers, timeout=20, verify=False)
                saldo_resp.raise_for_status()
                saldo_token = saldo_resp.headers.get("x-authorization")
                if saldo_token:
                    print(f"[DEBUG][VIVO] Token atualizado após saldo: {saldo_token[:40]}...")
                    new_token = saldo_token
            except Exception as e:
                print(f"[DEBUG][VIVO] Não foi possível atualizar token após saldo: {e}")

            # 2026: _decode_jwt_safe com algorithms explícito
            decoded   = _decode_jwt_safe(new_token)
            user_id   = decoded.get("X-USER-ID") or decoded.get("sub", "")
            wallet_id = decoded.get("X-WALLET-ID", "")

            print(f"✅ Token obtido: {new_token[:50]}...")
            return {
                "success": True,
                "data": {
                    "message":        "✅ Autenticação bem-sucedida!",
                    "user_id":        user_id,
                    "wallet_id":      wallet_id,
                    "token":          new_token,
                    "authorization":  new_token,
                    "transaction_id": None,
                },
            }
        except Exception as e:
            return {"success": False, "error": f"Erro ao validar PIN: {str(e)}", "data": {}}

    def get_balance(self, authorization: str) -> Dict[str, Any]:
        """Consulta saldo da carteira (Vivo)"""
        success, balance = get_wallet_balance(authorization)
        if success:
            return {"success": True, "balance": balance, "data": {"balance": balance}}
        return {"success": False, "error": balance, "data": {}}

    def get_campaigns(self, authorization: str, wallet_id: str, campaign_endpoint: str) -> Dict[str, Any]:
        """Obtém campanhas (Vivo)"""
        success, data, updated_token = get_campaigns_generic(wallet_id, authorization, campaign_endpoint)
        if success:
            return {"success": True, "data": data, "new_token": updated_token}
        return {"success": False, "error": data, "new_token": updated_token}

    def track_campaign(self, authorization: str, event: str, campaign_uuid: str,
                       wallet_id: str, request_id: str, media_uuid: str = None) -> Dict[str, Any]:
        """Rastreia eventos de campanha"""
        url     = f"{self.base_url}/adserver/tracker"
        headers = MOBILE_HEADERS_BASE.copy()
        headers["x-authorization"] = authorization
        params  = {"e": event, "c": campaign_uuid, "u": wallet_id, "requestId": request_id}
        if event == "complete" and media_uuid:
            params["m"] = media_uuid
        try:
            response  = self.session.post(url, headers=headers, json={}, params=params, timeout=20)
            new_token = response.headers.get("x-authorization")
            if new_token:
                headers["x-authorization"] = new_token
            response.raise_for_status()
            return {"success": True, "data": {"message": "Evento rastreado!"}, "new_token": new_token}
        except Exception as e:
            return {"success": False, "error": f"Erro ao rastrear evento {event}: {str(e)}", "data": {}}

    def redeem_package(self, authorization: str, destination_phone: str, api_package_id: int) -> Dict[str, Any]:
        """Resgata pacote (Vivo)"""
        url     = "https://api.appvivopontos.com.br/withdraw"
        headers = {
            "accept-encoding": "gzip",
            "content-type":    "application/json",
            "host":            "api.appvivopontos.com.br",
            # 2026: Dart/3.6 (versão atual do flutter SDK no app Vivo)
            "user-agent":      "Dart/3.6 (dart:io)",
            "x-app-version":   "3.1.02",
            "x-authorization": authorization,
            "x-channel":       "ANDROID",
            "x-connectivity":  "true",
        }
        payload = {"packageId": api_package_id, "destinationMsisdn": destination_phone}
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "SUCCESS":
                return {"success": True, "data": {"message": data.get("message", "Pacote resgatado com sucesso")}, "new_token": authorization}
            return {"success": False, "error": data.get("message", "Erro desconhecido ao resgatar pacote"), "new_token": authorization}
        except Exception as e:
            print(f"[DEBUG][VIVO] Erro ao resgatar pacote: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_data = e.response.json()
                    return {"success": False, "error": error_data.get("message", str(e)), "new_token": authorization}
                except Exception:
                    pass
            return {"success": False, "error": f"Erro ao resgatar pacote: {str(e)}", "new_token": authorization}

    def get_packages(self, authorization: str) -> Dict[str, Any]:
        """Obtém pacotes disponíveis da API oficial da Vivo"""
        url     = "https://api.appvivopontos.com.br/prize-list/v2"
        headers = {
            "accept-encoding": "gzip",
            "host":            "api.appvivopontos.com.br",
            "user-agent":      "Dart/3.6 (dart:io)",
            "x-app-version":   "3.1.02",
            "x-authorization": authorization,
            "x-channel":       "ANDROID",
            "x-connectivity":  "true",
        }
        try:
            response = requests.get(url, headers=headers, timeout=20, verify=False)
            response.raise_for_status()
            data = response.json()
            return {"success": True, "packages": data.get("packages", [])}
        except Exception as e:
            return {"success": False, "error": f"Erro ao buscar pacotes: {str(e)}"}

    def check_auth_validity(self, authorization: str) -> Dict[str, Any]:
        """Verifica se a autenticação ainda é válida"""
        try:
            result = self.get_balance(authorization)
            return {"success": result["success"], "data": {"valid": result["success"]}}
        except Exception:
            return {"success": False, "data": {"valid": False}, "error": "Erro ao verificar autenticação"}

    def configure_for_operator(self, operator):
        pass

    def get_internet_quota(self, authorization: str) -> dict:
        """Retorna informação de quota de internet (Vivo não fornece via API)."""
        return {
            "success":  True,
            "remaining": "N/A",
            "total":     "N/A",
            "message":   "Consulta de internet não disponível para Vivo.",
        }

    def rotate_proxy(self):
        """Compatibilidade com bot_core"""
        return True, "Proxy desativado para Vivo.", None, None
