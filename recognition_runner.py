import subprocess
import json
import os
import re
import sys
import logging

from config import TIMEOUT

logger = logging.getLogger(__name__)

def extract_json_from_output(output):
    json_pattern = r'\{.*\}'
    matches = re.findall(json_pattern, output, re.DOTALL)

    if matches:
        for json_str in reversed(matches):
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

    lines = output.split('\n')
    json_start = None
    json_end = None

    for i, line in enumerate(lines):
        if line.strip().startswith('{'):
            json_start = i
            break

    if json_start is not None:
        for i in range(json_start, len(lines)):
            if '}' in lines[i]:
                json_end = i
                break

        if json_end is not None:
            json_str = '\n'.join(lines[json_start:json_end + 1])
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

    return None

def run_recognition_on_image(image_path, task_id, program_script):
    try:
        logger.info(f"Запуск распознавания для: {os.path.basename(image_path)}")
        cmd = [sys.executable, program_script, image_path, task_id]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            encoding='utf-8',
            errors='ignore'
        )

        if result.returncode != 0:
            logger.error(f"Ошибка выполнения для {image_path}: {result.stderr}")
            return create_error_result(result.stderr)

        recognition_result = extract_json_from_output(result.stdout)

        if recognition_result is None:
            logger.error(f"Не удалось извлечь JSON из вывода для {image_path}")
            return create_error_result('JSON not found in output')

        if recognition_result.get('status') == 'failed':
            error_msg = recognition_result.get('error', 'Unknown error')
            logger.error(f"Распознавание не удалось для {image_path}: {error_msg}")
            return create_error_result(error_msg)

        logger.info(f"Успешно обработано: {os.path.basename(image_path)}")
        return recognition_result

    except subprocess.TimeoutExpired:
        logger.error(f"Таймаут при обработке {image_path}")
        return create_error_result('Timeout (120 seconds)')
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке {image_path}: {str(e)}")
        return create_error_result(str(e))

def create_error_result(error_message):
    return {
        'status': 'failed',
        'error': error_message[:200] + "..." if len(error_message) > 200 else error_message,
        'meter_reading': '',
        'serial_number': '',
        'model': '',
        'rate': ''
    }