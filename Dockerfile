FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglx0 \
    libgl1-mesa-dev \
    git \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY requirements_docker.txt ./requirements.txt

RUN mkdir -p /app/uploads /app/data /app/outputs /app/demo /app/testing_sets/test_1 \
    && chown -R appuser:appuser /app

RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir \
    numpy==2.0.2 \
    pillow==11.1.0 \
    requests==2.32.3 \
    flask==3.1.0

RUN pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir tensorflow==2.18.0

RUN pip install --no-cache-dir -r requirements.txt

# КОПИРУЕМ ИСХОДНЫЙ КОД
COPY . .

# КОПИРУЕМ ТЕСТОВЫЕ ДАННЫЕ ИЗ ПАПКИ ПРОЕКТА (относительные пути!)
COPY ./demo/Тестирование_1.xlsx /app/demo/
COPY ./testing_sets/test_1/ /app/testing_sets/test_1/

# ПРОВЕРКА ЧТО ФАЙЛЫ СКОПИРОВАЛИСЬ
RUN echo "=== Проверка файлов ===" && \
    echo "Excel файл:" && ls -la /app/demo/ && \
    echo "Изображения:" && find /app/testing_sets/test_1/ -type f | head -5 && \
    echo "Всего файлов: $(find /app/testing_sets/test_1/ -type f | wc -l)"

RUN chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TF_CPP_MIN_LOG_LEVEL=3

CMD ["python", "main.py"]