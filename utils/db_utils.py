from database.db_manager import db_manager
import logging

logger = logging.getLogger(__name__)


def show_test_history(limit=5):
    results = db_manager.get_test_history(limit)

    if not results:
        logger.info("История тестов пуста")
        return

    logger.info("=" * 100)
    logger.info("ИСТОРИЯ ТЕСТИРОВАНИЙ")
    logger.info("=" * 100)

    for i, test in enumerate(results, 1):
        logger.info(f"{i}. {test['test_date']} - v{test['system_version']}")
        logger.info(f"   Изображений: {test['total_images']} | Успешно: {test['successful_images']}")
        logger.info(f"   Общая точность: {test['total_accuracy']:.1f}%")
        logger.info(f"   Время: {test['duration_seconds']:.0f} сек")
        logger.info("-" * 50)


def get_accuracy_trend():
    results = db_manager.get_test_history(50)  # Последние 50 тестов

    if not results:
        return {}

    trend = {}
    for test in results:
        version = test['system_version']
        if version not in trend:
            trend[version] = {
                'tests': 0,
                'total_accuracy': 0,
                'best_accuracy': 0,
                'worst_accuracy': 100
            }

        trend[version]['tests'] += 1
        trend[version]['total_accuracy'] += test['total_accuracy']

        if test['total_accuracy'] > trend[version]['best_accuracy']:
            trend[version]['best_accuracy'] = test['total_accuracy']
        if test['total_accuracy'] < trend[version]['worst_accuracy']:
            trend[version]['worst_accuracy'] = test['total_accuracy']

    for version in trend:
        trend[version]['avg_accuracy'] = trend[version]['total_accuracy'] / trend[version]['tests']

    return trend