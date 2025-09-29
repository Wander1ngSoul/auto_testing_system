import sys
import time
import logging

from config import *
from utils.file_utils import validate_environment, get_image_files
from process.image_processor import process_images_folder
from generators.report_generator import generate_summary_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("🚀 АВТОМАТИЗИРОВАННОЕ ТЕСТИРОВАНИЕ СИСТЕМЫ РАСПОЗНАВАНИЯ")
    logger.info("=" * 60)

    if SELECTED_SERVER == 'default':
        logger.info("⚙️  РЕЖИМ: Локальный (default)")
        processing_mode = "последовательная обработка"
    else:
        server_url = SERVERS.get(SELECTED_SERVER)
        logger.info(f"🌐 РЕЖИМ: Серверный - {SELECTED_SERVER}")
        logger.info(f"🔗 URL: {server_url}")
        logger.info(f"🔑 Токен авторизации: {AUTHORIZED_TOKEN[:8]}...")
        logger.info("📋 API: Многоэтапный (tasks → status → result)")
        processing_mode = "последовательная обработка (серверная очередь)"

    if not validate_environment():
        logger.error("❌ Проверка окружения не пройдена. Завершение работы.")
        sys.exit(1)

    logger.info(f"📁 Папка с изображениями: {FOLDER_TEST}")
    logger.info(f"📊 Excel файл: {EXCEL_DATA}")
    logger.info(f"🔄 Режим обработки: {processing_mode}")

    if SELECTED_SERVER == 'default':
        logger.info(f"🐍 Программа распознавания: {PROGRAM_SCRIPT}")

    start_time = time.time()

    success, processed_count, errors_count, skipped_count = process_images_folder(
        FOLDER_TEST, EXCEL_DATA, PROGRAM_SCRIPT, max_workers=1
    )

    total_time = time.time() - start_time

    report = generate_summary_report(processed_count, errors_count, skipped_count, total_time, EXCEL_DATA)

    if success:
        try:
            new_excel_path = rename_file_with_version_and_time(EXCEL_DATA)
            logger.info(f"💾 Файл результатов переименован: {new_excel_path}")

            if SELECTED_SERVER != 'default':
                logger.info(f"🏁 Тестирование на сервере {SELECTED_SERVER} завершено!")
            else:
                logger.info(f"🏁 Локальное тестирование завершено!")

            logger.info(f"⏱️  Общее время: {total_time:.2f} секунд")
            logger.info(f"📈 Скорость: {report['images_per_minute']:.2f} изображений/мин")

        except Exception as e:
            logger.error(f"❌ Ошибка переименования файла: {e}")
    else:
        logger.error("❌ Тестирование завершено с ошибками!")
        sys.exit(1)


if __name__ == "__main__":
    main()