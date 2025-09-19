import pandas as pd


def compare_values(recognized, reference):
    if pd.isna(recognized) or pd.isna(reference):
        return False

    recognized_str = str(recognized).strip()
    reference_str = str(reference).strip()

    try:
        recognized_num = float(recognized_str.replace(',', '.'))
        reference_num = float(reference_str.replace(',', '.'))
        return abs(recognized_num - reference_num) < 0.001
    except (ValueError, TypeError):
        pass
    return recognized_str == reference_str


def is_numeric_value(value):
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return value.replace('.', '').replace(',', '').isdigit()
    return False


def compare_numeric_values(recognized, reference):
    try:
        recognized_clean = str(recognized).replace(',', '.').strip()
        reference_clean = str(reference).replace(',', '.').strip()
        return abs(float(recognized_clean) - float(reference_clean)) < 0.1
    except (ValueError, TypeError):
        return False


def compare_text_values(recognized, reference):
    recognized_str = str(recognized).strip().lower()
    reference_str = str(reference).strip().lower()

    return normalize_text(recognized_str) == normalize_text(reference_str)


def normalize_text(text):
    replacements = {
        ' ': '', '-': '', '_': '',
        'х': 'x', 'Х': 'X',
        'с': 'c', 'С': 'C',
        'о': 'o', 'О': 'O'
    }

    normalized = text
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    return normalized


def calculate_accuracy_stats(df):
    total_tests = len(df)

    indications_correct = int(df['Indications Match'].sum())
    series_correct = int(df['Series Match'].sum())
    model_correct = int(df['Model Match'].sum())
    rate_correct = int(df['Rate Match'].sum())
    overall_correct = int(df['Overall Match'].sum())

    if 'Overall Confidence Match' in df.columns:
        overall_conf_correct = int(df['Overall Confidence Match'].sum())
    else:
        overall_conf_correct = 0


    def calculate_percentage(correct, total):
        return float((correct / total) * 100 if total > 0 else 0)

    return {
        'total_tests': int(total_tests),
        'indications': {
            'correct': indications_correct,
            'accuracy': calculate_percentage(indications_correct, total_tests)
        },
        'series': {
            'correct': series_correct,
            'accuracy': calculate_percentage(series_correct, total_tests)
        },
        'model': {
            'correct': model_correct,
            'accuracy': calculate_percentage(model_correct, total_tests)
        },
        'rate': {
            'correct': rate_correct,
            'accuracy': calculate_percentage(rate_correct, total_tests)
        },
        'overall': {
            'correct': overall_correct,
            'accuracy': calculate_percentage(overall_correct, total_tests)
        },
        'overall_confidence': {
            'correct': overall_conf_correct,
            'accuracy': calculate_percentage(overall_conf_correct, total_tests)
        }
    }