SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS testing_system
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE testing_system;

CREATE TABLE IF NOT EXISTS test_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_date DATETIME NOT NULL,
    system_version VARCHAR(50) NOT NULL,
    test_system_version VARCHAR(50) NOT NULL,
    total_images INT NOT NULL DEFAULT 0,
    successful_images INT NOT NULL DEFAULT 0,
    error_images INT NOT NULL DEFAULT 0,
    total_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    counter_reading_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    serial_number_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    counter_model_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    tariff_accuracy DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    duration_seconds INT NOT NULL DEFAULT 0,
    comments TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_test_date (test_date),
    INDEX idx_system_version (system_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SHOW TABLES;
DESCRIBE test_results;