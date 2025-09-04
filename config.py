import threading
from datetime import datetime
from dotenv import load_dotenv
from openpyxl.styles import PatternFill, Alignment, Font, Border, Side

load_dotenv()

import subprocess
import os

MAIN_REPO_PATH = os.getenv('MAIN_REPO_PATH')

import threading
from datetime import datetime
from dotenv import load_dotenv
from openpyxl.styles import PatternFill, Alignment, Font, Border, Side
import subprocess
import os

load_dotenv()

# Добавьте путь к основному репозиторию в .env или здесь
MAIN_REPO_PATH = os.getenv('MAIN_REPO_PATH', 'D:/path/to/your/main/project')

def get_git_version():
    try:
        # Указываем путь к другому репозиторию через --git-dir и --work-tree
        version = subprocess.check_output(
            ['git', '--git-dir', os.path.join(MAIN_REPO_PATH, '.git'),
             '--work-tree', MAIN_REPO_PATH, 'describe', '--tags', '--abbrev=0'],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip().replace('v', '')
        return version
    except:
        try:
            commit_hash = subprocess.check_output(
                ['git', '--git-dir', os.path.join(MAIN_REPO_PATH, '.git'),
                 '--work-tree', MAIN_REPO_PATH, 'rev-parse', '--short', 'HEAD'],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
            return f"dev-{commit_hash}"
        except:
            return "unknown"


def rename_file_with_version_and_time(original_path):
    if not os.path.exists(original_path):
        return original_path

    directory = os.path.dirname(original_path)
    filename = os.path.basename(original_path)
    name, ext = os.path.splitext(filename)

    version = get_git_version()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    new_filename = f"{name}_v{version}_{timestamp}{ext}"
    new_path = os.path.join(directory, new_filename)

    os.rename(original_path, new_path)
    return new_path


APP_VERSION = get_git_version()
FOLDER_TEST = os.getenv('FOLDER_TEST')
EXCEL_DATA = os.getenv('EXCEL_DATA')
PROGRAM_SCRIPT = os.getenv('PROGRAM_SCRIPT')

processed_count = 0
errors_count = 0
skipped_count = 0

df_lock = threading.Lock()

GREEN_FILL = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
RED_FILL = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
BLUE_FILL = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
CENTER_ALIGNMENT = Alignment(horizontal='center', vertical='center')
BOLD_FONT = Font(bold=True)

THIN_BORDER = Side(border_style="thin", color="000000")
THICK_BORDER = Side(border_style="thick", color="000000")
HEADER_FILL = BLUE_FILL

TIMEOUT = 120
SUPPORTED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')