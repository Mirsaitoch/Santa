import sqlite3
from typing import List, Tuple, Optional


class Database:
    def __init__(self, db_name: str = 'santa.db'):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                wishlist TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавляем колонку wishlist, если её нет (для существующих БД)
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN wishlist TEXT')
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
        
        # Таблица исключений (кто кому не может дарить)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exclusions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER,
                user2_id INTEGER,
                FOREIGN KEY (user1_id) REFERENCES users(user_id),
                FOREIGN KEY (user2_id) REFERENCES users(user_id),
                UNIQUE(user1_id, user2_id)
            )
        ''')
        
        # Таблица распределения (кто кому дарит)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giver_id INTEGER,
                receiver_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (giver_id) REFERENCES users(user_id),
                FOREIGN KEY (receiver_id) REFERENCES users(user_id),
                UNIQUE(giver_id)
            )
        ''')
        
        conn.commit()
        conn.close()

    def add_user(self, user_id: int, username: str, first_name: str, last_name: str = None, wishlist: str = None):
        """Добавить пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, wishlist)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, wishlist))
        conn.commit()
        conn.close()

    def get_user(self, user_id: int) -> Optional[Tuple]:
        """Получить пользователя по ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user

    def get_all_users(self) -> List[Tuple]:
        """Получить всех пользователей"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users ORDER BY first_name')
        users = cursor.fetchall()
        conn.close()
        return users

    def is_registered(self, user_id: int) -> bool:
        """Проверить, зарегистрирован ли пользователь"""
        return self.get_user(user_id) is not None

    def add_exclusion(self, user1_id: int, user2_id: int):
        """Добавить исключение (user1 и user2 не могут дарить друг другу)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Добавляем в обе стороны для удобства
        try:
            cursor.execute('''
                INSERT INTO exclusions (user1_id, user2_id)
                VALUES (?, ?)
            ''', (min(user1_id, user2_id), max(user1_id, user2_id)))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Уже существует
        conn.close()

    def remove_exclusion(self, user1_id: int, user2_id: int):
        """Удалить исключение"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM exclusions
            WHERE user1_id = ? AND user2_id = ?
        ''', (min(user1_id, user2_id), max(user1_id, user2_id)))
        conn.commit()
        conn.close()

    def get_exclusions(self) -> List[Tuple]:
        """Получить все исключения"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM exclusions')
        exclusions = cursor.fetchall()
        conn.close()
        return exclusions

    def has_exclusion(self, user1_id: int, user2_id: int) -> bool:
        """Проверить, есть ли исключение между двумя пользователями"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM exclusions
            WHERE user1_id = ? AND user2_id = ?
        ''', (min(user1_id, user2_id), max(user1_id, user2_id)))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    def clear_assignments(self):
        """Очистить все распределения"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM assignments')
        conn.commit()
        conn.close()

    def save_assignment(self, giver_id: int, receiver_id: int):
        """Сохранить распределение"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO assignments (giver_id, receiver_id)
            VALUES (?, ?)
        ''', (giver_id, receiver_id))
        conn.commit()
        conn.close()

    def get_assignment(self, giver_id: int) -> Optional[int]:
        """Получить, кому должен дарить пользователь"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT receiver_id FROM assignments WHERE giver_id = ?', (giver_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def get_giver_by_receiver(self, receiver_id: int) -> Optional[int]:
        """Получить, кто дарит подарок получателю"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT giver_id FROM assignments WHERE receiver_id = ?', (receiver_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def get_all_assignments(self) -> List[Tuple]:
        """Получить все распределения"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM assignments')
        assignments = cursor.fetchall()
        conn.close()
        return assignments

    def remove_user(self, user_id: int):
        """Удалить пользователя и все связанные данные"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Удаляем исключения, где участвует этот пользователь
        cursor.execute('''
            DELETE FROM exclusions
            WHERE user1_id = ? OR user2_id = ?
        ''', (user_id, user_id))
        
        # Удаляем распределения, где пользователь даритель или получатель
        cursor.execute('''
            DELETE FROM assignments
            WHERE giver_id = ? OR receiver_id = ?
        ''', (user_id, user_id))
        
        # Удаляем самого пользователя
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()

    def update_wishlist(self, user_id: int, wishlist: str):
        """Обновить вишлист пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET wishlist = ? WHERE user_id = ?
        ''', (wishlist, user_id))
        conn.commit()
        conn.close()

    def get_wishlist(self, user_id: int) -> Optional[str]:
        """Получить вишлист пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT wishlist FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else None

