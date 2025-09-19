import concurrent.futures
import pandas as pd
import time
import logging

from config import *
from recognition_runner import run_recognition_on_image
from accuracy_calculator import compare_values, compare_numeric_values, compare_text_values
from utils.file_utils import load_excel_data, get_image_files, save_excel_progress

logger = logging.getLogger(__name__)

processed_count = 0
errors_count = 0
skipped_count = 0
df_lock = threading.Lock()


def process_single_image(args):
    """Обработка одного изображения в отдельном потоке"""
    global processed_count, errors_count, skipped_count

    image_file, image_path, df, filename_to_index, save_callback, program_script = args
    thread_id = threading.get_ident()

    if image_file not in filename_to_index:
        logger.warning(f"[Thread {thread_id}] Файл {image_file} не найден в Excel, пропускаем")
        with df_lock:
            skipped_count += 1
        return None

    row_index = filename_to_index[image_file]

    with df_lock:
        df.at[row_index, 'Filename'] = image_file

    if is_already_processed(df, row_index):
        logger.info(f"[Thread {thread_id}] Файл {image_file} уже обработан, пропускаем")
        with df_lock:
            skipped_count += 1
        return None

    logger.info(f"[Thread {thread_id}] Обрабатываем: {image_file}")
    task_id = f"test_{int(time.time())}_{image_file.replace('.', '_')}_{thread_id}"

    result = run_recognition_on_image(image_path, task_id, program_script)
    return update_dataframe_with_result(result, df, row_index, image_file, thread_id, save_callback)


def is_already_processed(df, row_index):
    """Проверяет, был ли файл уже обработан"""
    current_indications = str(df.at[row_index, 'Indications']) if pd.notna(df.at[row_index, 'Indications']) else ''
    current_series = str(df.at[row_index, 'Series number']) if pd.notna(df.at[row_index, 'Series number']) else ''
    current_model = str(df.at[row_index, 'Model']) if pd.notna(df.at[row_index, 'Model']) else ''
    current_rate = str(df.at[row_index, 'Rate']) if pd.notna(df.at[row_index, 'Rate']) else ''

    return (current_indications and current_series and current_model and current_rate and
            not current_indications.startswith('ERROR:'))


def update_dataframe_with_result(result, df, row_index, image_file, thread_id, save_callback):
    """Обновляет DataFrame с результатами распознавания"""
    global processed_count, errors_count

    if result['status'] == 'completed':
        try:
            meter_reading = process_meter_reading(result.get('meter_reading', ''))
            serial_number = str(result.get('serial_number', ''))
            model = str(result.get('model', ''))
            rate = str(result.get('rate', ''))

            # Получаем уверенности
            serial_confidence = result.get('serial_number_confidence', 0.0)
            recognition_confidences = result.get('recognition_confidences', [])
            overall_confidence = result.get('overall_confidence', 0.0)

            # Получаем временные метки
            timings = result.get('timings', {})
            image_size = result.get('image_size', '')
            create_date = result.get('create_date', '')

            ref_indications = str(df.at[row_index, 'Inidications (reference)']) if pd.notna(
                df.at[row_index, 'Inidications (reference)']) else ''
            ref_series = str(df.at[row_index, 'Series number (reference)']) if pd.notna(
                df.at[row_index, 'Series number (reference)']) else ''
            ref_model = str(df.at[row_index, 'Model (reference)']) if pd.notna(
                df.at[row_index, 'Model (reference)']) else ''
            ref_rate = str(df.at[row_index, 'Rate (reference)']) if pd.notna(
                df.at[row_index, 'Rate (reference)']) else ''

            with df_lock:
                # Основные данные
                df.at[row_index, 'Indications'] = str(meter_reading)
                df.at[row_index, 'Series number'] = str(serial_number)
                df.at[row_index, 'Model'] = str(model)
                df.at[row_index, 'Rate'] = str(rate)

                # Уверенности
                df.at[row_index, 'Serial Confidence'] = serial_confidence
                df.at[row_index, 'Recognition Confidence'] = str(recognition_confidences)
                df.at[row_index, 'Overall Confidence'] = overall_confidence


                # Временные метки
                for timing_key, timing_value in timings.items():
                    timing_col = f'Timing {timing_key.title()}'
                    if timing_col not in df.columns:
                        df[timing_col] = ''
                    df.at[row_index, timing_col] = timing_value

                update_match_columns(df, row_index, meter_reading, serial_number,
                                     model, rate, ref_indications, ref_series,
                                     ref_model, ref_rate, overall_confidence)

                processed_count += 1

            logger.info(f"[Thread {thread_id}] Успешно обновлены данные для {image_file}")

            if processed_count % 5 == 0:
                save_callback(df)

            return True

        except Exception as e:
            logger.error(f"[Thread {thread_id}] Ошибка обновления данных для {image_file}: {str(e)}")
            with df_lock:
                df.at[row_index, 'Indications'] = f"ERROR: Data update error - {str(e)}"
                errors_count += 1
            return False
    else:
        error_msg = result.get('error', 'Unknown error')
        logger.error(f"[Thread {thread_id}] Ошибка обработки {image_file}: {error_msg}")
        with df_lock:
            df.at[row_index, 'Indications'] = f"ERROR: {error_msg}"
            errors_count += 1
        return False


