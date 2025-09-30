import sqlite3
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.connection = None
        from config import DB_PATH
        self.db_path = DB_PATH
        self.connect()

    def connect(self):
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)

            self.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30
            )
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.row_factory = sqlite3.Row

            self._create_tables()
            logger.info(f"✅ Успешное подключение к SQLite: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к SQLite: {e}")
            self.connection = None

    def _create_tables(self):
        if not self.connection:
            return

        try:
            cursor = self.connection.cursor()

            create_table_query = """
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_date DATETIME NOT NULL,
                system_version VARCHAR(50) NOT NULL,
                test_system_version VARCHAR(50) NOT NULL,
                total_images INTEGER NOT NULL DEFAULT 0,
                successful_images INTEGER NOT NULL DEFAULT 0,
                error_images INTEGER NOT NULL DEFAULT 0,
                total_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                counter_reading_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                serial_number_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                counter_model_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                tariff_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                comments TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """

            cursor.execute(create_table_query)
            self.connection.commit()
            logger.info("✅ Таблица test_results создана/проверена")

        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")

    def save_test_result(self, report_data, excel_file_path=None):
        if not self.connection:
            self.connect()
            if not self.connection:
                return False

        try:
            cursor = self.connection.cursor()
            query = """
            INSERT INTO test_results (
                test_date, system_version, test_system_version, total_images,
                successful_images, error_images, total_accuracy, counter_reading_accuracy,
                serial_number_accuracy, counter_model_accuracy, tariff_accuracy,
                duration_seconds, comments
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            from config import APP_VERSION

            file_info = f"Файл: {os.path.basename(excel_file_path)}" if excel_file_path else "Тестовые данные"
            comments = f"Автоматическое тестирование. {file_info}. Успешность: {report_data['success_rate']:.1f}%"

            values = (
                report_data['completion_time'],
                APP_VERSION,
                "test_suite_v1.0",
                report_data['total_images'],
                report_data['successfully_processed'],
                report_data['errors'],
                report_data['accuracy']['overall']['accuracy'],
                report_data['accuracy']['indications']['accuracy'],
                report_data['accuracy']['series']['accuracy'],
                report_data['accuracy']['model']['accuracy'],
                report_data['accuracy']['rate']['accuracy'],
                report_data['total_time_seconds'],
                comments
            )

            cursor.execute(query, values)
            self.connection.commit()

            logger.info(f"✅ Результаты тестирования сохранены в базу данных (ID: {cursor.lastrowid})")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в базу данных: {e}")
            return False
        finally:
            if cursor:
                cursor.close()

    def get_test_history(self, limit=10):
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            query = """
            SELECT * FROM test_results 
            ORDER BY test_date DESC 
            LIMIT ?
            """

            cursor.execute(query, (limit,))
            results = cursor.fetchall()

            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in results]

        except Exception as e:
            logger.error(f"❌ Ошибка получения истории тестов: {e}")
            return []
        finally:
            if cursor:
                cursor.close()

    def get_total_records(self):
        if not self.connection:
            self.connect()
            if not self.connection:
                return 0

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM test_results")
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества записей: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()

    def get_last_insert_id(self):
        if not self.connection:
            return "N/A"

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT last_insert_rowid()")
            result = cursor.fetchone()
            return result[0] if result else "N/A"
        except Exception as e:
            logger.error(f"❌ Ошибка получения последнего ID: {e}")
            return "N/A"
        finally:
            if cursor:
                cursor.close()

    def clear_test_data(self):
        if not self.connection:
            return False

        try:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM test_results")
            self.connection.commit()
            logger.info("✅ Тестовые данные очищены")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка очистки данных: {e}")
            return False
        finally:
            if cursor:
                cursor.close()

    def backup_database(self, backup_path=None):
        try:
            if backup_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"backup_testing_system_{timestamp}.db"

            import shutil
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"✅ Резервная копия создана: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"❌ Ошибка создания резервной копии: {e}")
            return None

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("✅ Соединение с базой данных закрыто")


db_manager = DatabaseManager()