"""
Módulo de gerenciamento de revendedores
"""
import telebot
import json
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import RESELLER_CREDIT_PRICES, RESELLER_MIN_CREDITS, BOT_USERNAME, TRIAL_DAYS


class RevendaModule:
    def __init__(self, database, pix, bot, admin):
        self.db = database
        self.pix = pix
        self.bot = bot
        self.admin = admin
        self.active_clients_views = {}  # Controla visualizações ativas de clientes
        
    def is_reseller(self, user_id):
        """Verifica se um usuário é revendedor"""
        return self.db.is_reseller(user_id)
    
    def get_reseller_credits(self, user_id):
        """Obtem os créditos de um revendedor"""
        return self.db.get_reseller_credits(user_id)
    
    def generate_affiliate_link(self, user_id):
        """Gera um link de afiliado para o revendedor"""
        # Cria um código único baseado no ID do revendedor
        aff_code = self.db.generate_affiliate_code(user_id)
        affiliate_link = f"https://t.me/{BOT_USERNAME}?start=aff_{aff_code}"
        return affiliate_link
        
    def show_reseller_panel(self, message):
        """Mostra o painel de controle do revendedor"""
        user_id = str(message.from_user.id)
        
        if not self.is_reseller(user_id):
            self.bot.send_message(message.chat.id, "❌ Você não é um revendedor autorizado.")
            return
        
        # Busca informações do revendedor
        reseller_data = self.db.get_reseller_data(user_id)
        credits = reseller_data.get('credits', 0)
        total_clients = self.db.count_reseller_clients(user_id)
        active_clients = self.db.count_reseller_active_clients(user_id)
        trial_clients = self.db.count_reseller_trial_clients(user_id)  # Nova linha para contar clientes em teste
        
        # Cria o menu do revendedor
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("👥 Meus Clientes", "🔗 Gerar Link")
        markup.row("💳 Comprar Créditos", "⚙️ Configurações")
        markup.row("📊 Estatísticas", "🔙 Voltar ao Menu")
        
        # Mostra as informações
        self.bot.send_message(
            message.chat.id,
            f"🏪 PAINEL DE REVENDA\n\n"
            f"👤 Revendedor: {message.from_user.first_name}\n"
            f"🆔 ID: {message.from_user.id}\n\n"
            f"🎁 Testes concedidos: {trial_clients}\n"
            f"💰 Seus créditos: {credits}\n"
            f"👥 Total de clientes: {total_clients}\n"
            f"✅ Clientes ativos: {active_clients}\n"
            f"🎁 Clientes em teste: {trial_clients}\n\n"  # Nova linha mostrando clientes em teste
            f"Escolha uma opção abaixo:",
            reply_markup=markup
        )

            
    def _show_clients_page(self, chat_id, user_id):
        """Mostra uma página da lista de clientes com layout aprimorado"""
        view = self.active_clients_views.get(user_id)
        
        if not view:
            self.bot.send_message(chat_id, "❌ Erro ao carregar clientes. Tente novamente.")
            return
        
        clients = view['clients']
        page = view['page']
        total_pages = view['total_pages']
        per_page = 5
        
        # Calcula o intervalo da página atual
        start = (page - 1) * per_page
        end = min(start + per_page, len(clients))
        
        # Contagens para estatísticas
        active_count = 0
        trial_count = 0
        inactive_count = 0
        
        for client in clients:
            subscription = self.db.check_subscription(client['user_id'])
            if subscription["active"]:
                if subscription.get("is_trial", False):
                    trial_count += 1
                else:
                    active_count += 1
            else:
                inactive_count += 1
        
        # Formata a mensagem com estatísticas
        msg = f"<b>👥 MEUS CLIENTES</b> • Página {page}/{total_pages}\n\n"
        msg += f"<b>📊 ESTATÍSTICAS:</b>\n"
        msg += f"• Total: {len(clients)} clientes\n"
        msg += f"• ✅ Ativos: {active_count}\n"
        msg += f"• 🎁 Em teste: {trial_count}\n"
        msg += f"• ❌ Inativos: {inactive_count}\n\n"
        msg += f"<b>──────────────────</b>\n\n"
        
        # Lista de clientes da página atual com design melhorado
        for i, client in enumerate(clients[start:end], start + 1):
            subscription = self.db.check_subscription(client['user_id'])
            
            # Define ícones de status
            if subscription["active"]:
                if subscription.get("is_trial", False):
                    status_icon = "🔵"  # Azul para período de teste
                    status_text = "TESTE"
                else:
                    status_icon = "🟢"  # Verde para ativo
                    status_text = "ATIVO"
            else:
                status_icon = "🔴"  # Vermelho para inativo
                status_text = "INATIVO"
            
            days = subscription["days_left"] if subscription["active"] else 0
            name = client.get('name', f'Cliente {client["user_id"][-4:]}')
            user_id_str = client['user_id']
            phone = client.get('phone', 'N/A')
            
            # Formatação especial para clientes com poucos dias
            days_warning = ""
            if subscription["active"] and days <= 3:
                days_warning = "⚠️ "
            
            # Formata último acesso se disponível
            last_login = ""
            if client.get('last_login'):
                try:
                    login_date = datetime.fromisoformat(client.get('last_login'))
                    last_login = f"• Último acesso: {login_date.strftime('%d/%m/%Y')}"
                except:
                    pass
            
            # Montagem do card do cliente
            msg += f"<b>{i}. {status_icon} {name}</b>"
            if subscription.get("is_trial", False):
                msg += " 🎁"
            msg += f"\n"
            
            msg += f"  <code>{user_id_str}</code>\n"
            msg += f"  <b>{status_text}</b> • {days_warning}Dias: {days}\n"
            msg += f"  📱 {phone}\n"
            if last_login:
                msg += f"  {last_login}\n"
            msg += "\n"
        
        # Cria botões de navegação (mantendo os existentes)
        markup = telebot.types.InlineKeyboardMarkup()
        
        nav_row = []
        if page > 1:
            nav_row.append(telebot.types.InlineKeyboardButton("⬅️ Anterior", callback_data="clients_prev"))
        
        if page < total_pages:
            nav_row.append(telebot.types.InlineKeyboardButton("➡️ Próxima", callback_data="clients_next"))
        
        if nav_row:
            markup.row(*nav_row)
        
        # Mantém os mesmos botões de ação existentes
        markup.row(telebot.types.InlineKeyboardButton("🔄 Renovar Cliente", callback_data="clients_renew"))
        markup.row(telebot.types.InlineKeyboardButton("🗑️ Deletar Cliente", callback_data="clients_delete"))
        
        # Envia a mensagem com formatação HTML
        self.bot.send_message(chat_id, msg, reply_markup=markup, parse_mode="HTML")


        
    def start_renew_client(self, callback_query):
        """Inicia o processo de renovação de um cliente"""
        user_id = str(callback_query.from_user.id)
        
        # Verifica se é revendedor
        if not self.is_reseller(user_id):
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Você não é um revendedor autorizado.",
                show_alert=True
            )
            return
        
        # Verifica se tem créditos suficientes
        credits = self.db.get_reseller_credits(user_id)
        
        if credits < 1:
            self.bot.answer_callback_query(
                callback_query.id,
                f"❌ Você precisa de pelo menos 1 crédito. Atualmente tem {credits}.",
                show_alert=True
            )
            return
        
        # Responde ao callback
        self.bot.answer_callback_query(callback_query.id)
        
        # Solicita o ID do cliente
        msg = self.bot.send_message(
            callback_query.message.chat.id,
            f"🔄 RENOVAR CLIENTE\n\n"
            f"💰 Seus créditos: {credits}\n\n"
            f"Digite o ID do cliente que deseja renovar:"
        )
        
        # Registra o próximo passo
        self.bot.register_next_step_handler(msg, self.process_client_id_for_renewal)

    def process_client_id_for_renewal(self, message):
        """Processa o ID do cliente para renovação"""
        reseller_id = str(message.from_user.id)
        client_id = message.text.strip()
        
        # Verifica se o cliente existe e pertence ao revendedor
        if not self.db.is_client_of_reseller(client_id, reseller_id):
            self.bot.send_message(
                message.chat.id,
                "❌ Cliente não encontrado ou não pertence a você.\n\n"
                "Verifique o ID e tente novamente."
            )
            return
        
        # Busca informações do cliente
        client_data = self.db.get_client_data(client_id)
        name = client_data.get('name', 'Cliente')
        
        # Verifica a assinatura atual
        subscription = self.db.check_subscription(client_id)
        status = "Ativa" if subscription["active"] else "Inativa"
        days_left = subscription["days_left"] if subscription["active"] else 0
        
        # Pergunta a duração da renovação
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("30 dias", callback_data=f"renew_30_{client_id}"),
            telebot.types.InlineKeyboardButton("60 dias", callback_data=f"renew_60_{client_id}")
        )
        markup.row(telebot.types.InlineKeyboardButton("❌ Cancelar", callback_data="cancel_renewal"))
        
        self.bot.send_message(
            message.chat.id,
            f"🔄 RENOVAR CLIENTE\n\n"
            f"👤 Cliente: {name}\n"
            f"🆔 ID: {client_id}\n"
            f"📊 Status: {status}\n"
            f"⏳ Dias restantes: {days_left}\n\n"
            f"💰 Custo: 1 crédito\n\n"
            f"Escolha a duração da renovação:",
            reply_markup=markup
        )

    def confirm_renew_client(self, callback_query):
        """Confirma a renovação do cliente"""
        # Extrai os dados do callback
        parts = callback_query.data.split("_")
        days = int(parts[1])  # 30 ou 60 dias
        client_id = parts[2]
        reseller_id = str(callback_query.from_user.id)
        
        # ALTERAÇÃO: Calcular o custo correto de créditos com base nos dias
        credits_cost = 1  # Padrão para 30 dias
        if days == 60:
            credits_cost = 2  # Custo para 60 dias
        
        # Verifica novamente se tem créditos suficientes
        credits = self.db.get_reseller_credits(reseller_id)
        if credits < credits_cost:
            self.bot.answer_callback_query(
                callback_query.id,
                f"❌ Você precisa de {credits_cost} créditos para esta operação.",
                show_alert=True
            )
            return
        
        # Renova a assinatura do cliente
        success = self.db.extend_client_subscription(client_id, days)
        
        if success:
            # Deduz o número correto de créditos do revendedor
            self.db.deduct_reseller_credits(reseller_id, credits_cost)
            
            # Registra a transação
            self.db.add_reseller_transaction(reseller_id, client_id, days)
            
            # Notifica o cliente
            try:
                self.bot.send_message(
                    int(client_id),
                    f"🎉 Sua assinatura foi renovada em {days} dias pelo seu revendedor!\n\n"
                    f"✅ Obrigado por usar nosso serviço."
                )
            except:
                pass
            
            # Responde ao revendedor
            self.bot.answer_callback_query(
                callback_query.id,
                f"✅ Assinatura renovada por {days} dias com sucesso!",
                show_alert=True
            )
            
            # Atualiza a mensagem
            self.bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"✅ OPERAÇÃO CONCLUÍDA\n\n"
                    f"Você renovou o cliente {client_id} por {days} dias.\n"
                    f"Foi utilizado {credits_cost} crédito(s).\n\n"
                    f"💰 Seus créditos restantes: {credits - credits_cost}"
            )
            
        else:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Erro ao renovar cliente. Tente novamente.",
                show_alert=True
            )
            
    def cancel_renewal(self, callback_query):
        """Cancela a renovação do cliente"""
        self.bot.answer_callback_query(
            callback_query.id,
            "❌ Operação cancelada.",
            show_alert=True
        )
        
        self.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="❌ Operação cancelada."
        )

    def start_delete_client(self, callback_query):
        """Inicia o processo de exclusão de um cliente"""
        user_id = str(callback_query.from_user.id)
        
        # Verifica se é revendedor
        if not self.is_reseller(user_id):
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Você não é um revendedor autorizado.",
                show_alert=True
            )
            return
        
        # Responde ao callback
        self.bot.answer_callback_query(callback_query.id)
        
        # Solicita o ID do cliente
        msg = self.bot.send_message(
            callback_query.message.chat.id,
            f"🗑️ DELETAR CLIENTE\n\n"
            f"⚠️ Esta ação removerá o cliente e sua assinatura.\n"
            f"⚠️ Esta ação não pode ser desfeita!\n\n"
            f"Digite o ID do cliente que deseja deletar:"
        )
        
        # Registra o próximo passo
        self.bot.register_next_step_handler(msg, self.process_client_id_for_delete)

    def process_client_id_for_delete(self, message):
        """Processa o ID do cliente para exclusão"""
        reseller_id = str(message.from_user.id)
        client_id = message.text.strip()
        
        # Verifica se o cliente existe e pertence ao revendedor
        if not self.db.is_client_of_reseller(client_id, reseller_id):
            self.bot.send_message(
                message.chat.id,
                "❌ Cliente não encontrado ou não pertence a você.\n\n"
                "Verifique o ID e tente novamente."
            )
            return
        
        # Busca informações do cliente
        client_data = self.db.get_client_data(client_id)
        name = client_data.get('name', 'Cliente')
        
        # Pergunta confirmação
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("✅ Sim, deletar", callback_data=f"confirm_delete_{client_id}"),
            telebot.types.InlineKeyboardButton("❌ Cancelar", callback_data="cancel_delete")
        )
        
        self.bot.send_message(
            message.chat.id,
            f"🗑️ CONFIRMAR EXCLUSÃO\n\n"
            f"👤 Cliente: {name}\n"
            f"🆔 ID: {client_id}\n\n"
            f"⚠️ Esta ação removerá o cliente e sua assinatura.\n"
            f"⚠️ Esta ação não pode ser desfeita!\n\n"
            f"Confirma esta operação?",
            reply_markup=markup
        )

    def confirm_delete_client(self, callback_query):
        """Confirma a exclusão do cliente"""
        # Extrai o ID do cliente
        client_id = callback_query.data.split("_")[2]
        reseller_id = str(callback_query.from_user.id)
        
        # Verifica se o cliente pertence ao revendedor
        if not self.db.is_client_of_reseller(client_id, reseller_id):
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Cliente não encontrado ou não pertence a você.",
                show_alert=True
            )
            return
        
        # Processa a exclusão
        if self.db.delete_client(client_id, reseller_id):
            self.bot.answer_callback_query(
                callback_query.id,
                "✅ Cliente deletado com sucesso!",
                show_alert=True
            )
            
            # Atualiza a mensagem
            self.bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"✅ OPERAÇÃO CONCLUÍDA\n\n"
                    f"O cliente {client_id} foi removido com sucesso."
            )
        else:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Erro ao deletar cliente. Tente novamente.",
                show_alert=True
            )

    def cancel_delete_client(self, callback_query):
        """Cancela a exclusão do cliente"""
        self.bot.answer_callback_query(
            callback_query.id,
            "❌ Operação cancelada.",
            show_alert=True
        )
        
        self.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="❌ Operação cancelada."
        )

    def show_affiliate_link(self, message):
        """Mostra o link de afiliado do revendedor"""
        user_id = str(message.from_user.id)
        
        if not self.is_reseller(user_id):
            self.bot.send_message(message.chat.id, "❌ Você não é um revendedor autorizado.")
            return
        
        # Gera/obtém o link de afiliado
        affiliate_link = self.generate_affiliate_link(user_id)
        
        # Cria botão para compartilhar
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton(
                "📤 Compartilhar Link", 
                url=f"https://t.me/share/url?url={affiliate_link}&text=Assine%20o%20melhor%20bot%20da%20Claro%20Prez%C3%A3o!"
            )
        )
        
        # Envia o link
        self.bot.send_message(
            message.chat.id,
            f"🔗 SEU LINK DE AFILIADO\n\n"
            f"<code>{affiliate_link}</code>\n\n"
            f"Compartilhe este link com seus clientes para eles se cadastrarem pelo seu código.\n\n"
            f"💰 Você recebe 1 crédito para cada novo cliente que assinar via seu link.",
            parse_mode="HTML",
            reply_markup=markup
        )
    

    def show_credit_purchase(self, message):
        """Mostra as opções de compra de créditos"""
        user_id = str(message.from_user.id)
        
        if not self.is_reseller(user_id):
            self.bot.send_message(message.chat.id, "❌ Você não é um revendedor autorizado.")
            return
        
        # Obtém os planos de créditos da configuração
        markup = telebot.types.InlineKeyboardMarkup()
        
        for plan in RESELLER_CREDIT_PRICES:
            credits = plan['credits']
            price = plan['price']
            markup.row(
                telebot.types.InlineKeyboardButton(
                    f"💰 {credits} créditos - R$ {price:.2f}",
                    callback_data=f"buy_credits_{credits}"
                )
            )
        
        # Envia as opções
        self.bot.send_message(
            message.chat.id,
            f"💳 COMPRAR CRÉDITOS\n\n"
            f"Selecione o pacote de créditos desejado:\n\n"
            f"ℹ️ 1 crédito = 1 dia de assinatura para um cliente",
            reply_markup=markup
        )
    
    def process_credit_purchase(self, callback_query):
        """Processa a compra de créditos"""
        user_id = str(callback_query.from_user.id)
        
        if not self.is_reseller(user_id):
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Você não é um revendedor autorizado.",
                show_alert=True
            )
            return
        
        # Extrai os créditos selecionados
        credits = int(callback_query.data.split("_")[2])
        
        # Encontra o plano correspondente
        selected_plan = None
        for plan in RESELLER_CREDIT_PRICES:
            if plan['credits'] == credits:
                selected_plan = plan
                break
        
        if not selected_plan:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Plano inválido. Tente novamente.",
                show_alert=True
            )
            return
        
        # Gera um pagamento PIX
        price = selected_plan['price']
        phone = self.db.get_user_phone(user_id)
        
        # Notifica que está gerando o PIX
        self.bot.answer_callback_query(
            callback_query.id,
            "💳 Gerando pagamento PIX...",
            show_alert=False
        )
        
        # CORREÇÃO: Cria o pagamento com descrição clara para diferenciar de pagamentos normais
        description = f"Compra de {credits} créditos para revendedor"
        payment = self.pix.create_pix_payment(user_id, phone, price, description)
        
        if payment["success"]:
            payment_id = payment["payment_id"]
            # Registra o pagamento de créditos
            self.db.add_credit_payment(user_id, payment_id, price, credits)
            
            # Log adicional para debug
            print(f"Pagamento de créditos gerado: ID={payment_id}, Revendedor={user_id}, Créditos={credits}, Valor={price}")
            
            # Envia o QR Code
            import qrcode
            from io import BytesIO
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(payment["qr_code"])
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            bio = BytesIO()
            img.save(bio, 'PNG')
            bio.seek(0)
            
            caption = (
                f"💳 PIX para compra de créditos\n"
                f"💰 Valor: R$ {price:.2f}\n"
                f"🎯 Créditos: {credits}\n\n"
                f"📋 Código PIX:\n<code>{payment['qr_code']}</code>\n\n"
                f"✅ O pagamento será verificado automaticamente."
            )
            
            # Envia o QR Code
            self.bot.send_photo(
                callback_query.message.chat.id,
                bio,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            self.bot.send_message(
                callback_query.message.chat.id,
                f"❌ Erro ao gerar pagamento: {payment.get('error', 'Erro desconhecido')}"
            )


    def process_credit_purchase(self, callback_query):
        """Processa a compra de créditos"""
        user_id = str(callback_query.from_user.id)
        
        if not self.is_reseller(user_id):
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Você não é um revendedor autorizado.",
                show_alert=True
            )
            return
        
        # Extrai os créditos selecionados
        credits = int(callback_query.data.split("_")[2])
        
        # Encontra o plano correspondente
        selected_plan = None
        for plan in RESELLER_CREDIT_PRICES:
            if plan['credits'] == credits:
                selected_plan = plan
                break
        
        if not selected_plan:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Plano inválido. Tente novamente.",
                show_alert=True
            )
            return
        
        # Gera um pagamento PIX
        price = selected_plan['price']
        phone = self.db.get_user_phone(user_id)
        
        # Notifica que está gerando o PIX
        self.bot.answer_callback_query(
            callback_query.id,
            "💳 Gerando pagamento PIX...",
            show_alert=False
        )
        
        # Cria o pagamento
        payment = self.pix.create_pix_payment(user_id, phone, price, f"Compra de {credits} créditos")
        
        if payment["success"]:
            payment_id = payment["payment_id"]
            # Registra o pagamento de créditos
            self.db.add_credit_payment(user_id, payment_id, price, credits)
            
            # Envia o QR Code
            import qrcode
            from io import BytesIO
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(payment["qr_code"])
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            bio = BytesIO()
            img.save(bio, 'PNG')
            bio.seek(0)
            
            caption = (
                f"💳 PIX para compra de créditos\n"
                f"💰 Valor: R$ {price:.2f}\n"
                f"🎯 Créditos: {credits}\n\n"
                f"📋 Código PIX:\n<code>{payment['qr_code']}</code>\n\n"
                f"✅ O pagamento será verificado automaticamente."
            )
            
            # Envia o QR Code
            self.bot.send_photo(
                callback_query.message.chat.id,
                bio,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            self.bot.send_message(
                callback_query.message.chat.id,
                f"❌ Erro ao gerar pagamento: {payment.get('error', 'Erro desconhecido')}"
            )
            
    def show_reseller_settings(self, message):
        """Mostra as configurações do revendedor"""
        user_id = str(message.from_user.id)
        
        if not self.is_reseller(user_id):
            self.bot.send_message(message.chat.id, "❌ Você não é um revendedor autorizado.")
            return
        
        try:
            # Busca dados do revendedor
            reseller_data = self.db.get_reseller_data(user_id)
            mp_token = reseller_data.get('mercado_pago_token', 'Não configurado')
            custom_price = self.db.get_reseller_custom_price(user_id)
            
            # Garante que mp_token não seja None
            if mp_token is None:
                mp_token = 'Não configurado'
            
            # Encurta o token para exibição
            if len(mp_token) > 20 and mp_token != 'Não configurado':
                mp_token = mp_token[:10] + "..." + mp_token[-10:]
            
            # Texto para exibir o preço personalizado
            price_text = f"R$ {custom_price:.2f}" if custom_price is not None else "Não configurado (usando padrão)"
            
            # Cria menu de configurações
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "💳 Configurar Mercado Pago",
                    callback_data="config_mp"
                )
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "💰 Configurar Valor da Assinatura",
                    callback_data="config_price"
                )
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🔄 Testar Integração",
                    callback_data="test_mp"
                )
            )
            
            # Envia as configurações
            self.bot.send_message(
                message.chat.id,
                f"⚙️ CONFIGURAÇÕES DA REVENDA\n\n"
                f"💳 Token Mercado Pago: {mp_token}\n\n"
                f"💰 Valor da Assinatura: {price_text}\n\n"
                f"Selecione uma opção:",
                reply_markup=markup
            )
        except Exception as e:
            print(f"Erro nas configurações de revenda: {str(e)}")
            self.bot.send_message(
                message.chat.id,
                f"❌ Erro ao carregar configurações: {str(e)}\n\n"
                f"Por favor, tente novamente."
            ) 
    
    def start_price_config(self, callback_query):
        """Inicia a configuração do valor da assinatura"""
        self.bot.answer_callback_query(callback_query.id)
        
        # Obtém o valor atual (se existir)
        user_id = str(callback_query.from_user.id)
        current_price = self.db.get_reseller_custom_price(user_id)
        
        # Constrói a mensagem com base no valor atual
        if current_price is not None:
            price_text = f"R$ {current_price:.2f}"
            msg_text = f"💰 CONFIGURAÇÃO DO VALOR DA ASSINATURA\n\n" \
                    f"Valor atual: {price_text}\n\n" \
                    f"Digite o novo valor desejado (ex: 15.90):"
        else:
            from config import PIX_PRICE
            msg_text = f"💰 CONFIGURAÇÃO DO VALOR DA ASSINATURA\n\n" \
                    f"Valor padrão do sistema: R$ {PIX_PRICE:.2f}\n\n" \
                    f"Digite o valor desejado para seus clientes (ex: 15.90):"
        
        # Envia instruções
        msg = self.bot.send_message(
            callback_query.message.chat.id,
            msg_text
        )
        
        # Registra o próximo passo
        self.bot.register_next_step_handler(msg, self.process_price_config)

    def process_price_config(self, message):
        """Processa o valor da assinatura enviado"""
        from config import PIX_PRICE  # Importa o valor base da configuração
        
        user_id = str(message.from_user.id)
        price_text = message.text.strip().replace(',', '.')
        
        try:
            # Tenta converter para float
            price = float(price_text)
            
            # ALTERAÇÃO: Verifica se o valor é menor que o valor mínimo configurado
            if price < PIX_PRICE:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ Valor inválido. O preço não pode ser menor que R$ {PIX_PRICE:.2f} (valor configurado no sistema)."
                )
                return
            
            # Verifica se é um valor válido
            if price <= 0:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Valor inválido. Digite um número maior que zero."
                )
                return
            
            # Salva o valor personalizado
            self.db.set_reseller_custom_price(user_id, price)
            
            self.bot.send_message(
                message.chat.id,
                f"✅ Valor da assinatura configurado com sucesso!\n\n"
                f"Seus clientes pagarão R$ {price:.2f} pela assinatura."
            )
            
        except ValueError:
            self.bot.send_message(
                message.chat.id,
                f"❌ Valor inválido: {price_text}\n\n"
                f"Por favor, digite um número válido (ex: 15.90)."
            )
            
    def start_mp_config(self, callback_query):
        """Inicia a configuração do Mercado Pago"""
        self.bot.answer_callback_query(callback_query.id)
        
        # Envia instruções
        msg = self.bot.send_message(
            callback_query.message.chat.id,
            "💳 CONFIGURAÇÃO DO MERCADO PAGO\n\n"
            "Para receber pagamentos diretamente, você precisa cadastrar sua chave de acesso do Mercado Pago.\n\n"
            "1. Acesse mercadopago.com.br e faça login\n"
            "2. Vá para Seu negócio > Desenvolvedor > Credenciais de produção\n"
            "3. Copie o 'Access token' (token de acesso)\n\n"
            "Cole o token de acesso abaixo:"
        )
        
        # Registra o próximo passo
        self.bot.register_next_step_handler(msg, self.process_mp_token)
    
    def process_mp_token(self, message):
        """Processa o token do Mercado Pago enviado"""
        user_id = str(message.from_user.id)
        token = message.text.strip()
        
        # Tenta validar o token com uma operação simples
        import mercadopago
        try:
            # Cria instância temporária
            mp = mercadopago.SDK(token)
            # Tenta uma operação simples para validar
            result = mp.payment().get(1)
            
            # Se não der erro, salva o token
            self.db.set_reseller_mp_token(user_id, token)
            
            # Apaga a mensagem com o token por segurança
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            self.bot.send_message(
                message.chat.id,
                "✅ Token do Mercado Pago configurado com sucesso!\n\n"
                "Agora você receberá os pagamentos diretamente em sua conta do Mercado Pago."
            )
            
        except Exception as e:
            self.bot.send_message(
                message.chat.id,
                f"❌ Erro ao configurar token: {str(e)}\n\n"
                f"Verifique se o token está correto e tente novamente."
            )
    
    def test_mp_integration(self, callback_query):
        """Testa a integração com o Mercado Pago"""
        user_id = str(callback_query.from_user.id)
        
        # Busca o token
        reseller_data = self.db.get_reseller_data(user_id)
        mp_token = reseller_data.get('mercado_pago_token')
        
        if not mp_token:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Token do Mercado Pago não configurado. Configure primeiro.",
                show_alert=True
            )
            return
        
        # Testa o token
        import mercadopago
        try:
            # Cria instância temporária
            mp = mercadopago.SDK(mp_token)
            # Tenta uma operação simples para validar
            result = mp.payment().get(1)
            
            self.bot.answer_callback_query(
                callback_query.id,
                "✅ Integração com Mercado Pago funcionando corretamente!",
                show_alert=True
            )
            
        except Exception as e:
            self.bot.answer_callback_query(
                callback_query.id,
                f"❌ Erro na integração: {str(e)}. Verifique seu token.",
                show_alert=True
            )

    
    def show_reseller_stats(self, message):
        """Mostra estatísticas do revendedor"""
        user_id = str(message.from_user.id)
        
        if not self.is_reseller(user_id):
            self.bot.send_message(message.chat.id, "❌ Você não é um revendedor autorizado.")
            return
        
        # Busca estatísticas
        stats = self.db.get_reseller_stats(user_id)
        
        # Busca créditos diretamente para mostrar nas estatísticas
        credits = self.db.get_reseller_credits(user_id)
        
        # Calcula valores
        total_clients = stats.get('total_clients', 0)
        active_clients = stats.get('active_clients', 0)
        inactive_clients = total_clients - active_clients - stats.get('trial_clients', 0)  # Corrigido para excluir clientes em teste
        trial_clients = stats.get('trial_clients', 0)  # Novo campo para clientes em teste
        
        # Formata a mensagem incluindo clientes em teste
        self.bot.send_message(
            message.chat.id,
            f"📊 ESTATÍSTICAS DA REVENDA\n\n"
            f"💰 Seus créditos: {credits}\n"
            f"👥 Total de clientes: {total_clients}\n"
            f"✅ Clientes ativos: {active_clients}\n"
            f"❌ Clientes inativos: {inactive_clients}\n"
            f"🎁 Clientes em teste: {trial_clients}\n\n"  # Nova linha mostrando clientes em teste
            f"🔄 Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        ) 
  
    
    def navigate_clients(self, callback_query, direction):
        """Navega pela lista de clientes"""
        user_id = str(callback_query.from_user.id)
        view = self.active_clients_views.get(user_id)
        
        if not view:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Erro ao navegar. Inicie a visualização novamente.",
                show_alert=True
            )
            return
        
        # Atualiza a página
        if direction == "next" and view['page'] < view['total_pages']:
            view['page'] += 1
        elif direction == "prev" and view['page'] > 1:
            view['page'] -= 1
        
        # Responde ao callback
        self.bot.answer_callback_query(callback_query.id)
        
        # Atualiza a mensagem
        try:
            self.bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text="Carregando...",
                reply_markup=None
            )
        except:
            pass
        
        # Mostra a nova página
        self._show_clients_page(callback_query.message.chat.id, user_id)
    

    def show_clients_list(self, message):
        """Mostra a lista de clientes do revendedor"""
        user_id = str(message.from_user.id)
        print(f"[LOG] show_clients_list: user_id={user_id}")
        if not self.is_reseller(user_id):
            self.bot.send_message(message.chat.id, "❌ Você não é um revendedor autorizado.")
            return
        
        # Busca clientes do revendedor
        clients = self.db.get_reseller_clients(user_id)
        print(f"[LOG] Clientes encontrados: {clients}")
        
        if not clients:
            self.bot.send_message(
                message.chat.id,
                "👥 MEUS CLIENTES\n\n"
                "Você ainda não tem clientes cadastrados.\n\n"
                "Compartilhe seu link de afiliado para conseguir clientes."
            )
            return
        
        # Cria paginação para a lista
        page = 1
        per_page = 5
        total_pages = (len(clients) + per_page - 1) // per_page
        
        # Salva a visualização atual
        self.active_clients_views[user_id] = {
            'clients': clients,
            'page': page,
            'total_pages': total_pages
        }
        
        # Mostra a primeira página
        self._show_clients_page(message.chat.id, user_id)


    def start_add_days(self, callback_query):
        """Inicia o processo de adicionar dias a um cliente"""
        user_id = str(callback_query.from_user.id)
        
        # Verifica se é revendedor
        if not self.is_reseller(user_id):
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Você não é um revendedor autorizado.",
                show_alert=True
            )
            return
        
        # Verifica se tem créditos suficientes
        credits = self.db.get_reseller_credits(user_id)
        
        if credits < RESELLER_MIN_CREDITS:
            self.bot.answer_callback_query(
                callback_query.id,
                f"❌ Você precisa de pelo menos {RESELLER_MIN_CREDITS} créditos. Atualmente tem {credits}.",
                show_alert=True
            )
            return
        
        # Responde ao callback
        self.bot.answer_callback_query(callback_query.id)
        
        # Solicita o ID do cliente
        msg = self.bot.send_message(
            callback_query.message.chat.id,
            f"➕ ADICIONAR DIAS A CLIENTE\n\n"
            f"💰 Seus créditos: {credits}\n\n"
            f"Digite o ID do cliente que deseja adicionar dias:"
        )
        
        # Registra o próximo passo
        self.bot.register_next_step_handler(msg, self.process_client_id_for_days)
    
    def process_client_id_for_days(self, message):
        """Processa o ID do cliente para adicionar dias"""
        reseller_id = str(message.from_user.id)
        client_id = message.text.strip()
        
        # Verifica se o cliente existe e pertence ao revendedor
        if not self.db.is_client_of_reseller(client_id, reseller_id):
            self.bot.send_message(
                message.chat.id,
                "❌ Cliente não encontrado ou não pertence a você.\n\n"
                "Verifique o ID e tente novamente."
            )
            return
        
        # Busca informações do cliente
        client_data = self.db.get_client_data(client_id)
        name = client_data.get('name', 'Cliente')
        
        # Verifica a assinatura atual
        subscription = self.db.check_subscription(client_id)
        status = "Ativa" if subscription["active"] else "Inativa"
        days_left = subscription["days_left"] if subscription["active"] else 0
        
        # Pergunta quantos dias quer adicionar
        credits = self.db.get_reseller_credits(reseller_id)
        
        msg = self.bot.send_message(
            message.chat.id,
            f"➕ ADICIONAR DIAS\n\n"
            f"👤 Cliente: {name}\n"
            f"🆔 ID: {client_id}\n"
            f"📊 Status: {status}\n"
            f"⏳ Dias restantes: {days_left}\n\n"
            f"💰 Seus créditos: {credits}\n\n"
            f"Digite a quantidade de dias que deseja adicionar (máximo {credits}):"
        )
        
        # Guarda o ID do cliente para o próximo passo
        self.bot.register_next_step_handler(msg, self.process_days_amount, client_id)
    
    def process_days_amount(self, message, client_id):
        """Processa a quantidade de dias a adicionar"""
        reseller_id = str(message.from_user.id)
        
        try:
            days = int(message.text.strip())
            if days <= 0:
                raise ValueError("Dias deve ser maior que zero")
            
            # Verifica se tem créditos suficientes
            credits = self.db.get_reseller_credits(reseller_id)
            if days > credits:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ Você não tem créditos suficientes.\n\n"
                    f"💰 Seus créditos: {credits}\n"
                    f"🔢 Dias solicitados: {days}\n\n"
                    f"Por favor, digite um valor menor ou compre mais créditos."
                )
                return
            
            # Confirma a operação
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm_days_{client_id}_{days}"),
                telebot.types.InlineKeyboardButton("❌ Cancelar", callback_data="cancel_days")
            )
            
            self.bot.send_message(
                message.chat.id,
                f"🔄 CONFIRMAR ADIÇÃO DE DIAS\n\n"
                f"👤 Cliente: {client_id}\n"
                f"📅 Dias a adicionar: {days}\n"
                f"💰 Créditos a usar: {days}\n\n"
                f"Confirma esta operação?",
                reply_markup=markup
            )
            
        except (ValueError, TypeError):
            self.bot.send_message(
                message.chat.id,
                "❌ Por favor, digite um número válido maior que zero."
            )
    
    def confirm_add_days(self, callback_query):
        """Confirma a adição de dias ao cliente"""
        # Extrai dados do callback
        _, client_id, days = callback_query.data.split("_")[1:]
        days = int(days)
        reseller_id = str(callback_query.from_user.id)
        
        # Verifica novamente se tem créditos suficientes
        credits = self.db.get_reseller_credits(reseller_id)
        if days > credits:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Você não tem créditos suficientes para esta operação.",
                show_alert=True
            )
            return
        
        # Adiciona os dias à assinatura do cliente
        success = self.db.extend_client_subscription(client_id, days)
        
        if success:
            # Deduz os créditos do revendedor
            self.db.deduct_reseller_credits(reseller_id, days)
            
            # Registra a transação
            self.db.add_reseller_transaction(reseller_id, client_id, days)
            
            # Notifica o cliente
            try:
                self.bot.send_message(
                    int(client_id),
                    f"🎉 Sua assinatura foi estendida em {days} dias pelo seu revendedor!\n\n"
                    f"✅ Obrigado por usar nosso serviço."
                )
            except:
                pass
            
            # Responde ao revendedor
            self.bot.answer_callback_query(
                callback_query.id,
                f"✅ {days} dias adicionados com sucesso ao cliente!",
                show_alert=True
            )
            
            # Atualiza a mensagem
            self.bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"✅ OPERAÇÃO CONCLUÍDA\n\n"
                     f"Você adicionou {days} dias ao cliente {client_id}.\n"
                     f"Foram utilizados {days} créditos.\n\n"
                     f"💰 Seus créditos restantes: {credits - days}"
            )
            
        else:
            self.bot.answer_callback_query(
                callback_query.id,
                "❌ Erro ao adicionar dias. Tente novamente.",
                show_alert=True
            )
    
    def cancel_add_days(self, callback_query):
        """Cancela a adição de dias"""
        self.bot.answer_callback_query(
            callback_query.id,
            "❌ Operação cancelada.",
            show_alert=True
        )
        
        self.bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="❌ Operação cancelada."
        )
    
    def handle_affiliate_start(self, message, affiliate_code):
        """Processa o início via link de afiliado"""
        print(f"[LOG] handle_affiliate_start: user_id={message.from_user.id}, affiliate_code={affiliate_code}")
        self.bot.send_message(
            message.chat.id,
            "🔗 Você está entrando através de um link de revenda! Ao finalizar o cadastro, será associado ao revendedor e ele poderá te dar suporte exclusivo."
        )
        reseller_id = self.db.get_reseller_by_affiliate(affiliate_code)
        print(f"[LOG] reseller_id encontrado: {reseller_id}")
        if not reseller_id:
            print("[LOG] Código de afiliado inválido")
            self.bot.send_message(
                message.chat.id,
                "⚠️ Código de afiliado inválido ou expirado. Por favor, obtenha um link válido com um revendedor autorizado."
            )
            return False  # Retorna False para indicar que não é um link válido
        
        if not self.db.can_accept_new_client(reseller_id):
            print(f"[LOG] Revendedor {reseller_id} não pode aceitar novos clientes")
            self.bot.send_message(
                message.chat.id,
                "⚠️ Este revendedor atingiu o limite de clientes e não pode aceitar novos registros no momento.\n\nPor favor, entre em contato com outro revendedor ou tente novamente mais tarde."
            )
            return False  # Revendedor sem créditos suficientes
        
        user_id = str(message.from_user.id)
        
        if self.db.is_user_registered(user_id):
            print(f"[LOG] Usuário {user_id} já registrado")
            current_reseller = self.db.get_client_reseller(user_id)
            print(f"[LOG] current_reseller: {current_reseller}")
            if current_reseller:
                if current_reseller == reseller_id:
                    self.bot.send_message(
                        message.chat.id,
                        "✅ Você já está associado a este revendedor."
                    )
                else:
                    self.bot.send_message(
                        message.chat.id,
                        "ℹ️ Você já está associado a outro revendedor."
                    )
                return True
            else:
                if self.db.associate_client_to_reseller(user_id, reseller_id):
                    print(f"[LOG] Associação feita: {user_id} -> {reseller_id}")
                    self.db.increment_reseller_trial(reseller_id)  # Incrementa teste
                    self.bot.send_message(
                        message.chat.id,
                        "✅ Você foi associado ao revendedor com sucesso!"
                    )
                else:
                    print(f"[LOG] Falha ao associar {user_id} -> {reseller_id}")
                    self.bot.send_message(
                        message.chat.id,
                        "❌ Houve um erro ao associar você ao revendedor. Tente novamente mais tarde."
                    )
                return True
        else:
            print(f"[LOG] Salvando associação pendente: {user_id} -> {reseller_id}")
            self.db.save_pending_association(user_id, reseller_id)
            self.bot.send_message(
                message.chat.id,
                "✅ Código de afiliado válido! Você será associado ao revendedor após completar o cadastro."
            )
            return True