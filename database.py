import json
import os
import sqlite3
from datetime import datetime, timedelta
from config import DB_FILE, USERS_FILE, STATS_FILE, SUBSCRIPTION_DAYS, TRIAL_DAYS

class Database:
    def __init__(self):
        self.db_file = DB_FILE
        self.users_file = USERS_FILE
        self.stats_file = STATS_FILE
        self._initialize_database()
        self._initialize_files()
        self._ensure_suspenso_column()

    def _initialize_database(self):
        """Inicializa o banco de dados SQLite"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Cria tabela de usuários se não existir
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                phone_number TEXT,
                operator TEXT DEFAULT 'claro',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                auto_collect_enabled INTEGER DEFAULT 0,
                subscription_end TIMESTAMP,
                is_trial_used INTEGER DEFAULT 0,
                suspenso INTEGER DEFAULT 0
            )
        ''')
        
        # Verifica se a tabela de pagamentos já existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payments'")
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            # Verifica se as colunas necessárias existem na tabela payments
            cursor.execute("PRAGMA table_info(payments)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Se a coluna 'processed' não existir, adiciona-a
            if 'processed' not in columns:
                print("Adicionando coluna 'processed' à tabela payments...")
                cursor.execute('''
                    ALTER TABLE payments
                    ADD COLUMN processed INTEGER DEFAULT 0
                ''')
            
            # CORREÇÃO: Adicionar coluna para rastrear qual token foi usado
            if 'custom_token_used' not in columns:
                print("Adicionando coluna 'custom_token_used' à tabela payments...")
                cursor.execute('''
                    ALTER TABLE payments
                    ADD COLUMN custom_token_used INTEGER DEFAULT 0
                ''')
                
            # CORREÇÃO: Adicionar coluna para armazenar o ID do revendedor
            if 'reseller_id' not in columns:
                print("Adicionando coluna 'reseller_id' à tabela payments...")
                cursor.execute('''
                    ALTER TABLE payments
                    ADD COLUMN reseller_id TEXT DEFAULT NULL
                ''')
        else:
            # Cria a tabela payments com as novas colunas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    payment_id TEXT UNIQUE NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    processed INTEGER DEFAULT 0,
                    custom_token_used INTEGER DEFAULT 0,
                    reseller_id TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
        
        # O resto do código permanece igual
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS linking_history (
                user_id TEXT PRIMARY KEY,
                last_link TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                stat_name TEXT PRIMARY KEY,
                stat_value INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS button_clicks (
                user_id TEXT NOT NULL,
                button_type TEXT NOT NULL,
                last_click TIMESTAMP,
                PRIMARY KEY (user_id, button_type)
            )
        ''')
        
        # Inicializa estatísticas padrão se não existirem
        cursor.execute('''
            INSERT OR IGNORE INTO statistics (stat_name, stat_value)
            VALUES 
                ('total_users', 0),
                ('active_today', 0),
                ('campaigns_completed', 0)
        ''')
        
        # CORREÇÃO: Inicializa as tabelas de revendedores usando a conexão existente
        self._initialize_reseller_tables(conn, cursor)
        
        conn.commit()
        conn.close()

        
    def _initialize_reseller_tables(self, conn=None, cursor=None):
        """Inicializa as tabelas relacionadas ao sistema de revenda"""
        # Se não foram fornecidos conexão e cursor, criar novos
        close_conn = False
        if conn is None or cursor is None:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            close_conn = True
        
        # Tabela de revendedores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resellers (
                user_id TEXT PRIMARY KEY,
                credits INTEGER DEFAULT 0,
                mercado_pago_token TEXT,
                affiliate_code TEXT,
                custom_price REAL DEFAULT NULL,
                created_at TIMESTAMP,
                last_activity TIMESTAMP
            )
        ''')
                
        # Tabela de relação revendedor-cliente
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reseller_clients (
                client_id TEXT,
                reseller_id TEXT,
                association_date TIMESTAMP,
                PRIMARY KEY (client_id),
                FOREIGN KEY (client_id) REFERENCES users (user_id),
                FOREIGN KEY (reseller_id) REFERENCES resellers (user_id)
            )
        ''')
        
        # Tabela de transações de revendedores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reseller_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reseller_id TEXT,
                client_id TEXT,
                days INTEGER,
                transaction_date TIMESTAMP,
                FOREIGN KEY (reseller_id) REFERENCES resellers (user_id),
                FOREIGN KEY (client_id) REFERENCES users (user_id)
            )
        ''')
        
        # Tabela de pagamentos de créditos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reseller_credit_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reseller_id TEXT,
                payment_id TEXT UNIQUE,
                amount REAL,
                credits INTEGER,
                status TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY (reseller_id) REFERENCES resellers (user_id)
            )
        ''')
        
        # Tabela de associações pendentes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_associations (
                client_id TEXT PRIMARY KEY,
                reseller_id TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY (reseller_id) REFERENCES resellers (user_id)
            )
        ''')
        
        # Tabela para contar testes de revendedores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reseller_trials (
                reseller_id TEXT PRIMARY KEY,
                trial_count INTEGER DEFAULT 0
            )
        ''')
        
        # Apenas commit e fecha a conexão se foi criada neste método
        if close_conn:
            conn.commit()
            conn.close()

    def _initialize_files(self):
        files = {
            self.users_file: {},
            self.stats_file: {'total_users': 0, 'active_today': 0, 'campaigns_completed': 0}
        }
        for file, default_data in files.items():
            if not os.path.exists(file):
                with open(file, 'w') as f:
                    json.dump(default_data, f, indent=4)

    def load_users(self):
        with open(self.users_file, 'r') as f:
            return json.load(f)

    def save_users(self, users):
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=4)

    def set_trial(self, user_id, trial_end):
        """Define período de teste"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET subscription_end = ?, is_trial_used = 1
            WHERE user_id = ?
        ''', (trial_end.isoformat(), user_id))
        
        conn.commit()
        conn.close()
      
    def set_phone_change_enabled(self, enabled):
        """Define se a troca de número está habilitada"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Verifica se o registro já existe
        cursor.execute('SELECT 1 FROM statistics WHERE stat_name = "phone_change_enabled"')
        exists = cursor.fetchone() is not None
        
        if exists:
            cursor.execute('''
                UPDATE statistics 
                SET stat_value = ?
                WHERE stat_name = "phone_change_enabled"
            ''', (1 if enabled else 0,))
        else:
            cursor.execute('''
                INSERT INTO statistics (stat_name, stat_value)
                VALUES ("phone_change_enabled", ?)
            ''', (1 if enabled else 0,))
        
        conn.commit()
        conn.close()
    
    def is_phone_change_enabled(self):
        """Verifica se a troca de número está habilitada"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT stat_value FROM statistics WHERE stat_name = "phone_change_enabled"')
        result = cursor.fetchone()
        
        conn.close()
        
        # Se não existir registro, assume que está habilitado por padrão
        if result is None:
            return True
        
        return bool(result[0])
    
      
    def check_subscription(self, user_id):
        """Verifica se usuário tem assinatura ativa e não está suspenso"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT subscription_end, is_trial_used, suspenso 
            FROM users 
            WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        if not result or not result[0]:
            return {"active": False, "is_trial": False, "days_left": 0, "suspenso": bool(result[2]) if result else False}
        end_date = datetime.fromisoformat(result[0])
        is_trial = bool(result[1]) and end_date > datetime.now()
        suspenso = bool(result[2])
        if suspenso:
            return {"active": False, "is_trial": is_trial, "days_left": 0, "suspenso": True}
        if end_date > datetime.now():
            days_left = (end_date - datetime.now()).days
            return {"active": True, "is_trial": is_trial, "days_left": days_left, "suspenso": False}
        else:
            return {"active": False, "is_trial": False, "days_left": 0, "suspenso": False}


    def save_payment_token(self, payment_id, token):
        """Salva o token usado para gerar um pagamento para usar na verificação"""
        if not payment_id or not token:
            print(f"❌ Erro: payment_id ou token inválidos")
            return False
            
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        try:
            # Verifica se a tabela existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_tokens'")
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Cria a tabela se não existir
                cursor.execute('''
                    CREATE TABLE payment_tokens (
                        payment_id TEXT PRIMARY KEY,
                        token TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("Tabela payment_tokens criada")
            
            # Insere ou atualiza o token
            cursor.execute('''
                INSERT OR REPLACE INTO payment_tokens (payment_id, token, created_at)
                VALUES (?, ?, ?)
            ''', (payment_id, token, datetime.now().isoformat()))
            
            # Verifica se a inserção foi bem-sucedida
            cursor.execute('SELECT token FROM payment_tokens WHERE payment_id = ?', (payment_id,))
            stored_token = cursor.fetchone()
            
            conn.commit()
            
            if stored_token and stored_token[0] == token:
                print(f"✓ Token verificado e salvo corretamente para pagamento {payment_id}")
                return True
            else:
                print(f"⚠️ Verificação falhou: Token não foi salvo corretamente")
                return False
                
        except Exception as e:
            print(f"Erro ao salvar token de pagamento: {str(e)}")
            try:
                # Log mais detalhado para debugging
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
            except:
                pass
            return False
        finally:
            conn.close()
            
    def get_payment_token(self, payment_id):
        """Recupera o token usado para gerar um pagamento"""
        if not payment_id:
            print(f"❌ Erro: payment_id inválido")
            return None
            
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        try:
            # Verifica se a tabela existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_tokens'")
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                print("Tabela payment_tokens não existe")
                return None
            
            # Busca o token
            cursor.execute('SELECT token FROM payment_tokens WHERE payment_id = ?', (payment_id,))
            result = cursor.fetchone()
            
            if result:
                token = result[0]
                print(f"Token encontrado para pagamento {payment_id}: {token[:10]}...{token[-5:] if len(token) > 15 else token}")
                return token
            else:
                print(f"Token não encontrado para pagamento {payment_id}")
                
                # Log adicional para debugging
                cursor.execute('SELECT payment_id, created_at FROM payment_tokens ORDER BY created_at DESC LIMIT 5')
                recent = cursor.fetchall()
                if recent:
                    print("Tokens recentes encontrados:")
                    for pid, date in recent:
                        print(f"  - Payment ID: {pid}, Data: {date}")
                else:
                    print("Nenhum token encontrado na tabela")
                    
                return None
                
        except Exception as e:
            print(f"Erro ao buscar token de pagamento: {str(e)}")
            try:
                # Log mais detalhado para debugging
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
            except:
                pass
            return None
        finally:
            conn.close()



    def get_payment_info(self, payment_id):
        """Obtém informações completas sobre um pagamento"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, custom_token_used, reseller_id, status, processed 
            FROM payments 
            WHERE payment_id = ?
        ''', (payment_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
            
        return {
            'user_id': result[0],
            'custom_token_used': bool(result[1]),
            'reseller_id': result[2],
            'status': result[3],
            'processed': bool(result[4])
        }

    def add_payment(self, user_id, payment_id, amount, custom_token_used=False, reseller_id=None):
        """Adiciona registro de pagamento com informações estendidas"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # CORREÇÃO: Armazenar também se o token personalizado foi usado e o ID do revendedor
        cursor.execute('''
            INSERT INTO payments (user_id, payment_id, amount, status, processed, custom_token_used, reseller_id)
            VALUES (?, ?, ?, 'pending', 0, ?, ?)
        ''', (user_id, payment_id, amount, 1 if custom_token_used else 0, reseller_id))
        
        conn.commit()
        conn.close()
        
        
    def update_payment_status(self, payment_id, status):
        """Atualiza status do pagamento"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE payments 
            SET status = ?
            WHERE payment_id = ?
        ''', (status, payment_id))
        
        conn.commit()
        conn.close()
    
    def extend_subscription(self, user_id, days=SUBSCRIPTION_DAYS):
        """Estende assinatura"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Busca data atual
        cursor.execute('SELECT subscription_end FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            current_end = datetime.fromisoformat(result[0])
            if current_end > datetime.now():
                new_end = current_end + timedelta(days=days)
            else:
                new_end = datetime.now() + timedelta(days=days)
        else:
            new_end = datetime.now() + timedelta(days=days)
        
        cursor.execute('''
            UPDATE users 
            SET subscription_end = ?
            WHERE user_id = ?
        ''', (new_end.isoformat(), user_id))
        
        conn.commit()
        conn.close()
    

    def can_accept_new_client(self, reseller_id):
        """Verifica se um revendedor pode aceitar novos clientes"""
        # Modificação: Para novos clientes, sempre permitir se o revendedor tiver pelo menos 1 crédito
        credits = self.get_reseller_credits(reseller_id)
        return credits >= 1

        
    def delete_client(self, client_id, reseller_id):
        """Exclui um cliente específico de um revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        try:
            # Verifica se o cliente pertence ao revendedor
            cursor.execute('''
                SELECT 1 FROM reseller_clients
                WHERE client_id = ? AND reseller_id = ?
            ''', (client_id, reseller_id))
            
            if not cursor.fetchone():
                conn.close()
                return False
            
            # Remove a associação com o revendedor
            cursor.execute('''
                DELETE FROM reseller_clients
                WHERE client_id = ?
            ''', (client_id,))
            
            # Cancela a assinatura do cliente
            cursor.execute('''
                UPDATE users
                SET subscription_end = NULL
                WHERE user_id = ?
            ''', (client_id,))
            
            # Registra a ação no log de transações
            cursor.execute('''
                INSERT INTO reseller_transactions
                (reseller_id, client_id, days, transaction_date)
                VALUES (?, ?, ?, ?)
            ''', (reseller_id, client_id, -1, datetime.now().isoformat()))  # Usamos -1 para indicar remoção
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Erro ao deletar cliente: {str(e)}")
            conn.close()
            return False



    def get_payment_history(self, user_id, limit=5):
        """Busca histórico de pagamentos"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT payment_id, amount, status, created_at 
            FROM payments 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return [{"payment_id": r[0], "amount": r[1], "status": r[2], "date": r[3]} for r in results]

    def save_user_phone(self, user_id, phone_number):
        """Atualiza apenas o número de telefone do usuário, preservando a operadora e outros campos"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET phone_number = ?, last_login = ? WHERE user_id = ?
        ''', (phone_number, datetime.now().isoformat(), user_id))
        
        # Se o usuário não existe ainda, cria com operador padrão 'claro'
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO users (user_id, phone_number, operator, last_login)
                VALUES (?, ?, ?, ?)
            ''', (user_id, phone_number, 'claro', datetime.now().isoformat()))
        
        conn.commit()
        conn.close()

    def save_user_operator(self, user_id, operator):
        """Atualiza apenas a operadora do usuário, preservando os outros campos"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET operator = ?, last_login = ? WHERE user_id = ?
        ''', (operator, datetime.now().isoformat(), user_id))
        
        # Se o usuário não existe ainda, cria com operador informado
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO users (user_id, operator, last_login)
                VALUES (?, ?, ?)
            ''', (user_id, operator, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()

    def get_user_operator(self, user_id):
        """Busca a operadora do usuário no banco SQLite"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT operator FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else 'claro'  # Retorna 'claro' como padrão

    def get_user_phone(self, user_id):
        """Busca o número de telefone do usuário no banco SQLite"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT phone_number FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else None

    def update_last_login(self, user_id):
        """Atualiza o último login do usuário"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET last_login = ?
            WHERE user_id = ?
        ''', (datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()

    def set_auto_collect(self, user_id, enabled):
        """Atualiza o status da coleta automática para um usuário"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET auto_collect_enabled = ?
            WHERE user_id = ?
        ''', (1 if enabled else 0, user_id))
        
        conn.commit()
        conn.close()

    def get_auto_collect_status(self, user_id):
        """Busca o status da coleta automática do usuário"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT auto_collect_enabled FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return bool(result[0]) if result else False

    def can_link_account(self, user_id):
        """Verifica se o usuário pode vincular conta (limite de 1 vez por dia)"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT last_link FROM linking_history WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            last_link = datetime.fromisoformat(result[0])
            if datetime.now() - last_link < timedelta(days=1):
                conn.close()
                return False
        
        # Atualiza ou insere novo registro
        cursor.execute('''
            INSERT OR REPLACE INTO linking_history (user_id, last_link)
            VALUES (?, ?)
        ''', (user_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        return True


    def set_reseller_custom_price(self, user_id, price):
        """Define o valor personalizado da assinatura para um revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE resellers
            SET custom_price = ?, last_activity = ?
            WHERE user_id = ?
        ''', (price, datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()
        
        return True

    def get_reseller_custom_price(self, user_id):
        """Obtém o valor personalizado da assinatura de um revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT custom_price FROM resellers WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        # Se não estiver definido, retorna None
        return result[0] if result and result[0] is not None else None

    def has_resellers(self):
        """Verifica se existem revendedores cadastrados no sistema"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM resellers')
        count = cursor.fetchone()[0]
        
        conn.close()
        return count > 0

    def update_stats(self, stat_type, value=1):
        """Atualiza estatísticas no arquivo JSON (mantém compatibilidade)"""
        with open(self.stats_file, 'r') as f:
            stats = json.load(f)
        
        if stat_type in stats:
            stats[stat_type] += value
        
        with open(self.stats_file, 'w') as f:
            json.dump(stats, f, indent=4)
        
        # Também atualiza no banco SQLite
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE statistics 
            SET stat_value = stat_value + ?
            WHERE stat_name = ?
        ''', (value, stat_type))
        
        conn.commit()
        conn.close()

    def get_all_users_with_auto_collect(self):
        """Retorna todos os usuários com coleta automática ativada"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT u.user_id 
            FROM users u
            WHERE u.auto_collect_enabled = 1
        ''')
        
        result = cursor.fetchall()
        conn.close()
        
        return [row[0] for row in result]

    def create_backup(self):
        """Cria backup de todos os dados"""
        backup = {
            'users': self.load_users(),
            'stats': json.load(open(self.stats_file))
        }
        
        # Adiciona dados do SQLite ao backup
        conn = sqlite3.connect(self.db_file)
        
        # Backup da tabela users
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users')
        sqlite_users = cursor.fetchall()
        
        # Backup das estatísticas
        cursor.execute('SELECT * FROM statistics')
        sqlite_stats = cursor.fetchall()
        
        # Backup do histórico de vinculações
        cursor.execute('SELECT * FROM linking_history')
        linking_history = cursor.fetchall()
        
        # Backup dos pagamentos
        cursor.execute('SELECT * FROM payments')
        payments = cursor.fetchall()
        
        conn.close()
        
        backup['sqlite_data'] = {
            'users': sqlite_users,
            'statistics': sqlite_stats,
            'linking_history': linking_history,
            'payments': payments
        }
        
        backup_file = f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(backup_file, 'w') as f:
            json.dump(backup, f, indent=4)
        return backup_file

    def restore_backup(self, backup_file):
        """Restaura backup de dados"""
        try:
            with open(backup_file, 'r') as f:
                backup = json.load(f)
            
            # Restaura arquivos JSON
            self.save_users(backup['users'])
            with open(self.stats_file, 'w') as f:
                json.dump(backup['stats'], f, indent=4)
            
            # Restaura dados do SQLite se existirem
            if 'sqlite_data' in backup:
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()
                
                # Limpa tabelas existentes
                cursor.execute('DELETE FROM users')
                cursor.execute('DELETE FROM statistics')
                cursor.execute('DELETE FROM linking_history')
                cursor.execute('DELETE FROM payments')
                
                # Restaura tabela users
                for user_data in backup['sqlite_data']['users']:
                    cursor.execute('''
                        INSERT INTO users (user_id, phone_number, created_at, last_login, auto_collect_enabled, subscription_end, is_trial_used)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', user_data)
                
                # Restaura estatísticas
                for stat_data in backup['sqlite_data']['statistics']:
                    cursor.execute('''
                        INSERT INTO statistics (stat_name, stat_value)
                        VALUES (?, ?)
                    ''', stat_data)
                
                # Restaura histórico de vinculações
                for link_data in backup['sqlite_data']['linking_history']:
                    cursor.execute('''
                        INSERT INTO linking_history (user_id, last_link)
                        VALUES (?, ?)
                    ''', link_data)
                
                # Restaura pagamentos se existirem
                if 'payments' in backup['sqlite_data']:
                    for payment_data in backup['sqlite_data']['payments']:
                        cursor.execute('''
                            INSERT INTO payments (id, user_id, payment_id, amount, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', payment_data)
                
                conn.commit()
                conn.close()
            
            return True
        except Exception as e:
            print(f"Erro ao restaurar backup: {str(e)}")
            return False

    def get_user_by_payment(self, payment_id):
        """Busca usuário pelo ID do pagamento"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id 
            FROM payments 
            WHERE payment_id = ?
        ''', (payment_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def check_button_cooldown(self, user_id, button_type):
        """Verifica se o botão está em cooldown (proteção anti-autoclick)"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT last_click 
            FROM button_clicks 
            WHERE user_id = ? AND button_type = ?
        ''', (user_id, button_type))
        
        result = cursor.fetchone()
        
        # Se não há registro anterior, permite o clique
        if not result:
            cursor.execute('''
                INSERT INTO button_clicks (user_id, button_type, last_click)
                VALUES (?, ?, ?)
            ''', (user_id, button_type, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return False
        
        # Verifica o tempo desde o último clique
        last_click = datetime.fromisoformat(result[0])
        time_diff = (datetime.now() - last_click).total_seconds()
        
        # Atualiza o timestamp do clique
        cursor.execute('''
            UPDATE button_clicks 
            SET last_click = ?
            WHERE user_id = ? AND button_type = ?
        ''', (datetime.now().isoformat(), user_id, button_type))
        
        conn.commit()
        conn.close()
        
        # Retorna True se estiver em cooldown (não deve processar o clique)
        from config import BUTTON_COOLDOWN
        return time_diff < BUTTON_COOLDOWN


    def mark_payment_as_processed(self, payment_id):
        """Marca um pagamento como processado para evitar processamento duplicado"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE payments 
            SET processed = 1
            WHERE payment_id = ?
        ''', (payment_id,))
        
        conn.commit()
        conn.close()

    def is_payment_processed(self, payment_id):
        """Verifica se um pagamento já foi processado"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT processed
            FROM payments 
            WHERE payment_id = ?
        ''', (payment_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result and result[0] == 1
        
    def get_pending_payments(self):
        """Retorna pagamentos pendentes não processados nas últimas 24 horas"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
        
        cursor.execute('''
            SELECT payment_id, user_id, amount
            FROM payments 
            WHERE status = 'pending' 
            AND processed = 0
            AND created_at > ?
        ''', (one_day_ago,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results

    def cleanup_old_data(self):
        """Remove dados antigos para manter o banco limpo"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Remove usuários que não fizeram login há mais de 30 dias
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute('''
            DELETE FROM users 
            WHERE last_login < ? OR last_login IS NULL
        ''', (thirty_days_ago,))
        
        # Remove histórico de vinculações antigo
        cursor.execute('''
            DELETE FROM linking_history 
            WHERE last_link < ?
        ''', (thirty_days_ago,))
        
        # Remove cliques antigos (proteção anti-autoclick)
        one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
        cursor.execute('''
            DELETE FROM button_clicks 
            WHERE last_click < ?
        ''', (one_day_ago,))
        
        conn.commit()
        conn.close()

    # Adicionar ao arquivo database.py

    def is_reseller(self, user_id):
        """Verifica se um usuário é revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT 1 FROM resellers WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return bool(result)

    def get_reseller_credits(self, user_id):
        """Obtém o saldo de créditos de um revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT credits FROM resellers WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else 0

    def get_reseller_data(self, user_id):
        """Obtém todos os dados de um revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                user_id, 
                credits, 
                mercado_pago_token, 
                created_at, 
                last_activity
            FROM resellers 
            WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return {}
            
        return {
            'user_id': result[0],
            'credits': result[1],
            'mercado_pago_token': result[2],
            'created_at': result[3],
            'last_activity': result[4]
        }

    def generate_affiliate_code(self, user_id):
        """Gera um código de afiliado único para o revendedor"""
        import hashlib
        import random
        import string
        import time
        
        # Verifica se já existe um código
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT affiliate_code FROM resellers WHERE user_id = ?', (user_id,))
        existing_code = cursor.fetchone()
        
        if existing_code and existing_code[0]:
            conn.close()
            return existing_code[0]
        
        # Gera um novo código
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
        code_base = f"{user_id}_{salt}_{int(time.time())}"
        code_hash = hashlib.md5(code_base.encode()).hexdigest()[:8]
        
        # Salva o código
        cursor.execute('''
            UPDATE resellers
            SET affiliate_code = ?
            WHERE user_id = ?
        ''', (code_hash, user_id))
        
        conn.commit()
        conn.close()
        
        return code_hash

    def count_reseller_clients(self, reseller_id):
        """Conta quantos clientes um revendedor possui"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*)
            FROM reseller_clients
            WHERE reseller_id = ?
        ''', (reseller_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0


    def count_reseller_active_clients(self, reseller_id):
        """Conta quantos clientes ativos e pagantes um revendedor possui (exclui clientes em teste)"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        current_time = datetime.now().isoformat()
        
        # Verificamos se há registros de pagamentos para estes clientes
        # Um cliente é considerado pagante se tem um pagamento aprovado
        cursor.execute('''
            SELECT COUNT(DISTINCT rc.client_id)
            FROM reseller_clients rc
            JOIN users u ON rc.client_id = u.user_id
            JOIN payments p ON p.user_id = rc.client_id
            WHERE rc.reseller_id = ? 
            AND u.subscription_end > ? 
            AND p.status = 'approved'
        ''', (reseller_id, current_time))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0


    def set_reseller_mp_token(self, user_id, token):
        """Define o token do Mercado Pago para o revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE resellers
            SET mercado_pago_token = ?, last_activity = ?
            WHERE user_id = ?
        ''', (token, datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()
        
        return True



    def count_reseller_trial_clients(self, reseller_id):
        """Conta quantos clientes em período de teste um revendedor possui"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        current_time = datetime.now().isoformat()
        trial_period = datetime.now() - timedelta(days=TRIAL_DAYS)
        trial_period_iso = trial_period.isoformat()
        
        # Modificação: Consideramos cliente em teste se está ainda no período inicial 
        # (subscription_end aproximadamente TRIAL_DAYS após o momento atual)
        cursor.execute('''
            SELECT COUNT(*)
            FROM reseller_clients rc
            JOIN users u ON rc.client_id = u.user_id
            WHERE rc.reseller_id = ? 
            AND u.subscription_end > ? 
            AND u.is_trial_used = 1
            AND u.created_at > ?
        ''', (reseller_id, current_time, trial_period_iso))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0

    def get_reseller_stats(self, reseller_id):
        """Obtém estatísticas do revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Total de clientes
        cursor.execute('''
            SELECT COUNT(*)
            FROM reseller_clients
            WHERE reseller_id = ?
        ''', (reseller_id,))
        
        total_clients = cursor.fetchone()[0]
        
        # Clientes ativos pagantes (com assinatura válida e pagamento aprovado)
        current_time = datetime.now().isoformat()
        cursor.execute('''
            SELECT COUNT(DISTINCT rc.client_id)
            FROM reseller_clients rc
            JOIN users u ON rc.client_id = u.user_id
            JOIN payments p ON p.user_id = rc.client_id
            WHERE rc.reseller_id = ? 
            AND u.subscription_end > ? 
            AND p.status = 'approved'
        ''', (reseller_id, current_time))
        
        active_clients = cursor.fetchone()[0]
        
        # Clientes em teste (com assinatura válida mas sem pagamento aprovado)
        cursor.execute('''
            SELECT COUNT(*)
            FROM reseller_clients rc
            JOIN users u ON rc.client_id = u.user_id
            LEFT JOIN payments p ON p.user_id = rc.client_id AND p.status = 'approved'
            WHERE rc.reseller_id = ? 
            AND u.subscription_end > ? 
            AND p.payment_id IS NULL
        ''', (reseller_id, current_time))
        
        trial_clients = cursor.fetchone()[0]
        
        # Total de dias adicionados
        cursor.execute('''
            SELECT SUM(days)
            FROM reseller_transactions
            WHERE reseller_id = ?
        ''', (reseller_id,))
        
        total_days = cursor.fetchone()[0] or 0
        
        # Total de receita (baseado em transações)
        cursor.execute('''
            SELECT SUM(amount)
            FROM reseller_credit_payments
            WHERE reseller_id = ? AND status = 'approved'
        ''', (reseller_id,))
        
        total_revenue = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_clients': total_clients,
            'active_clients': active_clients,
            'trial_clients': trial_clients,
            'total_days': total_days,
            'total_revenue': total_revenue
        }
        
    def get_reseller_clients(self, reseller_id):
        print(f"[LOG] get_reseller_clients: reseller_id={reseller_id}")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT rc.client_id, u.phone_number, u.subscription_end, u.last_login
            FROM reseller_clients rc
            JOIN users u ON rc.client_id = u.user_id
            WHERE rc.reseller_id = ?
            ORDER BY u.subscription_end DESC
        ''', (reseller_id,))
        results = cursor.fetchall()
        print(f"[LOG] Resultado do banco: {results}")
        conn.close()
        clients = []
        for row in results:
            client_id, phone, sub_end, last_login = row
            clients.append({
                'user_id': client_id,
                'phone': phone,
                'subscription_end': sub_end,
                'last_login': last_login,
                'name': f"Cliente {client_id[-4:]}"
            })
        print(f"[LOG] Lista final de clientes: {clients}")
        return clients

    def is_client_of_reseller(self, client_id, reseller_id):
        """Verifica se um cliente pertence a um determinado revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 1
            FROM reseller_clients
            WHERE client_id = ? AND reseller_id = ?
        ''', (client_id, reseller_id))
        
        result = cursor.fetchone()
        conn.close()
        
        return bool(result)

    def get_client_data(self, client_id):
        """Obtém dados de um cliente"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, phone_number, subscription_end, last_login
            FROM users
            WHERE user_id = ?
        ''', (client_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return {}
        
        user_id, phone, sub_end, last_login = result
        
        return {
            'user_id': user_id,
            'phone': phone,
            'subscription_end': sub_end,
            'last_login': last_login,
            'name': f"Cliente {user_id[-4:]}"  # Usando últimos 4 dígitos do ID
        }

    def deduct_reseller_credits(self, reseller_id, credits):
        """Deduz créditos de um revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Verifica o saldo atual
        cursor.execute('SELECT credits FROM resellers WHERE user_id = ?', (reseller_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False
        
        current_credits = result[0]
        
        if current_credits < credits:
            conn.close()
            return False
        
        # Atualiza o saldo
        cursor.execute('''
            UPDATE resellers
            SET credits = credits - ?, last_activity = ?
            WHERE user_id = ?
        ''', (credits, datetime.now().isoformat(), reseller_id))
        
        conn.commit()
        conn.close()
        
        return True
        
    def extend_client_subscription(self, client_id, days):
        """Estende a assinatura de um cliente (versão para revendedor)"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Busca data atual
        cursor.execute('SELECT subscription_end FROM users WHERE user_id = ?', (client_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            current_end = datetime.fromisoformat(result[0])
            if current_end > datetime.now():
                new_end = current_end + timedelta(days=days)
            else:
                new_end = datetime.now() + timedelta(days=days)
        else:
            new_end = datetime.now() + timedelta(days=days)
        
        cursor.execute('''
            UPDATE users 
            SET subscription_end = ?
            WHERE user_id = ?
        ''', (new_end.isoformat(), client_id))
        
        conn.commit()
        conn.close()
        
        return True

    def add_reseller_transaction(self, reseller_id, client_id, days):
        """Registra uma transação de dias de um revendedor para um cliente"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO reseller_transactions
            (reseller_id, client_id, days, transaction_date)
            VALUES (?, ?, ?, ?)
        ''', (reseller_id, client_id, days, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return True

    def add_credit_payment(self, user_id, payment_id, amount, credits):
        """Adiciona um pagamento para compra de créditos"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        try:
            # CORREÇÃO: Verificar se o revendedor existe
            cursor.execute('SELECT 1 FROM resellers WHERE user_id = ?', (user_id,))
            if cursor.fetchone() is None:
                print(f"Erro: Tentativa de adicionar créditos para um não-revendedor: {user_id}")
                conn.close()
                return False
            
            # CORREÇÃO: Verificar se já existe esse payment_id
            cursor.execute('SELECT 1 FROM reseller_credit_payments WHERE payment_id = ?', (payment_id,))
            if cursor.fetchone() is not None:
                print(f"Aviso: Payment ID {payment_id} já existe na tabela")
                conn.close()
                return False
            
            # CORREÇÃO: Incluir validações de dados
            if not payment_id or not user_id or amount <= 0 or credits <= 0:
                print(f"Erro: Dados inválidos para pagamento de créditos: user_id={user_id}, payment_id={payment_id}, amount={amount}, credits={credits}")
                conn.close()
                return False
            
            cursor.execute('''
                INSERT INTO reseller_credit_payments
                (reseller_id, payment_id, amount, credits, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
            ''', (user_id, payment_id, amount, credits, datetime.now().isoformat()))
            
            # Log para debug
            print(f"✅ Pagamento de créditos registrado: ID={payment_id}, Revendedor={user_id}, Valor={amount}, Créditos={credits}")
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Erro ao adicionar pagamento de créditos: {str(e)}")
            try:
                conn.close()
            except:
                pass
            return False

    def get_reseller_by_affiliate(self, affiliate_code):
        """Obtém o ID do revendedor pelo código de afiliado"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id
            FROM resellers
            WHERE affiliate_code = ?
        ''', (affiliate_code,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None

    def is_user_registered(self, user_id):
        """Verifica se um usuário já está registrado no banco"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return bool(result)

    def get_client_reseller(self, client_id):
        """Obtém o ID do revendedor de um cliente"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT reseller_id
            FROM reseller_clients
            WHERE client_id = ?
        ''', (client_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None

    def associate_client_to_reseller(self, client_id, reseller_id):
        client_id = str(client_id)
        reseller_id = str(reseller_id)
        print(f"[LOG] associate_client_to_reseller: client_id={client_id} (type={type(client_id)}), reseller_id={reseller_id} (type={type(reseller_id)})")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO reseller_clients
            (client_id, reseller_id, association_date)
            VALUES (?, ?, ?)
        ''', (client_id, reseller_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        print("[LOG] Inserção feita na tabela reseller_clients")
        return True

    def save_pending_association(self, client_id, reseller_id, revenda_uid=None):
        if revenda_uid is None:
            revenda_uid = client_id
        print(f"[REV] Salvando pendência: revenda_uid={revenda_uid} client_id={client_id} reseller_id={reseller_id}")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO pending_associations
            (client_id, reseller_id, created_at)
            VALUES (?, ?, ?)
        ''', (revenda_uid, reseller_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def check_pending_association(self, client_id, revenda_uid=None):
        if revenda_uid is None:
            revenda_uid = client_id
        print(f"[REV] Buscando pendência para revenda_uid={revenda_uid}")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT reseller_id
            FROM pending_associations
            WHERE client_id = ?
        ''', (revenda_uid,))
        result = cursor.fetchone()
        conn.close()
        print(f"[REV] Resultado da busca de pendência: {result}")
        return result[0] if result else None


    def process_pending_association(self, client_id, revenda_uid=None):
        if revenda_uid is None:
            revenda_uid = client_id
        print(f"[REV] process_pending_association: revenda_uid={revenda_uid}")
        reseller_id = self.check_pending_association(client_id, revenda_uid)
        print(f"[REV] reseller_id pendente: {reseller_id}")
        if not reseller_id:
            print("[REV] Nenhuma associação pendente encontrada")
            return False, "Nenhuma associação pendente encontrada"
        if not self.can_accept_new_client(reseller_id):
            print(f"[REV] Revendedor {reseller_id} não pode aceitar novos clientes")
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM pending_associations WHERE client_id = ?', (revenda_uid,))
            conn.commit()
            conn.close()
            return False, "O revendedor não possui créditos suficientes para novos clientes"
        success = self.associate_client_to_reseller(client_id, reseller_id)
        print(f"[REV] associate_client_to_reseller retornou: {success}")
        if success:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM pending_associations WHERE client_id = ?', (revenda_uid,))
            conn.commit()
            conn.close()
        return success, "Cliente associado com sucesso"


    def add_reseller(self, user_id, initial_credits=0):
        """Adiciona um novo revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO resellers
            (user_id, credits, created_at, last_activity)
            VALUES (?, ?, ?, ?)
        ''', (user_id, initial_credits, datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return True


    def remove_reseller(self, user_id):
        """Remove um revendedor e todas as assinaturas associadas"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Primeiro, obtenha todos os clientes deste revendedor
        cursor.execute('SELECT client_id FROM reseller_clients WHERE reseller_id = ?', (user_id,))
        clients = [row[0] for row in cursor.fetchall()]
        
        # Remove assinaturas de todos os clientes
        for client_id in clients:
            cursor.execute('UPDATE users SET subscription_end = NULL WHERE user_id = ?', (client_id,))
        
        # Remove registros relacionados ao revendedor
        cursor.execute('DELETE FROM reseller_clients WHERE reseller_id = ?', (user_id,))
        cursor.execute('DELETE FROM reseller_transactions WHERE reseller_id = ?', (user_id,))
        cursor.execute('DELETE FROM reseller_credit_payments WHERE reseller_id = ?', (user_id,))
        cursor.execute('DELETE FROM pending_associations WHERE reseller_id = ?', (user_id,))
        
        # Remove o revendedor
        cursor.execute('DELETE FROM resellers WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        return True

    def add_credits_to_reseller(self, user_id, credits):
        """Adiciona créditos a um revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE resellers
            SET credits = credits + ?, last_activity = ?
            WHERE user_id = ?
        ''', (credits, datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()
        
        return True


    def update_credit_payment_status(self, payment_id, status):
        """Atualiza o status de um pagamento de créditos"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        try:
            print(f"Atualizando status do pagamento {payment_id} para {status}")
            
            cursor.execute('''
                UPDATE reseller_credit_payments
                SET status = ?
                WHERE payment_id = ?
            ''', (status, payment_id))
            
            # CORREÇÃO: Verificar se o UPDATE afetou alguma linha
            if cursor.rowcount == 0:
                print(f"Aviso: Nenhuma linha atualizada para o pagamento {payment_id}")
                
                # DEBUG: Verificar se o pagamento existe
                cursor.execute('SELECT 1 FROM reseller_credit_payments WHERE payment_id = ?', (payment_id,))
                exists = cursor.fetchone() is not None
                if not exists:
                    print(f"Erro: Pagamento {payment_id} não existe na tabela")
                    conn.commit()
                    conn.close()
                    return False
            
            # Se foi aprovado, adiciona os créditos ao revendedor
            if status == 'approved':
                cursor.execute('''
                    SELECT reseller_id, credits
                    FROM reseller_credit_payments
                    WHERE payment_id = ?
                ''', (payment_id,))
                
                result = cursor.fetchone()
                
                if result:
                    reseller_id, credits = result
                    print(f"Adicionando {credits} créditos ao revendedor {reseller_id}")
                    
                    # CORREÇÃO: Verificar se o revendedor existe
                    cursor.execute('SELECT 1 FROM resellers WHERE user_id = ?', (reseller_id,))
                    reseller_exists = cursor.fetchone() is not None
                    
                    if not reseller_exists:
                        print(f"Erro: Revendedor {reseller_id} não existe")
                        conn.commit()
                        conn.close()
                        return False
                    
                    # Adiciona os créditos ao revendedor
                    cursor.execute('''
                        UPDATE resellers
                        SET credits = credits + ?, last_activity = ?
                        WHERE user_id = ?
                    ''', (credits, datetime.now().isoformat(), reseller_id))
                    
                    # Verifica se o UPDATE afetou alguma linha
                    if cursor.rowcount == 0:
                        print(f"Erro: Não foi possível adicionar créditos ao revendedor {reseller_id}")
                        conn.commit()
                        conn.close()
                        return False
                    
                    # CORREÇÃO: Registrar o crédito no log de transações
                    cursor.execute('''
                        INSERT INTO reseller_transactions
                        (reseller_id, client_id, days, transaction_date)
                        VALUES (?, 'credit_purchase', ?, ?)
                    ''', (reseller_id, credits, datetime.now().isoformat()))
                    
                    print(f"✅ {credits} créditos adicionados com sucesso ao revendedor {reseller_id}")
                else:
                    print(f"Erro: Dados do pagamento {payment_id} não encontrados após UPDATE")
                    conn.commit()
                    conn.close()
                    return False
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Erro ao atualizar pagamento de créditos {payment_id}: {str(e)}")
            try:
                conn.close()
            except:
                pass
            return False


    def get_reseller_by_credit_payment(self, payment_id):
        """Obtém o ID do revendedor por um pagamento de créditos"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        try:
            print(f"Buscando pagamento de créditos: {payment_id}")
            
            # CORREÇÃO: Melhorar query para diagnóstico
            cursor.execute('''
                SELECT reseller_id, credits, status, created_at
                FROM reseller_credit_payments
                WHERE payment_id = ?
            ''', (payment_id,))
            
            result = cursor.fetchone()
            
            if result:
                print(f"Pagamento de créditos encontrado: ResellerID={result[0]}, Credits={result[1]}, Status={result[2]}, Created={result[3]}")
                return result[0], result[1]
            else:
                # DEBUG: Verificar todos os pagamentos recentes
                print("Pagamento não encontrado, verificando pagamentos recentes...")
                cursor.execute('''
                    SELECT payment_id, reseller_id, credits, status
                    FROM reseller_credit_payments
                    ORDER BY created_at DESC
                    LIMIT 5
                ''')
                
                recent = cursor.fetchall()
                for r in recent:
                    print(f"Pagamento recente: ID={r[0]}, ResellerID={r[1]}, Credits={r[2]}, Status={r[3]}")
                
                print(f"Pagamento {payment_id} NÃO encontrado na tabela de créditos")
                return None, 0
                
        except Exception as e:
            print(f"Erro ao buscar pagamento de créditos {payment_id}: {str(e)}")
            return None, 0
        finally:
            conn.close()

    def list_all_resellers(self):
        """Lista todos os revendedores com seus detalhes"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                r.user_id,
                r.credits,
                r.created_at,
                r.last_activity,
                (SELECT COUNT(*) FROM reseller_clients WHERE reseller_id = r.user_id) as total_clients,
                u.phone_number
            FROM resellers r
            LEFT JOIN users u ON r.user_id = u.user_id
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        resellers = []
        for row in results:
            user_id, credits, created_at, last_activity, total_clients, phone = row
            
            resellers.append({
                'user_id': user_id,
                'credits': credits,
                'created_at': created_at,
                'last_activity': last_activity,
                'total_clients': total_clients,
                'phone': phone if phone else 'Não cadastrado'
            })
        
        return resellers

    def _ensure_suspenso_column(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'suspenso' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN suspenso INTEGER DEFAULT 0')
                conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar coluna suspenso: {e}")
        finally:
            conn.close()

    def increment_reseller_trial(self, reseller_id):
        """Incrementa o contador de testes do revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reseller_trials (reseller_id, trial_count)
            VALUES (?, 1)
            ON CONFLICT(reseller_id) DO UPDATE SET trial_count = trial_count + 1
        ''', (reseller_id,))
        conn.commit()
        conn.close()

    def get_reseller_trial_count(self, reseller_id):
        """Obtém o número de testes do revendedor"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT trial_count FROM reseller_trials WHERE reseller_id = ?
        ''', (reseller_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
