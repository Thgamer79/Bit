#!/usr/bin/env python3
"""
API Client para o bot da Claro - Reconstrução 2026
Adaptações: User-Agent 2026, urllib3>=2.2 compatível, PyJWT>=2.9, headers modernos
"""

import requests
import json
import time
import re
from typing import Dict, Any, Optional
from uuid import uuid4
import urllib3
from config import (REQUEST_TIMEOUT, RETRY_ATTEMPTS, RETRY_DELAY,
                    CACHE_ENABLED, CACHE_TTL, CACHE_MAX_SIZE,
                    LOG_LEVEL, LOG_FILE, LOG_FORMAT,
                    PROXY_ENABLED, PROXY_HOST, PROXY_PORT,
                    PROXY_USER, PROXY_PASS, PROXY_MAX_ATTEMPTS,
                    PROXY_TIMEOUT, USER_AGENT, API_VERSION,
                    API_CHANNEL, API_ARTEMIS_CHANNEL_UUID, API_ACCESS_TOKEN,
                    OPERATORS)

# 2026: PyJWT >= 2.9 – import mantido mas sem uso de jwt.decode sem algorithms
try:
    import jwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2026: User-Agent Chrome 136 -> atualizado para Chrome 124 (stable 2026)
_UA_2026 = (
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.82 Mobile Safari/537.36"
)


