import pandas as pd
import time
import shutil
import os
from datetime import datetime
import threading
from config import *
from recognition_runner import run_recognition_on_image
from accuracy_calculator import compare_numeric_values, compare_text_values
from utils.file_utils import load_excel_data, get_image_files, save_excel_progress

logger = logging.getLogger(__name__)


class ImageProcessor:
    def __init__(self):
        self.processed_count = 0
        self.errors_count = 0
        self.skipped_count = 0
        self.df_lock = threading.Lock()

    def create_excel_copy(self, original_excel):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            target_dir = os.path.join(current_dir, '..', 'detail')
            os.makedirs(target_dir, exist_ok=True)

            original_name = os.path.basename(original_excel)
            name_without_ext = os.path.splitext(original_name)[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            copy_excel_file = os.path.join(target_dir, f"{name_without_ext}_{timestamp}.xlsx")

            shutil.copy2(original_excel, copy_excel_file)
            logger.info(f"📋 Создана копия Excel:")
            logger.info(f"   Исходный: {original_excel}")
            logger.info(f"   Копия: {copy_excel_file}")

            return copy_excel_file

        except Exception as e:
            logger.error(f"❌ Ошибка создания копии Excel: {str(e)}")
            return original_excel

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
        logger.info(f"🔍 ПОИСК ФАЙЛА {image_file} В МАППИНГЕ:")
        logger.info(f"   Доступные файлы в маппинге: {list(filename_to_index.keys())[:5]}...")

        if image_file not in filename_to_index:
            logger.warning(f"❌ Файл {image_file} не найден в Excel, пропускаем")
            self.skipped_count += 1
            return False

        row_index = filename_to_index[image_file]
        logger.info(f"✅ Найден файл {image_file} в строке {row_index}")

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
        logger.info(f"📊 Начинаем запись в Excel для {image_file}")

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

                logger.info(f"💾 ЗАПИСЫВАЕМ В EXCEL ДЛЯ {image_file}:")
                logger.info(f"   📝 Indications: {meter_reading}")
                logger.info(f"   📝 Series number: {serial_number}")
                logger.info(f"   📝 Model: {model}")
                logger.info(f"   📝 Rate: {rate}")
                logger.info(f"   📝 Overall Confidence: {overall_confidence}")

                with self.df_lock:
                    df.at[row_index, 'Filename'] = image_file
                    df.at[row_index, 'Indications'] = str(meter_reading)
                    df.at[row_index, 'Series number'] = str(serial_number)
                    df.at[row_index, 'Model'] = str(model)
                    df.at[row_index, 'Rate'] = str(rate)
                    df.at[row_index, 'Serial Confidence'] = serial_confidence

                    if 'Recognition Confidence' in df.columns:
                        df['Recognition Confidence'] = df['Recognition Confidence'].astype(object)
                    else:
                        df['Recognition Confidence'] = None
                    df.at[row_index, 'Recognition Confidence'] = recognition_confidences

                    df.at[row_index, 'Overall Confidence'] = overall_confidence
                    df.at[row_index, 'Image Size'] = image_size
                    df.at[row_index, 'Create Date'] = create_date

                    for timing_key, timing_value in timings.items():
                        timing_col = f'Timing {timing_key.title()}'
                        if timing_col not in df.columns:
                            df[timing_col] = ''
                        df.at[row_index, timing_col] = timing_value

                    self.update_match_columns(df, row_index, meter_reading, serial_number,
                                              model, rate, ref_indications, ref_series,
                                              ref_model, ref_rate, overall_confidence)

                    self.processed_count += 1

                logger.info(f"✅ Данные записаны в DataFrame для {image_file}")
                logger.info(f"💾 Вызываем сохранение Excel для {image_file}")
                save_success = save_callback(df)

                if save_success:
                    logger.info(f"✅ Excel файл успешно сохранен для {image_file}")
                else:
                    logger.error(f"❌ Ошибка сохранения Excel для {image_file}")

                if self.processed_count % 5 == 0:
                    logger.info(f"📦 Дополнительное сохранение после {self.processed_count} изображений")
                    save_callback(df)

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
        logger.info(f"🔍 СОЗДАЕМ МАППИНГ ФАЙЛОВ:")
        logger.info(f"   Всего строк в DF: {len(df)}")

        for idx, row in df.iterrows():
            filename = str(row.get('Filename', '')).strip()
            if filename:
                filename_to_index[filename] = idx
                if len(filename_to_index) <= 5:
                    logger.info(f"   📁 {filename} -> строка {idx}")

        logger.info(f"   📊 Всего найдено соответствий: {len(filename_to_index)}")
        return filename_to_index

    def process_images_folder(self, images_folder, excel_file, program_script):
        self.processed_count = self.errors_count = self.skipped_count = 0
        start_time = time.time()

        try:
            copied_excel_file = self.create_excel_copy(excel_file)

            df = load_excel_data(copied_excel_file)
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
                    lambda current_df: save_excel_progress(current_df, copied_excel_file),
                    program_script
                )

                if i % 10 == 0 or i == len(image_files):
                    logger.info(f"📊 Прогресс: {i}/{len(image_files)} обработано")

            success = save_excel_progress(df, copied_excel_file)
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

                logger.info(f"🎯 ПЕРЕДАЕМ ФАЙЛ В generate_summary_report:")
                logger.info(f"   📁 copied_excel_file: {copied_excel_file}")
                logger.info(f"   📁 excel_file (оригинал): {excel_file}")


                from generators.report_generator import generate_summary_report
                generate_summary_report(
                    self.processed_count,
                    self.errors_count,
                    self.skipped_count,
                    total_time,
                    copied_excel_file
                )
            else:
                logger.error("❌ Ошибка при сохранении результатов в Excel")

            return success, self.processed_count, self.errors_count, self.skipped_count

        except Exception as e:
            logger.error(f"💥 Критическая ошибка при обработке папки: {str(e)}")
            return False, self.processed_count, self.errors_count, self.skipped_count


def process_images_folder(images_folder, excel_file, program_script, max_workers=None):
    logger.info(f"🔍 Обработка изображений:")
    logger.info(f"   Папка с изображениями: {images_folder}")
    logger.info(f"   Excel файл: {excel_file}")
    logger.info(f"   Сервер: {SELECTED_SERVER}")

    processor = ImageProcessor()
    return processor.process_images_folder(images_folder, excel_file, program_script)


def get_processing_stats():
    processor = ImageProcessor()
    return {
        'processed': processor.processed_count,
        'errors': processor.errors_count,
        'skipped': processor.skipped_count
    }


def reset_counters():
    processor = ImageProcessor()
    processor.processed_count = processor.errors_count = processor.skipped_count = 0