def process_meter_reading(reading):
    """Обрабатывает показания счетчика, преобразуя в числовой формат если возможно"""
    try:
        if isinstance(reading, str):
            # Убираем лишние символы и пробелы
            reading_clean = reading.strip().replace(' ', '').replace(',', '.')

            # Проверяем, является ли числом
            if reading_clean.replace('.', '', 1).isdigit():
                return float(reading_clean)
            elif '?' in reading_clean or not reading_clean:
                return reading  # Оставляем как есть для нераспознанных значений
        elif isinstance(reading, (int, float)):
            return float(reading)

        return reading
    except (ValueError, TypeError) as e:
        logger.warning(f"Ошибка преобразования показаний '{reading}': {e}")
        return reading


def update_match_columns(df, row_index, meter_reading, serial_number, model, rate,
                         ref_indications, ref_series, ref_model, ref_rate, overall_confidence):
    """Обновляет колонки совпадения с эталонными значениями"""

    # Сравнение показаний (числовое сравнение)
    indications_match = compare_numeric_values(meter_reading, ref_indications)
    df.at[row_index, 'Indications Match'] = int(indications_match)

    # Сравнение серийных номеров (текстовое сравнение)
    series_match = compare_text_values(serial_number, ref_series)
    df.at[row_index, 'Series Match'] = int(series_match)

    # Сравнение моделей (текстовое сравнение)
    model_match = compare_text_values(model, ref_model)
    df.at[row_index, 'Model Match'] = int(model_match)

    # Сравнение тарифов (текстовое сравнение)
    rate_match = compare_text_values(rate, ref_rate)
    df.at[row_index, 'Rate Match'] = int(rate_match)

    # Общее совпадение (все поля должны совпадать)
    overall_match = all([indications_match, series_match, model_match, rate_match])
    df.at[row_index, 'Overall Match'] = int(overall_match)

    df.at[row_index, 'Overall Confidence Match'] = int(overall_confidence > 0)


def process_images_folder(images_folder, excel_file, program_script, max_workers=4):
    """Основная функция обработки папки с изображениями"""
    global processed_count, errors_count, skipped_count
    processed_count = errors_count = skipped_count = 0

    start_time = time.time()

    try:
        # Загрузка данных из Excel
        df = load_excel_data(excel_file)
        if df is None:
            logger.error("Не удалось загрузить данные из Excel файла")
            return False, 0, 0, 0

        # Получение списка изображений
        image_files = get_image_files(images_folder)
        if not image_files:
            logger.error("В указанной папке нет изображений")
            return False, 0, 0, 0

        # Создание mapping между именами файлов и индексами строк
        filename_to_index = create_filename_mapping(df)

        # Создание задач для обработки
        tasks = create_processing_tasks(image_files, images_folder, df, filename_to_index,
                                        lambda current_df: save_excel_progress(current_df, excel_file),
                                        program_script)

        logger.info(f"Запускаем многопоточную обработку с {max_workers} потоками")
        logger.info(f"Всего изображений для обработки: {len(tasks)}")

        # Многопоточная обработка
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_single_image, tasks))

        # Финализация - сохранение результатов
        success = save_excel_progress(df, excel_file)
        total_time = time.time() - start_time

        if success:
            logger.info(
                f"Обработка завершена. Успешно: {processed_count}, Ошибок: {errors_count}, Пропущено: {skipped_count}")
            logger.info(f"Общее время обработки: {total_time:.2f} секунд")
        else:
            logger.error("Ошибка при сохранении результатов в Excel")

        return success, processed_count, errors_count, skipped_count

    except Exception as e:
        logger.error(f"Критическая ошибка при обработке папки: {str(e)}")
        return False, processed_count, errors_count, skipped_count


def create_filename_mapping(df):
    """Создает mapping между именами файлов и индексами строк в DataFrame"""
    filename_to_index = {}
    for idx, row in df.iterrows():
        filename = str(row.get('Filename', '')).strip()
        if filename:  # Пропускаем пустые имена
            filename_to_index[filename] = idx
    return filename_to_index


def create_processing_tasks(image_files, images_folder, df, filename_to_index, save_callback, program_script):
    """Создает список задач для обработки изображений"""
    tasks = []
    for image_file in image_files:
        image_path = os.path.join(images_folder, image_file)
        if os.path.exists(image_path):
            tasks.append((
                image_file,
                image_path,
                df,
                filename_to_index,
                save_callback,
                program_script
            ))
        else:
            logger.warning(f"Файл {image_path} не существует, пропускаем")
    return tasks


def get_processing_stats():
    return {
        'processed': processed_count,
        'errors': errors_count,
        'skipped': skipped_count
    }


def reset_counters():
    """Сбрасывает счетчики обработки"""
    global processed_count, errors_count, skipped_count
    processed_count = errors_count = skipped_count = 0