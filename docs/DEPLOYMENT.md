# Deployment

## Варианты

1. **Docker Compose** — один сервер (быстрый старт, dev/staging).
2. **Kubernetes** — прод, автоскейл, отдельные GPU-ноды.
3. **GitHub-цикл** (рекомендуемый способ правок): код в приватном репо, на сервере
   `git pull` + `docker compose up -d --build`; правки промтов применяются без
   рестарта через `/admin/modes/reload`. Подробно — [GITHUB.md](GITHUB.md).

---

## 1. Docker Compose

```bash
cp .env.example .env          # выставить секреты и провайдеры
docker compose up --build -d  # postgres, redis, migrate (alembic), api, worker
docker compose exec api python -m scripts.create_api_key "Site" --callback https://site/cb
```

Со стеком наблюдаемости:
```bash
docker compose -f docker-compose.yml -f deploy/monitoring/docker-compose.monitoring.yml up -d
# Prometheus :9090, Grafana :3000 (дашборд "AI Generation API")
```

GPU: на хосте с NVIDIA установить nvidia-container-toolkit, в `docker-compose.yml`
раскомментировать блок `deploy.resources.devices` у `worker` и сервис `comfyui`,
выставить `GENERATION_PROVIDER=comfyui`.

---

## 2. Kubernetes

Порядок применения:
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
# секрет: НЕ из примера в проде — создать из значений/Vault/SealedSecrets
kubectl apply -f k8s/secret.example.yaml

kubectl apply -f k8s/migrate-job.yaml          # дождаться Completed
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/hpa-api.yaml
kubectl apply -f k8s/ingress.yaml
# масштабирование воркеров по очереди (нужен установленный KEDA):
kubectl apply -f k8s/keda-scaledobject.yaml
```

Перед этим: собрать и запушить образ (CI `docker-publish.yml`) и заменить
`ghcr.io/OWNER/...` в манифестах на свой образ.

### GPU-ноды
- Установить NVIDIA device plugin в кластере.
- Воркеры запрашивают `nvidia.com/gpu: 1`; повесить на GPU-пул через
  `nodeSelector`/`tolerations`.
- API держать на обычных (CPU) нодах.

### Масштабирование
- **API** — HPA по CPU (`hpa-api.yaml`), stateless.
- **Worker** — KEDA по длине очереди Redis (`keda-scaledobject.yaml`),
  `maxReplicaCount` ≤ числу доступных GPU.

---

## Миграции БД

```bash
alembic upgrade head                         # применить
alembic revision --autogenerate -m "msg"     # новая миграция после правки моделей
```

В Compose это делает сервис `migrate`, в K8s — `migrate-job.yaml`.

---

## Наблюдаемость

- API отдаёт `/metrics`; воркер поднимает свой `/metrics` на порту `9100`.
- GPU-метрики собирает **dcgm-exporter** на GPU-нодах (`gpu_usage`, `gpu_memory`).
- Алерты — `deploy/monitoring/alert_rules.yml`.

## Безопасность прод
- Сузить CORS `allow_origins` до доменов источников.
- Сменить `WEBHOOK_SIGNING_SECRET`, `INTERNAL_JWT_SECRET`.
- Секреты — через Vault/SealedSecrets, не в репозитории.
- HTTPS — cert-manager + Ingress TLS.
