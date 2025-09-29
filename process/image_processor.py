import pandas as pd
import time
import concurrent.futures
from threading import Lock
from config import *
from recognition_runner import run_recognition_on_image
from accuracy_calculator import compare_numeric_values, compare_text_values
from utils.file_utils import load_excel_data, get_image_files, save_excel_progress

logger = logging.getLogger(__name__)


class ParallelImageProcessor:
    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        self.processed_count = 0
        self.errors_count = 0
        self.skipped_count = 0
        self.df_lock = Lock()
        self.counter_lock = Lock()

    def process_single_image_wrapper(self, args):
        image_file, image_path, df, filename_to_index, excel_file, program_script = args
        temp_processor = SequentialImageProcessor()
        success = temp_processor.process_single_image(
            image_file, image_path, df, filename_to_index,
            lambda current_df: save_excel_progress(current_df, excel_file),
            program_script
        )

        with self.counter_lock:
            if success:
                self.processed_count += 1
            else:
                self.errors_count += 1

        return success

    def process_images_folder_parallel(self, images_folder, excel_file, program_script):
        self.processed_count = self.errors_count = self.skipped_count = 0
        start_time = time.time()

        try:
            df = load_excel_data(excel_file)
            if df is None:
                logger.error("Не удалось загрузить данные из Excel файла")
                return False, 0, 0, 0

            image_files = get_image_files(images_folder)
            if not image_files:
                logger.error("В указанной папке нет изображений")
                return False, 0, 0, 0

            filename_to_index = self.create_filename_mapping(df)

            logger.info(f"🚀 Запускаем ПАРАЛЛЕЛЬНУЮ обработку с {self.max_workers} workers")
            logger.info(f"📊 Всего изображений для обработки: {len(image_files)}")

            tasks = []
            for image_file in image_files:
                image_path = os.path.join(images_folder, image_file)

                if not os.path.exists(image_path):
                    logger.warning(f"Файл {image_path} не существует, пропускаем")
                    self.skipped_count += 1
                    continue

                if image_file not in filename_to_index:
                    logger.warning(f"Файл {image_file} не найден в Excel, пропускаем")
                    self.skipped_count += 1
                    continue

                tasks.append((image_file, image_path, df, filename_to_index, excel_file, program_script))

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []

                for task_args in tasks:
                    future = executor.submit(self.process_single_image_wrapper, task_args)
                    futures.append(future)

                completed = 0
                total = len(futures)

                for future in concurrent.futures.as_completed(futures):
                    completed += 1
                    if completed % 5 == 0 or completed == total:
                        logger.info(f"📊 Прогресс: {completed}/{total} обработано")

            success = save_excel_progress(df, excel_file)
            total_time = time.time() - start_time

            if success:
                logger.info("=" * 50)
                logger.info(f"✅ Параллельная обработка завершена!")
                logger.info(f"✅ Успешно: {self.processed_count}")
                logger.info(f"❌ Ошибок: {self.errors_count}")
                logger.info(f"⏭️  Пропущено: {self.skipped_count}")
                logger.info(f"⏱️  Общее время: {total_time:.2f} секунд")
                logger.info(f"📈 Скорость: {self.processed_count / max(total_time / 60, 0.01):.2f} изображений/мин")
                logger.info("=" * 50)
            else:
                logger.error("❌ Ошибка при сохранении результатов в Excel")

            return success, self.processed_count, self.errors_count, self.skipped_count

        except Exception as e:
            logger.error(f"💥 Критическая ошибка при параллельной обработке: {str(e)}")
            return False, self.processed_count, self.errors_count, self.skipped_count

    def create_filename_mapping(self, df):
        filename_to_index = {}
        for idx, row in df.iterrows():
            filename = str(row.get('Filename', '')).strip()
            if filename:
                filename_to_index[filename] = idx
        return filename_to_index


