"""
API Client para TIM Pontos - Reconstrução 2026
Adaptações: PyJWT>=2.9 (algorithms explícito), okhttp 4.12.0, Android 14,
Dart/3.6 mantido (app TIM atual), urllib3>=2.2
"""

import requests
import time
import random
from uuid import uuid4
from typing import Dict, Any, Optional, List
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (OPERATORS, PROXY_ENABLED, PROXY_HOST, PROXY_PORT,
                    PROXY_USER, PROXY_PASS, PROXY_MAX_ATTEMPTS, PROXY_TIMEOUT)

# 2026: PyJWT>=2.9 — decode com algorithms obrigatório
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
        return _jwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=["HS256", "RS256"]
        )
    except Exception:
        return {}


try:
    from config_tim import *
except ImportError:
    print("❌ config_tim.py não encontrado!")
    exit()

ZONE_UUID = "bbdef37d-f5c4-4b19-9cfb-ed6e8f43fa2f"


class APIClientTim:
    def __init__(self, base_url: str = None, database=None):
        self.base_url    = base_url or API_BASE_URL
        self.session     = requests.Session()
        self.session.verify = False
        self.database    = database
        self.app_version = "3.1.04"
        self.channel     = "ANDROID"
        # 2026: okhttp 4.12.0 (versão atual do app TIM)
        self.user_agent  = "okhttp/4.12.0"
        self.artemis_channel_uuid = "timfun-ae4e-4d0e-ad87-f398af9d38d2"
        self.x_access_token = OPERATORS["tim"]["api_access_token"]
        self.proxy_enabled  = PROXY_ENABLED
        self.proxy_configured = False
        self.proxy_info = {"ip": "desconhecido", "country": "desconhecido"}
        if self.proxy_enabled:
            print("Proxy está habilitado nas configurações. Configurando para TIM...")
            self.setup_proxy()

    def setup_proxy(self):
        """Configura e testa o proxy para a sessão da TIM."""
        if PROXY_ENABLED:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
            print(f"[TIM] Proxy ativado: {PROXY_HOST}:{PROXY_PORT}")
        else:
            self.session.proxies = {}
            print("[TIM] Proxy desativado.")

    def request_pin(self, msisdn: str) -> Dict[str, Any]:
        """Solicita o envio do PIN por SMS para o número informado."""
        print(f"[TIM] [DEBUG] Chamando request_pin para {msisdn}")
        url = ACTIVATE_ENDPOINT
        # 2026: JWT inicial TIM — atualizar quando expirar
        JWT_INICIAL = (
            "eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJBTkRST0lEIiwiWC1UT0tFTi1WRVJTSU9OIjoiMS4wLjAiLCJYLVVTRVIt"
            "SUQiOiIxNjk3NjA0ODE5MyIsIlgtV0FMTEVULUlEIjoiMzBjYzdlYTQ1N2M2ZSIsImV4cCI6MTc1OTU0MTg1NSwiaWF0IjoxNzUx"
            "NzY1ODU1LCJpc3MiOiJQQ0dSWjFqMWxmUXJ4VDBHOGFKd29KMmJJQVg4QUFYWiIsInN1YiI6IjE2OTc2MDQ4MTkzIn0."
            "n3p5UDxK75QjRmRs_I621V4BYvwsTy5jh8JaISSiE0M"
        )
        headers = {
            "accept-encoding":          "gzip",
            "content-type":             "application/json",
            "host":                     "api.timfun.com.br",
            "user-agent":               "Dart/3.6 (dart:io)",
            "x-app-version":            self.app_version,
            "x-authorization":          JWT_INICIAL,
            "x-channel":                self.channel,
            "x-connectivity":           "true",
            "x-ignore-session-expired": "true",
            "x-msisdn":                 msisdn,
        }
        data = {"msisdn": msisdn}
        print(f"[TIM] [DEBUG] Headers: {headers}")
        print(f"[TIM] [DEBUG] Data: {data}")
        try:
            resp = self.session.post(url, headers=headers, json=data, timeout=15)
            print(f"[TIM] [DEBUG] Status: {resp.status_code}, Response: {resp.text}")
            try:
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                print(f"[TIM] Erro ao solicitar PIN: status={resp.status_code}, resposta={resp.text}")
                return {
                    "success": False,
                    "error":    f"Status: {resp.status_code}",
                    "response": resp.text,
                    "headers":  dict(resp.headers),
                }
        except Exception as e:
            print(f"[TIM] Exceção ao solicitar PIN: {str(e)}")
            return {"success": False, "error": str(e)}

    def validate_pin(self, msisdn: str, token: str, pin_code: str) -> Dict[str, Any]:
        """Valida o PIN recebido por SMS."""
        url     = VALIDATE_ENDPOINT
        headers = {
            "accept-encoding":          "gzip",
            "content-type":             "application/json",
            "host":                     "api.timfun.com.br",
            "user-agent":               self.user_agent,
            "x-app-version":            self.app_version,
            "x-channel":                self.channel,
            "x-connectivity":           "true",
            "x-ignore-session-expired": "true",
            "x-msisdn":                 msisdn,
            "x-pincode":                pin_code,
            "x-authorization":          token,
        }
        data = {"token": pin_code}
        try:
            resp      = self.session.post(url, headers=headers, json=data, timeout=15)
            resp.raise_for_status()
            result    = resp.json()
            new_token = resp.headers.get("X-Authorization")
            if new_token:
                result["authorization"] = new_token
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_campaigns(self, token: str, user_id: str) -> Dict[str, Any]:
        """Busca campanhas/vídeos disponíveis para o usuário TIM."""
        if not user_id:
            return {"success": False, "error": "user_id não fornecido"}

        zone_uuid  = ZONE_UUID
        url_camp   = f"https://api.timfun.com.br/adserver/campaign/v3/{zone_uuid}"
        all_campaigns = []

        headers_camp = {
            "Accept-Encoding":        "gzip",
            "Connection":             "Keep-Alive",
            "Content-Type":           "application/json",
            "Host":                   "api.timfun.com.br",
            "User-Agent":             self.user_agent,
            "x-access-token":         self.x_access_token,
            "X-APP-VERSION":          self.app_version,
            "X-ARTEMIS-CHANNEL-UUID": self.artemis_channel_uuid,
            "X-AUTHORIZATION":        token,
            "X-CHANNEL":              self.channel,
        }

        if user_id.isdigit() and len(user_id) >= 10:
            return {"success": False, "error": "user_id inválido (não pode ser número de telefone)"}

        body = {
            "context": {
                "appVersion":   self.app_version,
                "product":      "windows_x86_64",
                "os":           "ANDROID",
                "battery":      "85",
                "deviceId":     str(uuid4()),
                "long":         "-47.3688692049563",
                "manufacturer": "Microsoft Corporation",
                "carrier":      "",
                "adId":         str(uuid4()),
                "osVersion":    "14",   # 2026: Android 14
                "appId":        "com.adfone.timfun",
                "sdkVersion":   "3.3.0.4-rc1",
                "model":        "Subsystem for Android(TM)",
                "brand":        "Windows",
                "lat":          "-21.488044542280523",
                "hardware":     "windows_x86_64",
                "eventDate":    str(int(time.time() * 1000)),
            },
            "userId": user_id,
        }
        try:
            resp_camp = self.session.post(url_camp, headers=headers_camp, json=body, timeout=15)
            resp_camp.raise_for_status()
            data_camp = resp_camp.json()
            print(f"[TIM][DEBUG] Resposta /adserver/campaign/v3/{zone_uuid}:", data_camp)

            for camp in data_camp.get("campaigns", []):
                medias    = []
                main_data = camp.get("mainData", {})
                for m in main_data.get("media", []):
                    fallback = m.get("fallbackNoFill", {})
                    is_video = (
                        m.get("type") == "programatica"
                        and fallback.get("type") == "vast"
                        and fallback.get("modeVideo")
                        and fallback.get("originalContent")
                    )
                    if is_video:
                        medias.append({
                            "uuid":          m.get("uuid"),
                            "title":         m.get("title"),
                            "type":          m.get("type"),
                            "thumbnail":     m.get("thumbnail"),
                            "video_url":     fallback.get("originalContent"),
                            "vast_url":      fallback.get("content", {}).get("url"),
                            "proxy":         m.get("proxy", False),
                            "viewed":        m.get("viewed", False),
                            "config":        m.get("config", {}),
                            "reward":        camp.get("benefitOffers", []),
                            "campaign_id":   camp.get("campaignUuid"),
                            "campaign_name": camp.get("campaignName"),
                            "tracking_id":   camp.get("trackingId"),
                        })
                        print(f"[TIM][DEBUG] Vídeo válido: {m.get('uuid')}")
                    else:
                        print(f"[TIM][DEBUG] Mídia ignorada: {m.get('uuid')} ({m.get('type')})")

                campaign = {
                    "campaign_id": camp.get("campaignUuid"),
                    "trackingId":  camp.get("trackingId"),
                    "name":        camp.get("campaignName"),
                    "start_date":  camp.get("campaignStartDate"),
                    "end_date":    camp.get("campaignEndDate"),
                    "medias":      medias,
                    "benefitOffers": camp.get("benefitOffers", []),
                }
                if medias:
                    all_campaigns.append(campaign)
                else:
                    print(f"[TIM][DEBUG] Campanha sem vídeos válidos: {camp.get('campaignUuid')}")

            print(f"[TIM][DEBUG] Total de campanhas de vídeo: {len(all_campaigns)}")
            return {"success": True, "campaigns": all_campaigns}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def track_campaign(self, event: str, campaign_uuid: str, user_id: str,
                       request_id: str, media_uuid: Optional[str], token: str) -> Dict[str, Any]:
        """Rastreia eventos de campanha (impression, complete, etc)."""
        url     = "https://api.timfun.com.br/adserver/tracker"
        headers = {
            "Accept-Encoding":        "gzip",
            "Connection":             "Keep-Alive",
            "Content-Length":         "0",
            "Content-Type":           "application/json",
            "Host":                   "api.timfun.com.br",
            "User-Agent":             self.user_agent,
            "x-access-token":         self.x_access_token,
            "X-APP-VERSION":          self.app_version,
            "X-ARTEMIS-CHANNEL-UUID": self.artemis_channel_uuid,
            "X-AUTHORIZATION":        token,
            "X-CHANNEL":              self.channel,
        }
        if user_id.isdigit() and len(user_id) >= 10:
            return {"success": False, "error": "user_id inválido (não pode ser número de telefone)"}

        params = {"e": event, "c": campaign_uuid, "u": user_id, "requestId": request_id}
        if media_uuid:
            params["m"] = media_uuid
        try:
            resp = self.session.post(url, headers=headers, params=params, json={}, timeout=15)
            resp.raise_for_status()
            return {"success": True, "status_code": resp.status_code, "headers": dict(resp.headers)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_balance(self, token: str) -> Dict[str, Any]:
        """Obtém saldo de moedas/pontos para TIM usando o endpoint /home."""
        url     = "https://api.timfun.com.br/home"
        headers = {
            "accept-encoding": "gzip",
            "host":            "api.timfun.com.br",
            "user-agent":      "Dart/3.6 (dart:io)",
            "x-app-version":   self.app_version,
            "x-authorization": token,
            "x-channel":       self.channel,
            "x-connectivity":  "true",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data    = resp.json()
            wallet  = data.get("wallet", {})
            balance = wallet.get("balance", 0)
            return {"success": True, "balance": balance, "wallet": wallet}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_packages(self, token: str) -> Dict[str, Any]:
        """Obtém pacotes disponíveis para TIM usando o endpoint /prize-list."""
        url     = "https://api.timfun.com.br/prize-list"
        headers = {
            "accept-encoding": "gzip",
            "host":            "api.timfun.com.br",
            "user-agent":      "Dart/3.6 (dart:io)",
            "x-app-version":   self.app_version,
            "x-authorization": token,
            "x-channel":       self.channel,
            "x-connectivity":  "true",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data     = resp.json()
            packages = data.get("packages", [])
            result   = []
            for p in packages:
                result.append({
                    "id":          p.get("id"),
                    "name":        p.get("name"),
                    "description": p.get("description"),
                    "price":       p.get("price"),
                    "fullPrice":   p.get("fullPrice", p.get("price", 0)),
                    "discount":    p.get("discount"),
                    "amount":      p.get("amount"),
                    "free_bonus":  p.get("freeBonus", False),
                    "validity":    p.get("validity"),
                    "terms":       p.get("terms"),
                    "offers":      p.get("offers", []),
                })
            return {"success": True, "packages": result, "raw": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def redeem_package(self, token: str, package_id: str, user_id: str) -> Dict[str, Any]:
        """Resgata pacote para TIM usando o endpoint oficial /withdraw."""
        url     = "https://api.timfun.com.br/withdraw"
        headers = {
            "accept-encoding": "gzip",
            "content-type":    "application/json",
            "host":            "api.timfun.com.br",
            "user-agent":      "Dart/3.6 (dart:io)",
            "x-app-version":   self.app_version,
            "x-authorization": token,
            "x-channel":       self.channel,
            "x-connectivity":  "true",
        }
        data = {"packageId": int(package_id), "destinationMsisdn": None}
        try:
            resp = self.session.post(url, headers=headers, json=data, timeout=15)
            print(f"[TIM][DEBUG] /withdraw: status={resp.status_code}, body={resp.text}")
            try:
                result = resp.json()
            except Exception:
                result = {"raw": resp.text}
            if resp.status_code != 200:
                error_msg = result.get("message") or result.get("error") or resp.text or "Erro desconhecido"
                return {
                    "success":     False,
                    "status_code": resp.status_code,
                    "error":       error_msg,
                    "response":    result,
                    "headers":     dict(resp.headers),
                }
            return {
                "success":     True,
                "status_code": resp.status_code,
                "response":    result,
                "headers":     dict(resp.headers),
            }
        except Exception as e:
            print(f"[TIM][DEBUG] Exceção no redeem_package: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_internet_quota(self, token: str) -> Dict[str, Any]:
        """Quota de internet TIM — endpoint não disponível."""
        return {"success": False, "error": "Endpoint de quota de internet não fornecido para TIM."}

    def check_auth_validity(self, token: str) -> Dict[str, Any]:
        """Valida o token de autenticação para TIM."""
        return {"success": True}

    def process_videos(self, user_id: str, token: str, campaign_uuid: str,
                       request_id: str, medias: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Processa todos os vídeos de uma campanha simulando visualização."""
        total     = len(medias)
        completed = 0
        for media in medias:
            media_uuid = media.get("uuid")
            track_resp = self.track_campaign("impression", campaign_uuid, user_id, request_id, media_uuid, token)
            if not track_resp.get("success"):
                continue
            time.sleep(random.uniform(1, 2))
            track_resp2 = self.track_campaign("complete", campaign_uuid, user_id, request_id, media_uuid, token)
            if track_resp2.get("success"):
                completed += 1
            time.sleep(random.uniform(0.2, 0.5))
        return {"success": True, "total": total, "completed": completed}

    def configure_for_operator(self, operator):
        pass

    def verify_pin(self, msisdn: str, pin_code: str) -> Dict[str, Any]:
        """Valida PIN e retorna dados no formato esperado pelo bot."""
        JWT_INICIAL = (
            "eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJBTkRST0lEIiwiWC1UT0tFTi1WRVJTSU9OIjoiMS4wLjAiLCJYLVVTRVIt"
            "SUQiOiI2NWIwZDU4ZjM1Yzk5Yjg1IiwiWC1XQUxMRVQtSUQiOiIzYWZiZTEwNjg0MjU2IiwiZXhwIjoxNzU5NTQxNzMyLCJpYXQi"
            "OjE3NTE3NjU3MzIsImlzcyI6IlBDR1JaMWoxbGZRcnhUMEc4YUp3b0oyYklBWDhBQVhaIiwic3ViIjoiNjViMGQ1OGYzNWM5OWI4NSJ9."
            "t9lASBc3YNatFx4OZQxuhMUF3HI8ClJktln6r28jgwE"
        )
        resp = self.validate_pin(msisdn, JWT_INICIAL, pin_code)
        if resp and (resp.get("authorization") or resp.get("data", {}).get("authorization")):
            authorization  = resp.get("authorization") or resp.get("data", {}).get("authorization")
            transaction_id = resp.get("transaction_id") or resp.get("X-TRANSACTION-ID") or ""
            user_id = None

            # Busca user_id correto do /home
            if authorization:
                home_resp = self.get_balance(authorization)
                if home_resp and home_resp.get("success") and home_resp.get("wallet", {}).get("id"):
                    user_id = home_resp["wallet"]["id"]

            # Fallback: decodifica JWT
            if not user_id and authorization:
                decoded = _decode_jwt_safe(authorization)
                user_id = decoded.get("X-USER-ID") or decoded.get("sub")

            if not user_id:
                user_id = msisdn

            return {
                "success": True,
                "data": {
                    "transaction_id": transaction_id,
                    "authorization":  authorization,
                    "user_id":        user_id,
                    "wallet_id":      "",
                },
            }
        else:
            return {"success": False, "error": resp.get("error", "Erro ao validar PIN")}

    def rotate_proxy(self):
        """Compatibilidade com bot_core"""
        return True, "Proxy desativado para TIM.", None, None
