from config import RESELLER_CREDIT_PRICES

OPERATOR_COIN_AVERAGE = {
    "claro": 3500,
    "vivo": 2500,
    "tim": 2000
}

def get_mensagem_start():
    media_text = (
        f"🔵 Claro: ~{OPERATOR_COIN_AVERAGE['claro']:,} moedas/dia\n"
        f"🟢 Vivo: ~{OPERATOR_COIN_AVERAGE['vivo']:,} moedas/dia\n"
        f"🟡 TIM: ~{OPERATOR_COIN_AVERAGE['tim']:,} moedas/dia"
    )
    return (
        "🎉 Bem-vindo ao bot!\n\n"
        "📱 Este bot funciona para as operadoras:\n"
        "🔵 Claro\n🟢 Vivo\n🟡 TIM\n\n"
        "🤖 O que ele faz?\n"
        "- Coleta moedas automaticamente todos os dias para você!\n"
        "- Compra pacotes de internet de forma automática, sem você precisar se preocupar!\n"
        "- Tudo 100% automatizado, basta ativar e relaxar!\n\n"
        f"💰 Média de moedas coletadas por dia:\n{media_text}\n\n"
        "⚠️ Na TIM é obrigatório ter uma recarga válida nos últimos 30 dias para conseguir coletar moedas!\n\n"
        "💼 Temos planos de revenda disponíveis.\n"
        "Interessados, entrar em contato com @roxzinsrv.\n\n"
        "Para começar, selecione sua operadora e siga as instruções."
    )

def get_mensagem_start_old():
    revenda_text = "\n".join(
        [f"  • {item['credits']} créditos: R$ {item['price']:.2f}" for item in RESELLER_CREDIT_PRICES]
    )
    media_text = (
        f"🔵 Claro: ~{OPERATOR_COIN_AVERAGE['claro']:,} moedas/dia\n"
        f"🟢 Vivo: ~{OPERATOR_COIN_AVERAGE['vivo']:,} moedas/dia\n"
        f"🟡 TIM: ~{OPERATOR_COIN_AVERAGE['tim']:,} moedas/dia"
    )
    return f"""
👋 Olá! Seja bem-vindo ao nosso bot automatizado!

📱 Este bot funciona para as operadoras:
🔵 Claro
🟢 Vivo
🟡 TIM

🤖 O que ele faz?
- Coleta moedas automaticamente todos os dias para você!
- Compra pacotes de internet de forma automática, sem você precisar se preocupar!
- Tudo 100% automatizado, basta ativar e relaxar!

💰 Média de moedas coletadas por dia:\n{media_text}

⚠️ Na TIM é obrigatório ter uma recarga válida nos últimos 30 dias para conseguir coletar moedas!

🚀 Pronto para começar? Use o menu ou comandos para explorar as funções!
""" 