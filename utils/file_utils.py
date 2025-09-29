import pandas as pd
import logging
from openpyxl import load_workbook
import os

from config import *
from generators.report_generator import apply_excel_styles

logger = logging.getLogger(__name__)


def validate_environment():
    errors = []

    required_paths = {
        'FOLDER_TEST': FOLDER_TEST,
        'EXCEL_DATA': EXCEL_DATA,
    }

    if SELECTED_SERVER == 'default':
        if not PROGRAM_SCRIPT:
            errors.append("Переменная окружения PROGRAM_SCRIPT не определена")
        elif not os.path.exists(PROGRAM_SCRIPT):
            errors.append(f"Путь не существует: PROGRAM_SCRIPT = {PROGRAM_SCRIPT}")
        else:
            required_paths['PROGRAM_SCRIPT'] = PROGRAM_SCRIPT

    for name, path in required_paths.items():
        if not path:
            errors.append(f"Переменная окружения {name} не определена")
        elif not os.path.exists(path):
            errors.append(f"Путь не существует: {name} = {path}")

    if errors:
        for error in errors:
            logger.error(error)
        return False

    if not os.listdir(FOLDER_TEST):
        logger.warning(f"Папка с изображениями пуста: {FOLDER_TEST}")

    return True


def load_excel_data(excel_file):
    try:
        dtype_spec = {
            'Series number (reference)': 'string',
            'Model (reference)': 'string',
            'Rate (reference)': 'string',
            'Inidications (reference)': 'string'
        }

        df = pd.read_excel(excel_file, sheet_name='Image Data', dtype=dtype_spec)
        logger.info(f"Загружен Excel файл: {excel_file}, строк: {len(df)}")

        expected_columns = ['Indications Match', 'Series Match', 'Model Match', 'Rate Match', 'Overall Match']
        for col in expected_columns:
            if col not in df.columns:
                df[col] = ''

        return fix_column_data_types(df)
    except Exception as e:
        logger.error(f"Ошибка загрузки Excel файла: {str(e)}")
        raise


def fix_column_data_types(df):
    if 'Filename' not in df.columns:
        df.insert(0, 'Filename', '')
    type_mapping = {
        'Filename': 'string',
        'Indications': 'string',
        'Series number': 'string',
        'Model': 'string',
        'Rate': 'string',
        'Inidications (reference)': 'string',
        'Series number (reference)': 'string',
        'Model (reference)': 'string',
        'Rate (reference)': 'string',
        'Indications Match': 'int64',
        'Series Match': 'int64',
        'Model Match': 'int64',
        'Rate Match': 'int64',
        'Overall Match': 'int64'
    }

    for col, dtype in type_mapping.items():
        if col in df.columns:
            try:
                if dtype == 'string':
                    df[col] = df[col].astype(str).apply(
                        lambda x: x if pd.isna(x) else str(x).strip() if x != 'nan' else '')
                if dtype == 'int64':
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int64') if x != 'nan' else 0
                else:
                    df[col] = df[col].astype(dtype)
            except Exception as e:
                logger.warning(f"Ошибка преобразования колонки {col} в {dtype}: {e}")
                continue

    return df


def save_excel_progress(df, excel_file, report_data=None):
    try:
        temp_file = excel_file.replace('.xlsx', '_temp.xlsx')

        with pd.ExcelWriter(temp_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Image Data', index=False)

        wb = load_workbook(temp_file)
        apply_excel_styles(wb, excel_file)
        if report_data:
            from generators.summary_report import create_summary_sheet
            create_summary_sheet(wb, report_data)

        wb.save(excel_file)

        if os.path.exists(temp_file):
            os.remove(temp_file)

        logger.info(f"Прогресс сохранен в {excel_file}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения Excel файла: {str(e)}")
        return False


def get_image_files(images_folder):
    return [f for f in os.listdir(images_folder)
            if f.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)]