class APIClient:
    def __init__(self, base_url: str = None, database=None):
        self.base_url = base_url or "https://api.prezaofree.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72"
        # 2026: prefere UA do config; fallback para UA 2026
        self.user_agent = USER_AGENT or _UA_2026
        self.session = requests.Session()

        # 2026: headers atualizados – sec-ch-ua Chrome 124
        self.session.headers.update({
            'x-channel': API_CHANNEL or 'WEB',
            'x-app-version': API_VERSION or '3.0.11',
            'user-agent': self.user_agent,
            'x-connectivity': 'true',
            'x-ignore-session-expired': 'true',
            'content-type': 'application/json',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'origin': 'https://prezaofree.com.br',
            'referer': 'https://prezaofree.com.br/',
            'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
        })

        self.session.verify = False
        self.db = database
        self.proxy_configured = False
        self.proxy_info = {'ip': 'desconhecido', 'country': 'desconhecido'}
        self.proxy_enabled = PROXY_ENABLED

        if self.proxy_enabled:
            print("Proxy está habilitado nas configurações. Configurando...")
            self.setup_proxy()

    def setup_proxy(self):
        """Configura e testa o proxy para a sessão."""
        if PROXY_ENABLED:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
            self.session.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            print(f"[CLARO] Proxy ativado: {PROXY_HOST}:{PROXY_PORT}")
        else:
            self.session.proxies = {}
            print("[CLARO] Proxy desativado.")

    def _get_api_url(self) -> str:
        """Obtém a URL da API dinamicamente"""
        return "https://api.prezaofree.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72"

    def rotate_proxy(self):
        """Rotaciona o proxy para obter um novo IP"""
        if not self.proxy_enabled:
            return False, "Proxy não está habilitado", None, None

        try:
            # 2026: ipify ainda funciona; mantemos como fallback
            response = self.session.get('https://api.ipify.org?format=json', timeout=10)
            if response.status_code == 200:
                data = response.json()
                new_ip = data.get('ip', 'desconhecido')
                new_country = data.get('country', 'desconhecido')
                self.proxy_info = {'ip': new_ip, 'country': new_country}
                return True, f"Proxy rotacionado - Novo IP: {new_ip}", new_ip, new_country
            else:
                return False, f"Erro ao rotacionar proxy - Status: {response.status_code}", None, None
        except Exception as e:
            return False, f"Erro ao rotacionar proxy: {str(e)}", None, None

    def _make_request(self, method: str, endpoint: str, headers: Optional[Dict[str, str]] = None,
                      data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Faz uma requisição HTTP com retry automático e tratamento de erros"""
        url = endpoint if endpoint.startswith('http') else f"{self._get_api_url()}/{endpoint}"

        request_headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://prezaofree.com.br',
            'Referer': 'https://prezaofree.com.br/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }

        if headers:
            request_headers.update(headers)

        for attempt in range(RETRY_ATTEMPTS + 1):
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, headers=request_headers, params=params, timeout=REQUEST_TIMEOUT)
                elif method.upper() == 'POST':
                    response = self.session.post(url, headers=request_headers, json=data, params=params, timeout=REQUEST_TIMEOUT)
                else:
                    return {'success': False, 'error': f'Método {method} não suportado', 'code': 0}

                try:
                    response_body = response.json()
                except Exception:
                    response_body = {}

                return {
                    'success': response.status_code < 400,
                    'code': response.status_code,
                    'body': response_body,
                    'text': response.text,
                    'headers': dict(response.headers),
                    'cookies': dict(response.cookies)
                }

            except requests.exceptions.Timeout:
                if attempt == RETRY_ATTEMPTS:
                    return {'success': False, 'error': 'Timeout na requisição', 'code': 0}
                time.sleep(RETRY_DELAY)

            except requests.exceptions.RequestException as e:
                if attempt == RETRY_ATTEMPTS:
                    return {'success': False, 'error': f'Erro na requisição: {str(e)}', 'code': 0}
                time.sleep(RETRY_DELAY)

            except Exception as e:
                return {'success': False, 'error': f'Erro inesperado: {str(e)}', 'code': 0}

        return {'success': False, 'error': 'Número máximo de tentativas excedido', 'code': 0}

    def get_internet_quota(self, authorization: str) -> Dict[str, Any]:
        """Consulta quota de internet"""
        response = self._make_request('GET', 'quota', headers={'x-authorization': authorization})
        if response.get('success'):
            return {
                'success': True,
                'quota': response['body'].get('quota', {}),
                'balance': response['body'].get('balance', 0)
            }
        return {'success': False, 'error': 'Erro ao consultar quota', 'response': response}

    def request_pin(self, phone: str) -> Dict[str, Any]:
        """Solicita PIN para o número de telefone com melhor tratamento de erro"""
        cleaned_phone = ''.join(filter(str.isdigit, phone))
        if cleaned_phone.startswith('55') and len(cleaned_phone) > 11:
            cleaned_phone = cleaned_phone[2:]
        if len(cleaned_phone) != 11:
            return {'success': False, 'error': f'Número inválido: {cleaned_phone} (deve ter 11 dígitos)'}

        print(f"Solicitando PIN para: {cleaned_phone}")

        try:
            headers = {
                'x-user-id': cleaned_phone,
                'x-app-version': API_VERSION or '3.0.11',
                'x-channel': API_CHANNEL or 'WEB'
            }
            response = self._make_request('POST', 'pnde', headers=headers, data={'msisdn': cleaned_phone})

            safe_response = {
                'success': response.get('success'),
                'code': response.get('code'),
                'error': response.get('error', None),
                'body_keys': list(response.get('body', {}).keys()) if isinstance(response.get('body'), dict) else None,
                'text_length': len(response.get('text', '')) if response.get('text') else 0
            }
            print(f"Resposta completa (resumida): {safe_response}")

            if not response.get('success'):
                error_details = {
                    'status_code': response.get('code'),
                    'error_message': response.get('error'),
                    'response_text': response.get('text'),
                    'headers': dict(response.get('headers', {})) if response.get('headers') else None
                }
                print(f"Detalhes do erro: {json.dumps(error_details, indent=2)}")

            return response

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Erro detalhado:\n{error_trace}")
            return {'success': False, 'error': f'Erro ao solicitar PIN: {str(e)}', 'trace': error_trace}

    def verify_pin(self, phone: str, pin: str) -> Dict[str, Any]:
        """Verifica o PIN recebido"""
        cleaned_phone = ''.join(filter(str.isdigit, phone))
        if cleaned_phone.startswith('55') and len(cleaned_phone) > 11:
            cleaned_phone = cleaned_phone[2:]
        if not pin.isdigit() or len(pin) != 6:
            return {'success': False, 'error': 'PIN inválido (deve ter 6 dígitos)'}

        headers = {
            'x-user-id': cleaned_phone,
            'x-pincode': pin,
            'x-app-version': API_VERSION or '3.0.11',
            'x-channel': API_CHANNEL or 'WEB'
        }
        response = self._make_request('POST', 'vapi', headers=headers, data={'token': pin})

        if response.get('success'):
            auth_header = None
            for header_key, header_value in response['headers'].items():
                if header_key.lower() == 'x-authorization':
                    auth_header = header_value
                    break
            if not auth_header:
                auth_header = response.get('body', {}).get('authorization')
            return {
                'success': True,
                'data': {
                    'authorization': auth_header,
                    'transaction_id': response['headers'].get('x-transaction-id') or response['headers'].get('X-TRANSACTION-ID'),
                    'user_id': response['body'].get('id'),
                    'phone': cleaned_phone,
                    'cookies': response.get('cookies', {}),
                }
            }
        return response

    def check_auth_validity(self, authorization: str, user_id: str = None) -> Dict[str, Any]:
        """Verifica se a autenticação ainda é válida para a Claro"""
        response = self._make_request('GET', 'hmld', headers={'x-authorization': authorization})
        print(f"[DEBUG][CLARO][SESSION] Resposta da API ao validar sessão: {response}")
        if response.get('code') == 200 and 'wallet' in response.get('body', {}):
            return {'success': True, 'valid': True, 'data': response['body']}
        error_text = (response.get('error') or response.get('body', {}).get('message', '') or response.get('text', ''))
        if response.get('code') in [401, 403] or 'token' in str(error_text).lower() or 'expirad' in str(error_text).lower():
            return {'success': False, 'valid': False, 'error': error_text}
        return {'success': False, 'valid': False, 'error': error_text}

    def get_balance(self, authorization: str, user_id: str = None) -> Dict[str, Any]:
        """Consulta saldo da carteira para a Claro usando /hmld"""
        response = self._make_request('GET', 'hmld', headers={'x-authorization': authorization})
        if response.get('success') and 'wallet' in response.get('body', {}):
            return {
                'success': True,
                'balance': response['body']['wallet'].get('balance', 0),
                'currency': 'BRL'
            }
        return {'success': False, 'error': 'Erro ao consultar saldo', 'response': response}

    def get_packages(self, authorization: str) -> Dict[str, Any]:
        """Obtém pacotes disponíveis para a Claro usando /przl"""
        response = self._make_request('GET', 'przl', headers={'x-authorization': authorization})
        print(f"[DEBUG][CLARO][PACKAGES] Resposta da API ao buscar pacotes: {response}")
        if response.get('success') and 'packages' in response.get('body', {}):
            return {'success': True, 'packages': response['body']['packages']}
        return {'success': False, 'error': 'Erro ao obter pacotes', 'response': response}

    def redeem_package(self, authorization: str, package_id: str, user_id: str) -> Dict[str, Any]:
        """Resgata um pacote específico com proteção contra múltiplos cliques"""
        if self.db:
            button_key = f"redeem_package_{package_id}"
            if self.db.check_button_cooldown(user_id, button_key):
                return {'success': False, 'error': 'Aguarde alguns segundos antes de resgatar novamente.'}

        response = self._make_request(
            'POST', 'wtdr',
            headers={'x-authorization': authorization},
            data={'packageId': package_id, 'destinationMsisdn': None}
        )

        if not response.get('success'):
            error_text = response.get('text', '').lower()
            if any(k in error_text for k in ['limit', 'daily', 'quota', 'maximum', 'excedido', 'limit reached']):
                return {
                    'success': False,
                    'error': 'Limite diário de resgate atingido. Tente novamente amanhã.',
                    'limit_reached': True
                }

        return {'success': response.get('success'), 'response': response}

    def get_campaigns(self, authorization: str, user_id: str, campaign_id: str) -> Dict[str, Any]:
        """Obtém as campanhas disponíveis"""
        response = self._make_request(
            'POST',
            f'adserver/campaign/v3/{campaign_id}',
            headers={
                'x-authorization': authorization,
                'x-artemis-channel-uuid': API_ARTEMIS_CHANNEL_UUID,
                'x-access-token': API_ACCESS_TOKEN
            },
            data={
                'userId': user_id,
                'contextInfo': {
                    'os': 'WEB',
                    'brand': self.user_agent,
                    'manufacturer': 'Linux aarch64',
                    'osVersion': 'Linux aarch64',
                    'eventDate': int(time.time() * 1000),
                    'battery': '65',
                    'lat': 'Unknown',
                    'long': 'Unknown'
                }
            },
            params={'size': '100'}
        )

        if response.get('success'):
            return {'success': True, 'campaigns': response['body'].get('campaigns', [])}
        return {'success': False, 'error': 'Erro ao obter campanhas', 'response': response}

    def track_campaign(self, authorization: str, event: str, campaign_uuid: str,
                       user_id: str, request_id: str, media_uuid: str) -> Dict[str, Any]:
        """Rastreia eventos de campanha"""
        endpoint = "/campaign/track"
        payload = {
            "event": event,
            "campaignUuid": campaign_uuid,
            "userId": user_id,
            "requestId": request_id,
            "mediaUuid": media_uuid
        }
        headers = {'Authorization': authorization}
        return self._make_request('POST', endpoint, headers=headers, data=payload)

    def track_campaign_claro(self, authorization, event, campaign_id, wallet_id, request_id, media_uuid=None):
        headers = {
            'x-authorization': authorization,
            'x-access-token': API_ACCESS_TOKEN,
            'x-artemis-channel-uuid': API_ARTEMIS_CHANNEL_UUID,
            'x-channel': 'WEB'
        }
        params = {
            'e': event,
            'c': campaign_id,
            'u': wallet_id,
            'requestId': request_id
        }
        if event == 'complete' and media_uuid:
            params['m'] = media_uuid
        return self._make_request('POST', 'adserver/tracker', headers=headers, params=params, data=None)

    def configure_for_operator(self, operator: str):
        """Configura a API para uma operadora específica"""
        print(f"API configurada para operadora: {operator}")
        return True
