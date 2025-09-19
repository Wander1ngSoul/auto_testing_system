import os.path
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
    logger.info("ЗАПУСК АВТОМАТИЗИРОВАННОГО ТЕСТИРОВАНИЯ СИСТЕМЫ РАСПОЗНАВАНИЯ")
    logger.info("=" * 60)

    if not validate_environment():
        logger.error("Проверка окружения не пройдена. Завершение работы.")
        sys.exit(1)

    logger.info(f"Папка с изображениями: {FOLDER_TEST}")
    logger.info(f"Excel файл: {EXCEL_DATA}")
    logger.info(f"Программа распознавания: {PROGRAM_SCRIPT}")

    cpu_count = os.cpu_count() or 4
    max_workers = min(cpu_count * 2, 8)
    logger.info(f"Используем {max_workers} потоков для обработки")

    start_time = time.time()

    success, processed_count, errors_count, skipped_count = process_images_folder(
        FOLDER_TEST, EXCEL_DATA, PROGRAM_SCRIPT, max_workers=max_workers
    )
    total_time = time.time() - start_time

    report = generate_summary_report(processed_count, errors_count, skipped_count, total_time, EXCEL_DATA)

    if success:
        try:
            new_excel_path = rename_file_with_version_and_time(EXCEL_DATA)
            logger.info(f"Файл результатов переименован: {new_excel_path}")
        except Exception as e:
            logger.error(f"Ошибка переименования файла: {e}")
    else:
        logger.error("Тестирование завершено с ошибками!")
        sys.exit(1)


if __name__ == "__main__":
    main()