import concurrent.futures
import pandas as pd
import time
import logging

from config import *
from recognition_runner import run_recognition_on_image
from accuracy_calculator import compare_values
from utils.file_utils import load_excel_data, get_image_files, save_excel_progress

logger = logging.getLogger(__name__)


def process_single_image(args):
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
    current_indications = str(df.at[row_index, 'Indications']) if pd.notna(df.at[row_index, 'Indications']) else ''
    current_series = str(df.at[row_index, 'Series number']) if pd.notna(df.at[row_index, 'Series number']) else ''
    current_model = str(df.at[row_index, 'Model']) if pd.notna(df.at[row_index, 'Model']) else ''
    current_rate = str(df.at[row_index, 'Rate']) if pd.notna(df.at[row_index, 'Rate']) else ''

    return (current_indications and current_series and current_model and current_rate and
            not current_indications.startswith('ERROR:'))


def update_dataframe_with_result(result, df, row_index, image_file, thread_id, save_callback):
    global processed_count, errors_count

    if result['status'] == 'completed':
        try:
            meter_reading = process_meter_reading(result.get('meter_reading', ''))
            serial_number = str(result.get('serial_number', ''))
            model = str(result.get('model', ''))
            rate = str(result.get('rate', ''))
            preprocessing_results = result.get('preprocessing_results', {})

            ref_indications = str(df.at[row_index, 'Inidications (reference)']) if pd.notna(
                df.at[row_index, 'Inidications (reference)']) else ''
            ref_series = str(df.at[row_index, 'Series number (reference)']) if pd.notna(
                df.at[row_index, 'Series number (reference)']) else ''
            ref_model = str(df.at[row_index, 'Model (reference)']) if pd.notna(
                df.at[row_index, 'Model (reference)']) else ''
            ref_rate = str(df.at[row_index, 'Rate (reference)']) if pd.notna(
                df.at[row_index, 'Rate (reference)']) else ''

            with df_lock:
                df.at[row_index, 'Indications'] = str(meter_reading)
                df.at[row_index, 'Series number'] = str(serial_number)
                df.at[row_index, 'Model'] = str(model)
                df.at[row_index, 'Rate'] = str(rate)

                for key, value in preprocessing_results.items():
                    if key not in df.columns:
                        df[key] = ''
                    df.at[row_index, key] = str(value)

                update_match_columns(df, row_index, meter_reading, serial_number,
                                     model, rate, ref_indications, ref_series,
                                     ref_model, ref_rate)

                processed_count += 1

            logger.info(f"[Thread {thread_id}] Успешно обновлены данные для {image_file}")

            if processed_count % 5 == 0:
                save_callback(df)

            return True

        except Exception as e:
            logger.error(f"[Thread {thread_id}] Ошибка обновления данных для {image_file}: {str(e)}")
            with df_lock:
                df.at[row_index, 'Indications'] = "ERROR: Data update error"
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
    try:
        if isinstance(reading, str) and reading.replace(',', '').replace('.', '').isdigit():
            return float(reading.replace(',', '.'))
        elif isinstance(reading, (int, float)):
            return float(reading)
        return reading
    except (ValueError, TypeError):
        return reading


def update_match_columns(df, row_index, meter_reading, serial_number, model, rate,
                         ref_indications, ref_series, ref_model, ref_rate):
    df.at[row_index, 'Indications Match'] = int(compare_values(meter_reading, ref_indications))
    df.at[row_index, 'Series Match'] = int(compare_values(serial_number, ref_series))
    df.at[row_index, 'Model Match'] = int(compare_values(model, ref_model))
    df.at[row_index, 'Rate Match'] = int(compare_values(rate, ref_rate))

    overall_match = all([
        df.at[row_index, 'Indications Match'] == 1,
        df.at[row_index, 'Series Match'] == 1,
        df.at[row_index, 'Model Match'] == 1,
        df.at[row_index, 'Rate Match'] == 1
    ])
    df.at[row_index, 'Overall Match'] = int(overall_match)


def process_images_folder(images_folder, excel_file, program_script, max_workers=4):
    global processed_count, errors_count, skipped_count
    processed_count = errors_count = skipped_count = 0

    df = load_excel_data(excel_file)
    image_files = get_image_files(images_folder)

    if not image_files:
        logger.error("В указанной папке нет изображений")
        return False, 0, 0

    filename_to_index = create_filename_mapping(df)

    tasks = create_processing_tasks(image_files, images_folder, df, filename_to_index,
                                    lambda current_df: save_excel_progress(current_df, excel_file),
                                    program_script)

    logger.info(f"Запускаем многопоточную обработку с {max_workers} потоками")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_image, tasks))

    success = save_excel_progress(df, excel_file)
    return success, processed_count, errors_count


def create_filename_mapping(df):
    return {str(row['Filename']).strip(): idx for idx, row in df.iterrows()}


def create_processing_tasks(image_files, images_folder, df, filename_to_index, save_callback, program_script):
    return [
        (image_file, os.path.join(images_folder, image_file), df,
         filename_to_index, save_callback, program_script)
        for image_file in image_files
    ]