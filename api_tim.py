"""
API Client para TIM Pontos
Estrutura completa - métodos de autenticação, campanhas, assistir vídeos, saldo, etc.
"""

import requests
import time
import random
from uuid import uuid4
from typing import Dict, Any, Optional, List
import jwt
from config import OPERATORS, PROXY_ENABLED, PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASS, PROXY_MAX_ATTEMPTS, PROXY_TIMEOUT

# Importar configurações da TIM (será criado em config_tim.py)
try:
    from config_tim import *
except ImportError:
    print("❌ config_tim.py não encontrado!")
    exit()

ZONE_UUID = "bbdef37d-f5c4-4b19-9cfb-ed6e8f43fa2f"  # zone_uuid fixo da TIM

class APIClientTim:
    def __init__(self, base_url: str = None, database=None):
        self.base_url = base_url or API_BASE_URL
        self.session = requests.Session()
        self.database = database
        self.app_version = "3.1.04"
        self.channel = "ANDROID"
        self.user_agent = "okhttp/4.11.0"
        self.artemis_channel_uuid = "timfun-ae4e-4d0e-ad87-f398af9d38d2"
        self.x_access_token = OPERATORS["tim"]["api_access_token"]  # Valor fixo do app oficial
        self.proxy_enabled = PROXY_ENABLED
        self.proxy_configured = False
        self.proxy_info = {'ip': 'desconhecido', 'country': 'desconhecido'}
        if self.proxy_enabled:
            print("Proxy está habilitado nas configurações. Configurando para TIM...")
            self.setup_proxy()

    def setup_proxy(self):
        """Configura e testa o proxy para a sessão da TIM."""
        if PROXY_ENABLED:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
            self.session.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            print(f"[TIM] Proxy ativado: {proxy_url}")
        else:
            self.session.proxies = {}
            print("[TIM] Proxy desativado.")

    def request_pin(self, msisdn: str) -> Dict[str, Any]:
        """Solicita o envio do PIN por SMS para o número informado."""
        print(f"[TIM] [DEBUG] Chamando request_pin para {msisdn}")
        url = ACTIVATE_ENDPOINT
        # Token JWT de exemplo (deve ser atualizado conforme necessário)
        JWT_EXEMPLO = "eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJBTkRST0lEIiwiWC1UT0tFTi1WRVJTSU9OIjoiMS4wLjAiLCJYLVVTRVItSUQiOiIxNjk3NjA0ODE5MyIsIlgtV0FMTEVULUlEIjoiMzBjYzdlYTQ1N2M2ZSIsImV4cCI6MTc1OTU0MTg1NSwiaWF0IjoxNzUxNzY1ODU1LCJpc3MiOiJQQ0dSWjFqMWxmUXJ4VDBHOGFKd29KMmJJQVg4QUFYWiIsInN1YiI6IjE2OTc2MDQ4MTkzIn0.n3p5UDxK75QjRmRs_I621V4BYvwsTy5jh8JaISSiE0M"
        headers = {
            "accept-encoding": "gzip",
            "content-length": "24",
            "content-type": "application/json",
            "host": "api.timfun.com.br",
            "user-agent": "Dart/3.6 (dart:io)",
            "x-app-version": self.app_version,
            "x-authorization": JWT_EXEMPLO,
            "x-channel": self.channel,
            "x-connectivity": "true",
            "x-ignore-session-expired": "true",
            "x-msisdn": msisdn,
        }
        data = {"msisdn": msisdn}
        print(f"[TIM] [DEBUG] Headers: {headers}")
        print(f"[TIM] [DEBUG] Data: {data}")
        try:
            resp = self.session.post(url, headers=headers, json=data, timeout=15)
            print(f"[TIM] [DEBUG] Status: {resp.status_code}, Response: {resp.text}, Headers: {dict(resp.headers)}")
            try:
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                # Log detalhado para debug
                print(f"[TIM] Erro ao solicitar PIN: status={resp.status_code}, resposta={resp.text}, headers={dict(resp.headers)}")
                return {"success": False, "error": f"Status: {resp.status_code}", "response": resp.text, "headers": dict(resp.headers)}
        except Exception as e:
            print(f"[TIM] Exceção ao solicitar PIN: {str(e)}")
            return {"success": False, "error": str(e)}

    def validate_pin(self, msisdn: str, token: str, pin_code: str) -> Dict[str, Any]:
        """Valida o PIN recebido por SMS."""
        url = VALIDATE_ENDPOINT
        headers = {
            "accept-encoding": "gzip",
            "content-type": "application/json",
            "host": "api.timfun.com.br",
            "user-agent": self.user_agent,
            "x-app-version": self.app_version,
            "x-channel": self.channel,
            "x-connectivity": "true",
            "x-ignore-session-expired": "true",
            "x-msisdn": msisdn,
            "x-pincode": pin_code,
            "x-authorization": token,
        }
        data = {"token": pin_code}
        try:
            resp = self.session.post(url, headers=headers, json=data, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            # O novo token pode vir no header X-Authorization
            new_token = resp.headers.get("X-Authorization")
            if new_token:
                result["authorization"] = new_token
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_campaigns(self, token: str, user_id: str) -> Dict[str, Any]:
        """Busca campanhas/vídeos disponíveis para o usuário TIM, acessando diretamente o endpoint correto."""
        if not user_id:
            return {"success": False, "error": "user_id não pode ser vazio!"}
        all_campaigns = []
        zone_uuid = ZONE_UUID
        url_camp = f"https://api.timfun.com.br/adserver/campaign/v3/{zone_uuid}?size=100"
        headers_camp = {
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "Content-Length": "483",  # pode ser sobrescrito pelo requests
            "Content-Type": "application/json; charset=UTF-8",
            "Host": "api.timfun.com.br",
            "User-Agent": self.user_agent,
            "x-access-token": self.x_access_token,  # Corrigido para valor fixo
            "X-APP-VERSION": self.app_version,
            "X-ARTEMIS-CHANNEL-UUID": self.artemis_channel_uuid,
            "X-AUTHORIZATION": token,
            "X-CHANNEL": self.channel,
        }
        # user_id NÃO deve ser o número de telefone! Use o ID interno correto.
        # Se você estiver armazenando o user_id como número, troque para o ID interno (exemplo: hash, uuid, etc)
        # Aqui, vamos garantir que não seja um número de telefone:
        if user_id.isdigit() and len(user_id) >= 10:
            return {"success": False, "error": "user_id inválido (não pode ser número de telefone)"}
        body = {
            "context": {
                "appVersion": self.app_version,
                "product": "windows_x86_64",
                "os": "ANDROID",
                "battery": "85",
                "deviceId": str(uuid4()),
                "long": "-47.3688692049563",
                "manufacturer": "Microsoft Corporation",
                "carrier": "",
                "adId": str(uuid4()),
                "osVersion": "13",
                "appId": "com.adfone.timfun",
                "sdkVersion": "3.3.0.4-rc1",
                "model": "Subsystem for Android(TM)",
                "brand": "Windows",
                "lat": "-21.488044542280523",
                "hardware": "windows_x86_64",
                "eventDate": str(int(time.time() * 1000)),
            },
            "userId": user_id,
        }
        try:
            resp_camp = self.session.post(url_camp, headers=headers_camp, json=body, timeout=15)
            resp_camp.raise_for_status()
            data_camp = resp_camp.json()
            print(f"[TIM][DEBUG] Resposta /adserver/campaign/v3/{zone_uuid}:", data_camp)
            for camp in data_camp.get('campaigns', []):
                medias = []
                main_data = camp.get("mainData", {})
                for m in main_data.get("media", []):
                    fallback = m.get("fallbackNoFill", {})
                    is_video = (
                        m.get("type") == "programatica" and
                        fallback.get("type") == "vast" and
                        fallback.get("modeVideo") and
                        fallback.get("originalContent")
                    )
                    if is_video:
                        medias.append({
                            "uuid": m.get("uuid"),
                            "title": m.get("title"),
                            "type": m.get("type"),
                            "thumbnail": m.get("thumbnail"),
                            "video_url": fallback.get("originalContent"),
                            "vast_url": fallback.get("content", {}).get("url"),
                            "proxy": m.get("proxy", False),
                            "viewed": m.get("viewed", False),
                            "config": m.get("config", {}),
                            "reward": camp.get("benefitOffers", []),
                            "campaign_id": camp.get("campaignUuid"),
                            "campaign_name": camp.get("campaignName"),
                            "tracking_id": camp.get("trackingId"),
                        })
                        print(f"[TIM][DEBUG] Adicionando vídeo válido: {m.get('uuid')}")
                    else:
                        print(f"[TIM][DEBUG] Ignorando mídia não-vídeo válido: {m.get('uuid')} ({m.get('type')})")
                campaign = {
                    "campaign_id": camp.get("campaignUuid"),
                    "trackingId": camp.get("trackingId"),
                    "name": camp.get("campaignName"),
                    "start_date": camp.get("campaignStartDate"),
                    "end_date": camp.get("campaignEndDate"),
                    "medias": medias,
                    "benefitOffers": camp.get("benefitOffers", []),
                }
                if medias:
                    all_campaigns.append(campaign)
                else:
                    print(f"[TIM][DEBUG] Campanha ignorada (sem vídeos válidos): {camp.get('campaignUuid')}")
            print(f"[TIM][DEBUG] Total de campanhas de vídeo encontradas: {len(all_campaigns)}")
            return {"success": True, "campaigns": all_campaigns}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def track_campaign(self, event: str, campaign_uuid: str, user_id: str, request_id: str, media_uuid: Optional[str], token: str) -> Dict[str, Any]:
        """Rastreia eventos de campanha (impression, complete, etc) com headers idênticos ao app oficial."""
        url = "https://api.timfun.com.br/adserver/tracker"
        headers = {
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "Content-Length": "0",
            "Content-Type": "application/json",
            "Host": "api.timfun.com.br",
            "User-Agent": self.user_agent,
            "x-access-token": self.x_access_token,  # Corrigido para valor fixo
            "X-APP-VERSION": self.app_version,
            "X-ARTEMIS-CHANNEL-UUID": self.artemis_channel_uuid,
            "X-AUTHORIZATION": token,
            "X-CHANNEL": self.channel,
        }
        # user_id NÃO deve ser o número de telefone! Use o ID interno correto.
        if user_id.isdigit() and len(user_id) >= 10:
            return {"success": False, "error": "user_id inválido (não pode ser número de telefone)"}
        params = {
            "e": event,
            "c": campaign_uuid,
            "u": user_id,
            "requestId": request_id,
        }
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
        url = f"https://api.timfun.com.br/home"
        headers = {
            "accept-encoding": "gzip",
            "host": "api.timfun.com.br",
            "user-agent": "Dart/3.6 (dart:io)",
            "x-app-version": self.app_version,
            "x-authorization": token,
            "x-channel": self.channel,
            "x-connectivity": "true",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            wallet = data.get("wallet", {})
            balance = wallet.get("balance", 0)
            return {"success": True, "balance": balance, "wallet": wallet}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_packages(self, token: str) -> Dict[str, Any]:
        """Obtém pacotes disponíveis para TIM usando o endpoint /prize-list, no formato padrão do bot."""
        url = "https://api.timfun.com.br/prize-list"
        headers = {
            "accept-encoding": "gzip",
            "host": "api.timfun.com.br",
            "user-agent": "Dart/3.6 (dart:io)",
            "x-app-version": self.app_version,
            "x-authorization": token,
            "x-channel": self.channel,
            "x-connectivity": "true",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            packages = data.get("packages", [])
            result = []
            for p in packages:
                pkg = {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description"),
                    "price": p.get("price"),
                    "fullPrice": p.get("fullPrice", p.get("price", 0)),  # Garante compatibilidade
                    "discount": p.get("discount"),
                    "amount": p.get("amount"),
                    "free_bonus": p.get("freeBonus", False),
                    "validity": p.get("validity"),
                    "terms": p.get("terms"),
                    "offers": p.get("offers", []),
                }
                result.append(pkg)
            return {"success": True, "packages": result, "raw": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def redeem_package(self, token: str, package_id: str, user_id: str) -> Dict[str, Any]:
        """Resgata pacote para TIM usando o endpoint oficial /withdraw."""
        url = "https://api.timfun.com.br/withdraw"
        headers = {
            "accept-encoding": "gzip",
            "content-length": "40",  # O requests sobrescreve, mas mantido para compatibilidade
            "content-type": "application/json",
            "host": "api.timfun.com.br",
            "user-agent": "Dart/3.6 (dart:io)",
            "x-app-version": self.app_version,
            "x-authorization": token,
            "x-channel": self.channel,
            "x-connectivity": "true",
        }
        data = {
            "packageId": int(package_id),
            "destinationMsisdn": None
        }
        try:
            resp = self.session.post(url, headers=headers, json=data, timeout=15)
            print(f"[TIM][DEBUG] Resposta do /withdraw: status={resp.status_code}, body={resp.text}, headers={dict(resp.headers)}")
            try:
                result = resp.json()
            except Exception:
                result = {"raw": resp.text}
            # Se não for sucesso, tenta extrair mensagem de erro
            if resp.status_code != 200:
                error_msg = result.get("message") or result.get("error") or resp.text or "Erro desconhecido"
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": error_msg,
                    "response": result,
                    "headers": dict(resp.headers)
                }
            return {
                "success": True,
                "status_code": resp.status_code,
                "response": result,
                "headers": dict(resp.headers)
            }
        except Exception as e:
            print(f"[TIM][DEBUG] Exceção no redeem_package: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_internet_quota(self, token: str) -> Dict[str, Any]:
        """Obtém quota de internet para TIM (endpoint não fornecido, retorna erro padrão)."""
        return {"success": False, "error": "Endpoint de quota de internet não fornecido para TIM."}

    def check_auth_validity(self, token: str) -> Dict[str, Any]:
        """Valida o token de autenticação para TIM (endpoint não fornecido, retorna sempre True para não bloquear o fluxo)."""
        # Como não há endpoint, retorna sucesso sempre
        return {"success": True}

    def process_videos(self, user_id: str, token: str, campaign_uuid: str, request_id: str, medias: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Processa todos os vídeos de uma campanha, simulando visualização e rastreando eventos."""
        total = len(medias)
        completed = 0
        for media in medias:
            media_uuid = media.get("uuid")
            # Evento de impressão (início do vídeo)
            track_resp = self.track_campaign("impression", campaign_uuid, user_id, request_id, media_uuid, token)
            if not track_resp.get("success"):
                continue
            # Simula tempo de visualização
            time.sleep(random.uniform(1, 2))
            # Evento de conclusão (fim do vídeo)
            track_resp2 = self.track_campaign("complete", campaign_uuid, user_id, request_id, media_uuid, token)
            if track_resp2.get("success"):
                completed += 1
            time.sleep(random.uniform(0.2, 0.5))
        return {"success": True, "total": total, "completed": completed}

    def configure_for_operator(self, operator):
        pass

    def verify_pin(self, msisdn: str, pin_code: str) -> Dict[str, Any]:
        """Valida o PIN recebido por SMS e retorna dados no formato esperado pelo bot, buscando o user_id correto do /home."""
        JWT_EXEMPLO = "eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJBTkRST0lEIiwiWC1UT0tFTi1WRVJTSU9OIjoiMS4wLjAiLCJYLVVTRVItSUQiOiI2NWIwZDU4ZjM1Yzk5Yjg1IiwiWC1XQUxMRVQtSUQiOiIzYWZiZTEwNjg0MjU2IiwiZXhwIjoxNzU5NTQxNzMyLCJpYXQiOjE3NTE3NjU3MzIsImlzcyI6IlBDR1JaMWoxbGZRcnhUMEc4YUp3b0oyYklBWDhBQVhaIiwic3ViIjoiNjViMGQ1OGYzNWM5OWI4NSJ9.t9lASBc3YNatFx4OZQxuhMUF3HI8ClJktln6r28jgwE"
        resp = self.validate_pin(msisdn, JWT_EXEMPLO, pin_code)
        if resp and (resp.get('authorization') or resp.get('data', {}).get('authorization')):
            authorization = resp.get('authorization') or resp.get('data', {}).get('authorization')
            transaction_id = resp.get('transaction_id') or resp.get('X-TRANSACTION-ID') or ''
            # Busca o user_id correto do /home
            user_id = None
            if authorization:
                home_resp = self.get_balance(authorization)
                if home_resp and home_resp.get('success') and home_resp.get('wallet', {}).get('id'):
                    user_id = home_resp['wallet']['id']
            # Fallbacks antigos (não usar mais, mas mantém para compatibilidade)
            if not user_id:
                user_id = resp.get('userId') or resp.get('user_id')
            if not user_id and authorization:
                try:
                    decoded = jwt.decode(authorization, options={"verify_signature": False})
                    user_id = decoded.get("X-USER-ID") or decoded.get("sub")
                except Exception as e:
                    user_id = None
            if not user_id:
                user_id = msisdn
            return {
                'success': True,
                'data': {
                    'transaction_id': transaction_id,
                    'authorization': authorization,
                    'user_id': user_id,
                    'wallet_id': ''
                }
            }
        else:
            return {
                'success': False,
                'error': resp.get('error', 'Erro ao validar PIN')
            }

    def rotate_proxy(self):
        return True, "Proxy desativado para TIM.", None, None

    # Métodos de autenticação, campanhas, saldo, pacotes, etc, serão implementados depois 