import mysql.connector
import logging
from mysql.connector import Error
from config import *

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connect()

    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 3306)),
                database=os.getenv('DB_NAME', 'detection_system'),
                user=os.getenv('DB_USER', 'root'),
                password=os.getenv('DB_PASSWORD', '')
            )
            logger.info("Успешное подключение к MySQL")
        except Error as e:
            logger.error(f"Ошибка подключения к MySQL: {e}")
            self.connection = None

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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

            logger.info(f"Результаты тестирования сохранены в базу данных (ID: {cursor.lastrowid})")
            return True

        except Error as e:
            logger.error(f"Ошибка сохранения в базу данных: {e}")
            return False
        finally:
            if cursor:
                cursor.close()

    def get_test_history(self, limit=10):
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(dictionary=True)

            query = """
            SELECT * FROM test_results 
            ORDER BY test_date DESC 
            LIMIT %s
            """

            cursor.execute(query, (limit,))
            results = cursor.fetchall()

            return results

        except Error as e:
            logger.error(f"Ошибка получения истории тестов: {e}")
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
        except Error as e:
            logger.error(f"Ошибка получения количества записей: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()

    def get_last_insert_id(self):
        if not self.connection:
            return "N/A"

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT LAST_INSERT_ID()")
            result = cursor.fetchone()
            return result[0] if result else "N/A"
        except Error as e:
            logger.error(f"Ошибка получения последнего ID: {e}")
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
            logger.info("Тестовые данные очищены")
            return True
        except Error as e:
            logger.error(f"Ошибка очистки данных: {e}")
            return False
        finally:
            if cursor:
                cursor.close()

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("Соединение с базой данных закрыто")


db_manager = DatabaseManager()