class SequentialImageProcessor:
    def __init__(self):
        self.processed_count = 0
        self.errors_count = 0
        self.skipped_count = 0
        self.df_lock = threading.Lock()

    def is_already_processed(self, df, row_index):
        current_indications = str(df.at[row_index, 'Indications']) if pd.notna(df.at[row_index, 'Indications']) else ''
        current_series = str(df.at[row_index, 'Series number']) if pd.notna(df.at[row_index, 'Series number']) else ''
        current_model = str(df.at[row_index, 'Model']) if pd.notna(df.at[row_index, 'Model']) else ''
        current_rate = str(df.at[row_index, 'Rate']) if pd.notna(df.at[row_index, 'Rate']) else ''

        return (current_indications and current_series and current_model and current_rate and
                not current_indications.startswith('ERROR:'))

    def process_meter_reading(self, reading):
        try:
            if isinstance(reading, str):
                reading_clean = reading.strip().replace(' ', '').replace(',', '.')

                if reading_clean.replace('.', '', 1).isdigit():
                    return float(reading_clean)
                elif '?' in reading_clean or not reading_clean:
                    return reading
            elif isinstance(reading, (int, float)):
                return float(reading)

            return reading
        except (ValueError, TypeError) as e:
            logger.warning(f"Ошибка преобразования показаний '{reading}': {e}")
            return reading

    def update_match_columns(self, df, row_index, meter_reading, serial_number, model, rate,
                             ref_indications, ref_series, ref_model, ref_rate, overall_confidence):
        indications_match = compare_numeric_values(meter_reading, ref_indications)
        df.at[row_index, 'Indications Match'] = int(indications_match)


        series_match = compare_text_values(serial_number, ref_series)
        df.at[row_index, 'Series Match'] = int(series_match)

        model_match = compare_text_values(model, ref_model)
        df.at[row_index, 'Model Match'] = int(model_match)

        rate_match = compare_text_values(rate, ref_rate)
        df.at[row_index, 'Rate Match'] = int(rate_match)

        overall_match = all([indications_match, series_match, model_match, rate_match])
        df.at[row_index, 'Overall Match'] = int(overall_match)

        df.at[row_index, 'Overall Confidence Match'] = int(overall_confidence > 0)

    def process_single_image(self, image_file, image_path, df, filename_to_index, save_callback, program_script):
        if image_file not in filename_to_index:
            logger.warning(f"Файл {image_file} не найден в Excel, пропускаем")
            self.skipped_count += 1
            return False

        row_index = filename_to_index[image_file]

        with self.df_lock:
            df.at[row_index, 'Filename'] = image_file

        if self.is_already_processed(df, row_index):
            logger.info(f"Файл {image_file} уже обработан, пропускаем")
            self.skipped_count += 1
            return True

        logger.info(f"Обрабатываем: {image_file}")
        task_id = f"seq_{int(time.time())}_{image_file.replace('.', '_')}"

        result = run_recognition_on_image(image_path, task_id, program_script)

        return self.update_dataframe_with_result(result, df, row_index, image_file, save_callback)

    def update_dataframe_with_result(self, result, df, row_index, image_file, save_callback):

        if result['status'] == 'completed':
            try:
                meter_reading = self.process_meter_reading(result.get('meter_reading', ''))
                serial_number = str(result.get('serial_number', ''))
                model = str(result.get('model', ''))
                rate = str(result.get('rate', ''))

                serial_confidence = result.get('serial_number_confidence', 0.0)
                recognition_confidences = result.get('recognition_confidences', [])
                overall_confidence = result.get('overall_confidence', 0.0)

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

                with self.df_lock:
                    df.at[row_index, 'Indications'] = str(meter_reading)
                    df.at[row_index, 'Series number'] = str(serial_number)
                    df.at[row_index, 'Model'] = str(model)
                    df.at[row_index, 'Rate'] = str(rate)

                    df.at[row_index, 'Serial Confidence'] = serial_confidence
                    df.at[row_index, 'Recognition Confidence'] = str(recognition_confidences)
                    df.at[row_index, 'Overall Confidence'] = overall_confidence

                    for timing_key, timing_value in timings.items():
                        timing_col = f'Timing {timing_key.title()}'
                        if timing_col not in df.columns:
                            df[timing_col] = ''
                        df.at[row_index, timing_col] = timing_value

                    self.update_match_columns(df, row_index, meter_reading, serial_number,
                                              model, rate, ref_indications, ref_series,
                                              ref_model, ref_rate, overall_confidence)

                    self.processed_count += 1

                logger.info(f"✅ Успешно обработано: {image_file}")

                if self.processed_count % 5 == 0:
                    save_callback(df)
                    logger.info(f"💾 Прогресс сохранен после {self.processed_count} изображений")

                return True

            except Exception as e:
                logger.error(f"❌ Ошибка обновления данных для {image_file}: {str(e)}")
                with self.df_lock:
                    df.at[row_index, 'Indications'] = f"ERROR: Data update error - {str(e)}"
                    self.errors_count += 1
                return False
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"❌ Ошибка обработки {image_file}: {error_msg}")
            with self.df_lock:
                df.at[row_index, 'Indications'] = f"ERROR: {error_msg}"
                self.errors_count += 1
            return False

    def create_filename_mapping(self, df):
        filename_to_index = {}
        for idx, row in df.iterrows():
            filename = str(row.get('Filename', '')).strip()
            if filename:
                filename_to_index[filename] = idx
        return filename_to_index

    def process_images_folder_sequential(self, images_folder, excel_file, program_script):
        self.processed_count = self.errors_count = self.skipped_count = 0
        start_time = time.time()

        try:
            df = load_excel_data(excel_file)
            if df is None:
                logger.error("Не удалось загрузить данные из Excel файла")
                return False, 0, 0, 0

            image_files = get_image_files(images_folder)
            if not image_files:
                logger.error("В указанной папке нет изображений")
                return False, 0, 0, 0

            filename_to_index = self.create_filename_mapping(df)

            logger.info(f"🚀 Запускаем ПОСЛЕДОВАТЕЛЬНУЮ обработку")
            logger.info(f"📊 Всего изображений для обработки: {len(image_files)}")

            for i, image_file in enumerate(image_files, 1):
                image_path = os.path.join(images_folder, image_file)

                if not os.path.exists(image_path):
                    logger.warning(f"Файл {image_path} не существует, пропускаем")
                    self.skipped_count += 1
                    continue

                success = self.process_single_image(
                    image_file, image_path, df, filename_to_index,
                    lambda current_df: save_excel_progress(current_df, excel_file),
                    program_script
                )

                if i % 10 == 0 or i == len(image_files):
                    logger.info(f"📊 Прогресс: {i}/{len(image_files)} обработано")

            success = save_excel_progress(df, excel_file)
            total_time = time.time() - start_time

            if success:
                logger.info("=" * 50)
                logger.info(f"✅ Обработка завершена!")
                logger.info(f"✅ Успешно: {self.processed_count}")
                logger.info(f"❌ Ошибок: {self.errors_count}")
                logger.info(f"⏭️  Пропущено: {self.skipped_count}")
                logger.info(f"⏱️  Общее время: {total_time:.2f} секунд")
                logger.info(f"📈 Скорость: {self.processed_count / max(total_time / 60, 0.01):.2f} изображений/мин")
                logger.info("=" * 50)
            else:
                logger.error("❌ Ошибка при сохранении результатов в Excel")

            return success, self.processed_count, self.errors_count, self.skipped_count

        except Exception as e:
            logger.error(f"💥 Критическая ошибка при обработке папки: {str(e)}")
            return False, self.processed_count, self.errors_count, self.skipped_count


