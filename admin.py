"""Módulo de administração do bot"""
from datetime import datetime, timedelta
from typing import Dict, List, Any
import sqlite3
from config import DB_FILE, ADMIN_PASSWORD, SUBSCRIPTION_DAYS

class AdminModule:
    def __init__(self, database):
        self.db = database
        self.DB_FILE = DB_FILE
        self.ADMIN_PASSWORD = ADMIN_PASSWORD
        
    def check_admin_password(self, password: str) -> bool:
        """Verifica se a senha de admin está correta"""
        return password == self.ADMIN_PASSWORD
    
    def toggle_phone_change(self, enabled):
        """Ativa ou desativa a troca de número"""
        self.db.set_phone_change_enabled(enabled)
        return True


    # Adicionar ao arquivo admin.py

    def list_all_resellers(self) -> List[Dict[str, Any]]:
        """Lista todos os revendedores com seus detalhes"""
        return self.db.list_all_resellers()

    def add_reseller(self, user_id: str, initial_credits: int = 0) -> bool:
        """Adiciona um novo revendedor"""
        return self.db.add_reseller(user_id, initial_credits)

    def remove_reseller(self, user_id: str) -> bool:
        """Remove um revendedor"""
        return self.db.remove_reseller(user_id)

    def add_credits_to_reseller(self, user_id: str, credits: int) -> bool:
        """Adiciona créditos a um revendedor"""
        return self.db.add_credits_to_reseller(user_id, credits)


      
    def list_all_users(self) -> List[Dict[str, Any]]:
        """Lista todos os usuários ATIVOS com seus detalhes"""
        conn = sqlite3.connect(self.DB_FILE)
        cursor = conn.cursor()
        try:
            now = datetime.now().isoformat()
            cursor.execute('''
                SELECT 
                    user_id,
                    phone_number,
                    subscription_end,
                    created_at,
                    last_login,
                    auto_collect_enabled,
                    operator
                FROM users
                WHERE subscription_end > ?
            ''', (now,))
            users = []
            for row in cursor.fetchall():
                user_id, phone, sub_end, created, last_login, auto_collect, operator = row
                # Calcula dias restantes
                days_left = 0
                if sub_end:
                    try:
                        end_date = datetime.fromisoformat(sub_end)
                        days_left = (end_date - datetime.now()).days
                    except:
                        days_left = 0
                phone_display = phone if phone else "Não cadastrado"
                # Formata datas
                created_display = "-"
                if created:
                    try:
                        created_display = datetime.fromisoformat(created).strftime("%d/%m/%Y %H:%M")
                    except:
                        created_display = str(created)
                last_login_display = "-"
                if last_login:
                    try:
                        last_login_display = datetime.fromisoformat(last_login).strftime("%d/%m/%Y %H:%M")
                    except:
                        last_login_display = str(last_login)
                users.append({
                    'user_id': user_id,
                    'phone': phone_display,
                    'subscription_end': sub_end,
                    'days_left': days_left,
                    'created_at': created_display,
                    'last_login': last_login_display,
                    'auto_collect': bool(auto_collect),
                    'operator': operator if operator else "-"
                })
        except Exception as e:
            print(f"Erro ao listar usuários: {str(e)}")
            users = []
        finally:
            conn.close()
        return users
        
    def list_expired_users(self) -> List[Dict[str, Any]]:
        """Lista usuários com assinatura vencida"""
        conn = sqlite3.connect(self.DB_FILE)
        cursor = conn.cursor()
        
        try:
            now = datetime.now().isoformat()
            
            # Usuários com subscription_end no passado ou NULL
            cursor.execute('''
                SELECT 
                    user_id,
                    phone_number,
                    subscription_end,
                    last_login
                FROM users 
                WHERE subscription_end < ? OR subscription_end IS NULL
            ''', (now,))
            
            expired = []
            for row in cursor.fetchall():
                user_id, phone, sub_end, last_login = row
                
                # Mostra telefone completo
                phone_display = phone if phone else "Não cadastrado"
                
                # Formata data de vencimento
                if sub_end:
                    try:
                        end_date = datetime.fromisoformat(sub_end)
                        venc_display = end_date.strftime("%d/%m/%Y %H:%M")
                    except:
                        venc_display = "Data inválida"
                else:
                    venc_display = "Nunca ativo"
                
                # Formata último login
                if last_login:
                    try:
                        login_date = datetime.fromisoformat(last_login)
                        login_display = login_date.strftime("%d/%m/%Y %H:%M")
                    except:
                        login_display = "Data inválida"
                else:
                    login_display = "Nunca logou"
                
                expired.append({
                    'user_id': user_id,
                    'phone': phone_display,
                    'subscription_end': venc_display,
                    'last_login': login_display
                })
                
        except Exception as e:
            print(f"Erro ao listar usuários vencidos: {str(e)}")
            expired = []
            
        finally:
            conn.close()
            
        return expired
        
    def renew_user(self, user_id: str, days: int = SUBSCRIPTION_DAYS) -> bool:
        """Renova assinatura de um usuário"""
        conn = sqlite3.connect(self.DB_FILE)
        cursor = conn.cursor()
        
        try:
            # Verifica se usuário existe
            cursor.execute('SELECT subscription_end FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                print(f"Usuário {user_id} não encontrado")
                return False
            
            # Calcula nova data
            current_end = None
            if result[0]:
                try:
                    current_end = datetime.fromisoformat(result[0])
                except:
                    current_end = None
            
            if current_end and current_end > datetime.now():
                new_end = current_end + timedelta(days=days)
            else:
                new_end = datetime.now() + timedelta(days=days)
            
            # Atualiza no banco
            cursor.execute('''
                UPDATE users 
                SET subscription_end = ?
                WHERE user_id = ?
            ''', (new_end.isoformat(), user_id))
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"Erro ao renovar usuário {user_id}: {str(e)}")
            return False
            
        finally:
            conn.close()
            
    def remove_days(self, user_id: str, days: int) -> bool:
        """Remove dias da assinatura de um usuário"""
        conn = sqlite3.connect(self.DB_FILE)
        cursor = conn.cursor()
        
        try:
            # Verifica se usuário existe
            cursor.execute('SELECT subscription_end FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                print(f"Usuário {user_id} não encontrado")
                return False
            
            if not result[0]:
                print(f"Usuário {user_id} não tem assinatura")
                return False
            
            try:
                current_end = datetime.fromisoformat(result[0])
                new_end = current_end - timedelta(days=days)
                
                cursor.execute('''
                    UPDATE users 
                    SET subscription_end = ?
                    WHERE user_id = ?
                ''', (new_end.isoformat(), user_id))
                
                conn.commit()
                return True
                
            except:
                print(f"Data de assinatura inválida para usuário {user_id}")
                return False
                
        except Exception as e:
            print(f"Erro ao remover dias do usuário {user_id}: {str(e)}")
            return False
            
        finally:
            conn.close()
        
    def delete_user(self, user_id: str) -> bool:
        """Exclui um usuário do sistema"""
        conn = sqlite3.connect(self.DB_FILE)
        cursor = conn.cursor()
        
        try:
            # Verifica se usuário existe
            cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
            if not cursor.fetchone():
                print(f"Usuário {user_id} não encontrado")
                return False
            
            # Remove das tabelas relacionadas primeiro
            cursor.execute('DELETE FROM linking_history WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM payments WHERE user_id = ?', (user_id,))
            
            # Remove o usuário
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            
            # Remove dos dados em JSON também
            users = self.db.load_users()
            if user_id in users:
                del users[user_id]
                self.db.save_users(users)
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"Erro ao excluir usuário {user_id}: {str(e)}")
            return False
            
        finally:
            try:
                conn.close()
            except:
                pass

    def suspender_usuario(self, user_id: str) -> bool:
        """Suspende o usuário imediatamente (define suspenso=1)"""
        conn = sqlite3.connect(self.DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET suspenso = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao suspender usuário {user_id}: {str(e)}")
            return False
        finally:
            conn.close()

    def ativar_usuario(self, user_id: str) -> bool:
        """Ativa o usuário (define suspenso=0)"""
        conn = sqlite3.connect(self.DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET suspenso = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao ativar usuário {user_id}: {str(e)}")
            return False
        finally:
            conn.close()