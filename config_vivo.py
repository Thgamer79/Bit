# ============= CONFIGURAÇÕES DO BOT VIVO PONTOS V3 TURBO =============

# TELEGRAM BOT (OBRIGATÓRIO - CONFIGURE AQUI)
#TELEGRAM_TOKEN = "7880581319:AAE5luIEk9cGir57Vnp3eCiLzNdEuy-FpJA"  # Substitua pelo token do @BotFather
#ADMIN_ID = 5761539332                  # Substitua pelo seu ID do Telegram

# WEBHOOK SQUARECLOUD (IMPORTANTE - CONFIGURE COM SUA URL REAL APÓS DEPLOY)
#WEBHOOK_BASE_URL = "https://botvivo.squareweb.app/"  # 🔴 SUBSTITUA pela sua URL da SquareCloud
WEBHOOK_SECRET = "vivo_bot_webhook_secret_2025"    # Pode deixar assim

# API VIVO PONTOS (NÃO ALTERAR)
API_BASE_URL = "https://api.appvivopontos.com.br/39dd54c0-9ea1-4708-a9c5-5120810b3b72"
API_ACCESS_TOKEN = "4e82abb4-2718-4d65-bcd4-c4e147c3404f"
API_ARTEMIS_CHANNEL_UUID = "vivo-pontos-10ad-400c-88d9-fc32e2371e36"

# TOKENS INICIAIS (NÃO ALTERAR)
INITIAL_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJBTkRST0lEIiwiWC1UT0tFTi1WRVJTSU9OIjoiMS4wLjAiLCJYLVVTRVItSUQiOiJlNjg5NDcxZGJlOTI2NjRmIiwiWC1XQUxMRVQtSUQiOiI2NmE1OTA1MTdhODc1IiwiZXhwIjoxNzU2ODE3MzY0LCJpYXQiOjE3NDkwNDEzNjQsImlzcyI6ImNZNzhuM2hldWt5d2E0aHpQdThYeFBxTk1YaE1DQjI0Iiwic3ViIjoiZTY4OTQ3MWRiZTkyNjY0ZiJ9.gdkCFWBUtTf3m2a09P9n_mnkqyxzCIR0WNO_DOTsXrM"

# ENDPOINTS DA API (NÃO ALTERAR)
MOBILE_CAMPAIGN_ENDPOINT = "https://api.appvivopontos.com.br/adserver/campaign/v3/99f9c90a-b13e-419a-b53d-f47f6f2dea35"
RESPESCAGEM_CAMPAIGN_ENDPOINT = "https://api.appvivopontos.com.br/adserver/campaign/v3/dbf70686-e31a-11ef-bb8e-0680334bb059"
WITHDRAW_ENDPOINT = "https://api.appvivopontos.com.br/withdraw"

# MERCADO PAGO CONFIGURAÇÕES (IMPORTANTE - CONFIGURE SUA KEY REAL)
#MERCADO_PAGO_ACCESS_TOKEN = "APP_USR-7724660828833513-060611-4ec029643072f66c80890b639d645a86-30033708"  # 🔴 Sua key real
#PIX_ACTUAL_PRICE = 14.90      # 🔴 Preço mensal em reais
#TRIAL_DAYS = 1               # Dias grátis para novos usuários
#SUBSCRIPTION_DAYS = 30       # Dias por renovação

# CONFIGURAÇÕES DE PROXY (OPCIONAL)
#PROXY_ENABLED = False     # True para usar proxy, False para desabilitar
#PROXY_HOST = "brd.superproxy.io"
#PROXY_PORT = 33335
#PROXY_USER = "brd-customer-hl_4f76f27d-zone-mobile_proxy1"
#PROXY_PASS = "pi7yppp91fe3"

# CONFIGURAÇÕES DO BANCO DE DADOS
#DATABASE_PATH = "vivo_bot.db"

# HEADERS DA API (NÃO ALTERAR)
MOBILE_HEADERS_BASE = {
    "x-access-token": API_ACCESS_TOKEN,
    "x-channel": "ANDROID",
    "x-app-version": "2.5.95",
    "x-artemis-channel-uuid": API_ARTEMIS_CHANNEL_UUID,
    "content-type": "application/json; charset=UTF-8",
    "host": "api.appvivopontos.com.br",
    "connection": "Keep-Alive",
    "accept-encoding": "gzip",
    "user-agent": "okhttp/4.12.0"
}

AUTH_HEADERS_BASE = {
    "user-agent": "Dart/3.6 (dart:io)",
    "x-channel": "ANDROID",
    "accept-encoding": "gzip",
    "host": "api.appvivopontos.com.br",
    "content-type": "application/json",
    "x-app-version": "2.5.95"
}

