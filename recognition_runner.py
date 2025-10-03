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
        image_name = os.path.basename(image_path)
        logger.info(f"📤 Отправка изображения на сервер: {image_name}")

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

        logger.info(f"📥 Ответ создания задачи - Статус: {response.status_code}")

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

            logger.info(f"✅ Задача создана, ID: {task_uuid}")

        except json.JSONDecodeError as e:
            error_msg = f"Неверный JSON ответ от сервера при создании задачи: {str(e)}"
            logger.error(error_msg)
            return create_error_result(error_msg)

        # Опрашиваем каждые 5 секунд пока не получим completed
        result_url = f"{server_url}/result?uuid={task_uuid}"
        max_attempts = 60  # максимум 5 минут ожидания
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            logger.info(f"🔄 Опрос результата {attempt}/{max_attempts}...")

            result_response = requests.get(
                result_url,
                headers=headers,
                timeout=TIMEOUT
            )

            logger.info(f"📥 Ответ результата - Статус: {result_response.status_code}")

            if result_response.status_code != 200:
                error_msg = f"Ошибка получения результата: HTTP {result_response.status_code}"
                logger.error(error_msg)
                return create_error_result(error_msg)

            try:
                recognition_result = result_response.json()
                current_status = recognition_result.get('status')

                logger.info(f"📊 Текущий статус задачи: '{current_status}'")

                if current_status == 'completed':
                    # ЛОГИРУЕМ ЧТО ПРИШЛО В ОТВЕТЕ
                    logger.info("=" * 60)
                    logger.info(f"📋 ПОЛНЫЙ ОТВЕТ ОТ СЕРВЕРА ДЛЯ {image_name}:")

                    # Просто печатаем все поля что пришли
                    fields_to_log = [
                        ('status', '📊 Статус'),
                        ('create_date', '📅 Create date'),
                        ('image_size', '🖼️  Image size'),
                        ('meter_reading', '🔢 Meter reading'),
                        ('model', '📱 Model'),
                        ('model_confidence', '✅ Model confidence'),
                        ('rate', '⚡ Rate'),
                        ('serial_number', '🏷️  Serial number'),
                        ('serial_number_confidence', '✅ Serial confidence'),
                        ('recognition_confidences', '🔢 Recognition confidences'),
                        ('overall_confidence', '📈 Overall confidence'),
                        ('timings', '⏱️  Timings')
                    ]

                    for field, description in fields_to_log:
                        value = recognition_result.get(field)
                        logger.info(f"   {description}: {value}")

                    logger.info("=" * 60)
                    logger.info(f"✅ Задача завершена! Возвращаем результат для {image_name}")
                    return recognition_result
                else:
                    logger.info(f"⏳ Статус '{current_status}' - ждем 5 секунд...")
                    time.sleep(5)  # ждем 5 секунд перед следующим опросом

            except json.JSONDecodeError as e:
                error_msg = f"Неверный JSON в результате: {str(e)}"
                logger.error(error_msg)
                logger.error(f"📋 Сырой ответ: {result_response.text}")
                return create_error_result(error_msg)

        # Если вышли по максимальному количеству попыток
        error_msg = f"Превышено время ожидания завершения задачи ({max_attempts * 5} секунд)"
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