def process_images_folder(images_folder, excel_file, program_script, max_workers=None):
    # ОТЛАДКА ДО ВСЕГО
    logger.info(f"🔍 DEBUG IMAGE_PROCESSOR START:")
    logger.info(f"   MAX_WORKERS from config: {MAX_WORKERS}")
    logger.info(f"   max_workers parameter: {max_workers}")
    logger.info(f"   SELECTED_SERVER: {SELECTED_SERVER}")
    logger.info(f"   PROCESSING_MODE: {PROCESSING_MODE}")

    if max_workers is None:
        max_workers = MAX_WORKERS
        logger.info(f"🔍 Используем MAX_WORKERS из config: {max_workers}")
    else:
        logger.info(f"🔍 Используем переданный max_workers: {max_workers}")

    # ОТЛАДОЧНАЯ ИНФОРМАЦИЯ - добавьте эту строку
    logger.info(
        f"🔧 Параметры обработки: MAX_WORKERS={max_workers}, SELECTED_SERVER='{SELECTED_SERVER}', PROCESSING_MODE='{PROCESSING_MODE}'")

    # Условие для параллельной обработки
    use_parallel = (max_workers > 1 and SELECTED_SERVER in ['server1', 'server2'])

    logger.info(
        f"🔍 Условие параллельной обработки: max_workers > 1 = {max_workers > 1}, SERVER in ['server1','server2'] = {SELECTED_SERVER in ['server1', 'server2']}")
    logger.info(f"🔍 use_parallel = {use_parallel}")

    if use_parallel:
        logger.info(f"🚀 Запускаем ПАРАЛЛЕЛЬНУЮ обработку с {max_workers} workers")
        processor = ParallelImageProcessor(max_workers=max_workers)
        return processor.process_images_folder_parallel(images_folder, excel_file, program_script)
    else:
        reason = "неизвестная причина"
        if max_workers <= 1:
            reason = f"MAX_WORKERS={max_workers} (требуется > 1)"
        elif SELECTED_SERVER not in ['server1', 'server2']:
            reason = f"SELECTED_SERVER={SELECTED_SERVER} (только server1/server2)"
        else:
            reason = "другая причина"

        logger.info(f"💻 Используем последовательную обработку: {reason}")
        processor = SequentialImageProcessor()
        return processor.process_images_folder_sequential(images_folder, excel_file, program_script)


def get_processing_stats():
    processor = SequentialImageProcessor()
    return {
        'processed': processor.processed_count,
        'errors': processor.errors_count,
        'skipped': processor.skipped_count
    }


def reset_counters():
    processor = SequentialImageProcessor()
    processor.processed_count = processor.errors_count = processor.skipped_count = 0