# ⚡ CONFIGURAÇÕES DE TEMPO SUPER ACELERADAS (MÁXIMA VELOCIDADE)
VIDEO_PROCESSING_DELAYS = {
    "optimized_delay": 0.01,  # 0.01 segundos = SUPER RÁPIDO (10x mais rápido que antes!)
    "between_videos": 0.5,   # 0.5 segundos entre vídeos
    "between_campaigns": 1.0  # 1 segundo entre campanhas
}

# MENSAGENS DO SISTEMA PERSONALIZADAS
MESSAGES = {
    "welcome": "🎮 VIVO PONTOS BOT V3 TURBO\n\n✨ FUNCIONALIDADES PREMIUM:\n⚡ • Coleta em MÁXIMA VELOCIDADE\n🎯 • Análise instantânea de campanhas\n🚀 • Sistema otimizado nativo\n🔄 • Processamento TURBO (10x mais rápido)\n💸 • Sistema de transferência automático\n🔒 • Conexão segura com proxy\n💾 • Dados salvos permanentemente\n🎮 • Painel personalizado\n💰 • Consulta de saldo instantânea\n📦 • Loja de pacotes com moedas\n📱 • Número automático (só DDD + número)\n\n🚀 Sistema pronto para ação TURBO!",
    
    "subscription_expired": "⏰ SUA ASSINATURA EXPIROU!\n\n💎 Para continuar usando o bot TURBO, renove sua assinatura mensal.\n💰 Valor: R$ {price:.2f}/mês\n\n🎁 Recursos Premium:\n• ⚡ Coleta TURBO automatizada ilimitada (10x mais rápida)\n• 🎯 Análise instantânea de campanhas\n• 🔒 Conexão segura e anônima\n• 💸 Sistema de transferência\n• 📊 Estatísticas detalhadas\n• 💾 Dados salvos permanentemente\n• 🎮 Painel personalizado\n• 💰 Consulta de saldo em tempo real\n• 📦 Loja de pacotes completa\n• 📱 Login simplificado (só DDD + número)\n\n💳 Ative agora para velocidade máxima!",
    
    "proxy_connecting": "🔒 Estabelecendo conexão TURBO segura...",
    
    "collection_start": "🚀 INICIANDO ANÁLISE TURBO...\n\n🔒 Estabelecendo conexão segura\n🎯 Analisando campanhas disponíveis\n⚡ Otimizando configurações TURBO (velocidade máxima)",
    
    "payment_success": "✅ PAGAMENTO CONFIRMADO!\n\n🎉 Sua assinatura TURBO foi renovada automaticamente!\n⏰ Válida até: {end_date}\n\n🚀 Sistema pronto para coleta em MÁXIMA velocidade!",
    
    "login_saved": "✅ LOGIN SALVO COM SUCESSO!\n\n💾 Seus dados foram salvos permanentemente.\n🚀 Próximo acesso será automático!\n📱 Número processado automaticamente (55 + DDD + número)\n\n🎮 Bem-vindo ao painel personalizado:",
    
    "auto_collect_enabled": "🟢 COLETA AUTOMÁTICA ATIVADA!\n\n⚡ O sistema agora coletará moedas automaticamente em MÁXIMA velocidade.\n🎯 Você será notificado dos resultados.",
    
    "auto_collect_disabled": "🔴 COLETA AUTOMÁTICA DESATIVADA!\n\n⏸️ A coleta automática foi pausada.\n🎮 Use o painel para controle manual.",
    
    "balance_updated": "💰 SALDO ATUALIZADO!\n\nSeu saldo foi consultado em tempo real.",
    
    "webhook_payment": "⚡ PAGAMENTO DETECTADO!\n\nProcessando renovação automaticamente...",
    
    "package_purchased": "🎉 PACOTE COMPRADO COM SUCESSO!\n\n📦 {package_name} foi enviado para {phone}\n💰 Custo: {cost} moedas\n📱 Verifique em seu aparelho!",
    
    "package_insufficient_balance": "❌ SALDO INSUFICIENTE!\n\n📦 {package_name}\n💰 Custo: {cost} moedas\n💎 Seu saldo: {balance} moedas\n❗ Faltam: {needed} moedas\n\n🚀 Colete mais moedas em MÁXIMA velocidade!",
    
    "package_already_redeemed": "❌ VOCÊ JÁ RESGATOU ESTE PACOTE!\n\n🎁 Cada usuário pode resgatar o pacote bônus apenas uma vez.",
    
    "phone_format": "📱 NOVO FORMATO SIMPLIFICADO!\n\n✅ Digite apenas: DDD + NÚMERO\n📝 Exemplo: 11999999999\n\n⚡ O sistema adiciona o 55 automaticamente!\n🇧🇷 Resultado final: 5511999999999"
} 