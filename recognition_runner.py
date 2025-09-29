import subprocess
import json
import os
import re
import sys
import logging
import requests
import time
from config import TIMEOUT, SERVERS, SELECTED_SERVER, AUTHORIZED_TOKEN

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


def run_recognition_on_image_server(image_path, task_id, server_url):
    try:
        logger.info(f"📤 Отправка изображения на сервер: {os.path.basename(image_path)}")

        headers = {
            'Authorization': f'Bearer {AUTHORIZED_TOKEN}',
            'X-API-Key': AUTHORIZED_TOKEN
        }

        create_task_url = f"{server_url}/tasks"
        logger.info(f"🆕 Создаем задачу")

        with open(image_path, 'rb') as image_file:
            files = {'image': image_file}

            response = requests.post(
                create_task_url,
                files=files,
                headers=headers,
                timeout=TIMEOUT
            )

        if response.status_code != 200:
            error_msg = f"Ошибка создания задачи: HTTP {response.status_code} - {response.text}"
            logger.error(error_msg)
            return create_error_result(error_msg)

        try:
            task_data = response.json()
            task_uuid = task_data.get('task_id')
            if not task_uuid:
                error_msg = "Не получен task_id от сервера"
                logger.error(error_msg)
                return create_error_result(error_msg)

            logger.info(f"✅ Задача создана, ID: {task_uuid[:8]}...")

            wait_time = task_data.get('estimated_wait_time', 20)
            logger.info(f"⏳ Ожидаем {wait_time} секунд...")

        except json.JSONDecodeError:
            error_msg = "Неверный JSON ответ от сервера при создании задачи"
            logger.error(error_msg)
            return create_error_result(error_msg)

        time.sleep(wait_time)

        result_url = f"{server_url}/result?uuid={task_uuid}"
        logger.info(f"📥 Запрашиваем результат...")

        result_response = requests.get(
            result_url,
            headers=headers,
            timeout=TIMEOUT
        )

        if result_response.status_code != 200:
            error_msg = f"Ошибка получения результата: HTTP {result_response.status_code}"
            logger.error(error_msg)

            if result_response.status_code == 404 or "not ready" in result_response.text.lower():
                logger.info("🔄 Результат не готов, ждем еще 10 секунд...")
                time.sleep(10)

                result_response = requests.get(
                    result_url,
                    headers=headers,
                    timeout=TIMEOUT
                )

                if result_response.status_code != 200:
                    error_msg = f"Повторная ошибка получения результата: HTTP {result_response.status_code}"
                    logger.error(error_msg)
                    return create_error_result(error_msg)
            else:
                return create_error_result(error_msg)

        try:
            recognition_result = result_response.json()

            if not isinstance(recognition_result, dict):
                error_msg = "Некорректный формат результата"
                logger.error(error_msg)
                return create_error_result(error_msg)

            if 'overall_confidence' not in recognition_result:
                serial_conf = recognition_result.get('serial_number_confidence', 0.0)
                digit_confs = recognition_result.get('recognition_confidences', [])

                overall_conf = serial_conf
                if digit_confs:
                    product = 1.0
                    for conf in digit_confs:
                        product *= conf
                    overall_conf = round(serial_conf * product, 4)

                recognition_result['overall_confidence'] = overall_conf

            recognition_result['status'] = 'completed'

            logger.info(f"✅ Успешно обработано: {os.path.basename(image_path)}")
            return recognition_result

        except json.JSONDecodeError:
            error_msg = "Неверный JSON в результате"
            logger.error(error_msg)
            return create_error_result(error_msg)

    except requests.exceptions.Timeout:
        logger.error(f"⏰ Таймаут при обработке {os.path.basename(image_path)}")
        return create_error_result('Server timeout')
    except Exception as e:
        logger.error(f"💥 Ошибка связи с сервером для {os.path.basename(image_path)}: {str(e)}")
        return create_error_result(str(e))


def run_recognition_on_image_local(image_path, task_id, program_script):
    try:
        logger.info(f"Локальный запуск распознавания для: {os.path.basename(image_path)}")
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
        if 'overall_confidence' not in recognition_result:
            serial_conf = recognition_result.get('serial_number_confidence', 0.0)
            digit_confs = recognition_result.get('recognition_confidences', [])

            def calculate_overall(serial_conf, digit_confs):
                if not digit_confs:
                    return round(serial_conf, 4)

                product = 1.0
                for conf in digit_confs:
                    product *= conf

                return round(serial_conf * product, 4)

            recognition_result['overall_confidence'] = calculate_overall(serial_conf, digit_confs)

        logger.info(f"Успешно обработано локально: {os.path.basename(image_path)}")
        return recognition_result

    except subprocess.TimeoutExpired:
        logger.error(f"Таймаут при обработке {image_path}")
        return create_error_result('Timeout (120 seconds)')
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке {image_path}: {str(e)}")
        return create_error_result(str(e))


def run_recognition_on_image(image_path, task_id, program_script):
    if SELECTED_SERVER == 'default':
        return run_recognition_on_image_local(image_path, task_id, program_script)
    else:
        server_url = SERVERS.get(SELECTED_SERVER)
        if server_url:
            return run_recognition_on_image_server(image_path, task_id, server_url)
        else:
            logger.error(f"Неизвестный сервер: {SELECTED_SERVER}")
            return create_error_result(f"Unknown server: {SELECTED_SERVER}")


def create_error_result(error_message):
    return {
        'status': 'failed',
        'error': error_message[:200] + "..." if len(error_message) > 200 else error_message,
        'meter_reading': '',
        'serial_number': '',
        'model': '',
        'rate': '',
        'serial_number_confidence': 0.0,
        'recognition_confidences': [],
        'overall_confidence': 0.0
    }