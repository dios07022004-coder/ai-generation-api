"""Метрики Prometheus. Отдаются на /metrics.

GPU-метрики (gpu_usage/gpu_memory) собирает отдельный экспортер на GPU-сервере
(например, nvidia-dcgm-exporter), а не этот API-процесс — здесь метрики приложения.
"""
from prometheus_client import Counter, Gauge, Histogram

requests_total = Counter(
    "api_requests_total", "Всего HTTP-запросов", ["method", "path", "status"]
)
tasks_total = Counter(
    "tasks_total", "Создано задач", ["task_type", "status"]
)
generation_seconds = Histogram(
    "generation_seconds", "Время генерации", ["task_type"],
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300, 600),
)
queue_size = Gauge("queue_size", "Размер очереди задач")
errors_total = Counter("errors_total", "Всего ошибок", ["where"])
