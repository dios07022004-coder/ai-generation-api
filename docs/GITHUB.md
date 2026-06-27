# Деплой и правки через GitHub (бесплатный план)

Удобный цикл: правишь код/промты у себя → пушишь в GitHub → на сервере
`git pull` + перезапуск. Подходит для бесплатного плана GitHub.

---

## 1. Что важно на бесплатном плане
- **Приватные репозитории — бесплатно** (без лимита). Держи репозиторий
  **приватным** (там вся логика сервиса).
- **GitHub Actions**: ~2000 бесплатных минут/мес для приватных репо. Наши CI
  (`.github/workflows/ci.yml`, `docker-publish.yml`) их расходуют — если экономишь
  минуты, можно временно отключить Actions (Settings → Actions → Disable) и
  собирать образ прямо на сервере.
- **СЕКРЕТЫ НЕ КОММИТЯТСЯ.** `.env` уже в `.gitignore`. В репозиторий идёт только
  `.env.example` с заглушками. Ключи/пароли — лежат на сервере в `.env`, не в git.

---

## 2. Первая загрузка (репозиторий уже инициализирован)

Локальный коммит уже сделан (ветка `main`). Осталось создать репо на GitHub и
запушить. Два способа:

### Способ A — через сайт GitHub (без доп. инструментов)
1. github.com → **New repository** → имя напр. `ai-generation-api` →
   **Private** → НЕ добавляй README/gitignore (репо уже не пустой) → Create.
2. В терминале (в папке проекта):
```bash
cd /c/Users/dios0/ai-generation-api
git remote add origin https://github.com/<твой-логин>/ai-generation-api.git
git push -u origin main
```
3. При первом push Git for Windows откроет браузер для входа (Credential Manager) —
   подтверди. Готово.

### Способ B — через gh CLI (если установишь)
```bash
winget install GitHub.cli      # один раз
gh auth login                  # вход в аккаунт
cd /c/Users/dios0/ai-generation-api
gh repo create ai-generation-api --private --source=. --push
```

---

## 3. Ежедневный цикл правок (это и есть «удобно править»)

```bash
# у себя на компьютере: поправил промты/код
git add -A
git commit -m "edit PHOTO_MODE_3 prompt"
git push
```

На сервере подтянуть и применить:
```bash
ssh root@<IP-сервера>
cd ai-generation-api
git pull
# только промты/режимы изменились → без пересборки:
docker compose exec api python -m scripts.mint_internal_token --subject ops   # токен
curl -X POST http://localhost:8000/admin/modes/reload -H "Authorization: Bearer <token>"
# изменился код/зависимости → пересобрать:
docker compose up -d --build
```

> Правка только промтов (`config/modes/*`) применяется **без перезапуска** через
> `/admin/modes/reload`. Пересборка нужна лишь при изменении кода/requirements.

---

## 4. Первичная установка на новом сервере (из GitHub)
```bash
ssh root@<IP>
git clone https://github.com/<логин>/ai-generation-api.git
cd ai-generation-api
cp .env.example .env && nano .env      # вписать реальные секреты/настройки
docker compose up -d --build
```

---

## 5. Правила гигиены
- Никогда не коммить `.env`, ключи, пароли (проверка: `git ls-files | grep .env`
  должен показывать только `.env.example`).
- Большие модели ComfyUI (чекпоинты) **не храни в git** — качай их на сервере
  отдельно (они огромные). В репо — только код, конфиги, промты, workflow-JSON.
- Результаты генерации — в S3, не в git.
- Ветки: для экспериментов делай `git checkout -b feature/x`, потом merge в `main`.
