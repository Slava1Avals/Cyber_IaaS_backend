# Cyber IaaS — Infrastructure as a Service Platform

Облачная платформа управления виртуальными машинами (VM) с поддержкой мультитенантности, двухфакторной аутентификацией и планированием ресурсов.

## 📋 Быстрый старт

```bash
# Клонирование и подготовка
git clone <repository-url> && cd Cyber_IaaS
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Инициализация БД и запуск
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8986
```

API доступен: `http://localhost:8986/api/`

## 🎯 Что это?

**Cyber IaaS** — REST API на Django для управления виртуальными инфраструктурами:
- 🏢 Мультитенантность с контролем ресурсов
- 🖥️ Управление VM (создание, запуск, остановка, удаление)
- 👤 Система пользователей с 2FA по email
- 📊 Сбор и отслеживание метрик ресурсов
- ⏱️ Планировщик пиков нагрузки (Peak Scheduler)
- 🔐 Контроль доступа через роли и перми
- 🧪 Mock Docker Service для разработки

## 🏗️ Структура

### Два основных приложения:

**Users** — управление пользователями и аутентификацией
- JWT токены (access/refresh)
- Email 2FA
- Временные пароли для новых пользователей
- Смена пароля

**VM Manager** — управление виртуальными машинами и ресурсами
- CRUD операции для Tenants и VMs
- Контроль лимитов ресурсов (CPU, RAM, Disk, Network)
- Автоматический сбор метрик
- Peak Resource Scheduler для планирования увеличения ресурсов
- Логирование всех действий

## 🚀 Основные API эндпоинты

### Аутентификация
```
POST   /api/login/                    # Вход
POST   /api/login/2fa/                # 2FA подтверждение
POST   /api/login/2fa/resend/         # Повторная отправка кода
POST   /api/refresh/                  # Обновление токена
```

### Пользователи
```
GET    /api/users/                    # Список (админ)
POST   /api/register/                 # Создание (админ)
GET    /api/users/me/                 # Мой профиль
POST   /api/users/change-my-password/ # Смена пароля
POST   /api/users/{id}/generate-temp-password/  # Временный пароль (админ)
```

### Арендаторы (Tenants)
```
GET    /api/tenants/                  # Список
POST   /api/tenants/                  # Создание (админ)
PATCH  /api/tenants/{id}/             # Обновление (админ)
DELETE /api/tenants/{id}/             # Удаление (админ)
POST   /api/tenants/{id}/add-member/  # Добавить члена (админ)
POST   /api/tenants/{id}/transfer-owner/  # Передать владельца (админ)
```

### Виртуальные машины (VMs)
```
GET    /api/vms/                      # Список
POST   /api/vms/                      # Создание
DELETE /api/vms/{id}/                 # Удаление
POST   /api/vms/{id}/start/           # Запуск
POST   /api/vms/{id}/stop/            # Остановка
POST   /api/vms/{id}/restart/         # Перезагрузка
POST   /api/vms/{id}/resize/          # Изменение ресурсов (админ)
POST   /api/vms/{id}/move-tenant/     # Перемещение (админ)
```

### Метрики
```
GET    /api/system-resources/         # Информация о ресурсах (админ)
POST   /api/system-resources/collect-metrics/  # Сбор метрик (админ)
GET    /api/system-resources/metrics/ # История метрик (админ)
```

### Peak Scheduler
```
GET    /api/peak-schedules/           # Список
POST   /api/peak-schedules/           # Создание
DELETE /api/peak-schedules/{id}/      # Удаление
```

## 🔐 Роли и права

| Роль | Описание | 2FA |
|------|---------|-----|
| **Superuser** | Полный доступ, управляет всеми пользователями и ресурсами | Не требуется |
| **Admin/Staff** | Создает tenants, управляет пользователями и VM | Обязательна |
| **Regular User** | Видит и управляет только своими VM в разрешенных tenants | Обязательна |

## 🔑 Аутентификация

### Логин с 2FA
```bash
# 1. Логин
POST /api/login/
{
  "user_name": "admin",
  "password": "password"
}

# Ответ (если требуется 2FA):
{
  "mfa_required": true,
  "mfa_token": "token_value"
}

# 2. Подтверждение 2FA
POST /api/login/2fa/
{
  "mfa_token": "token_value",
  "code": "123456"
}

# Ответ:
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "user": { ... }
}
```

### Использование токена
```bash
curl -H "Authorization: Bearer <access_token>" \
     http://localhost:8986/api/users/me/
```

### Обновление токена
```bash
POST /api/refresh/
{
  "refresh": "eyJ..."
}

# Ответ:
{
  "access": "eyJ..."
}
```

## 📊 Примеры использования

### Создание tenant'а
```bash
curl -X POST http://localhost:8986/api/tenants/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production",
    "owner_id": 1,
    "cpu_cores_limit": 20,
    "ram_mb_limit": 16384,
    "disk_gb_limit": 400,
    "network_mbps_limit": 2000,
    "max_vms": 10
  }'
```

### Создание и запуск VM
```bash
# Создание
curl -X POST http://localhost:8986/api/vms/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "name": "web-server-01",
    "docker_image": "ubuntu:22.04",
    "cpu_cores": 2,
    "ram_mb": 2048,
    "disk_gb": 50,
    "network_mbps": 100
  }'

# Запуск
curl -X POST http://localhost:8986/api/vms/{id}/start/ \
  -H "Authorization: Bearer <token>"
```

### Планирование пика нагрузки
```bash
curl -X POST http://localhost:8986/api/peak-schedules/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "target_type": "vm",
    "vm_id": 1,
    "apply_at": "2026-03-09T18:00:00Z",
    "cpu_cores_delta": 2,
    "ram_mb_delta": 2048,
    "disk_gb_delta": 0,
    "network_mbps_delta": 0
  }'
```

## 📦 Технологический стек

- **Backend:** Django 5.2, Django REST Framework
- **БД:** SQLite (dev) / PostgreSQL (prod)
- **Аутентификация:** JWT (djangorestframework-simplejwt)
- **Email:** SMTP (для 2FA кодов)
- **CORS:** django-cors-headers
- **Виртуализация:** Mock Docker Service (без зависимостей)

## ⚙️ Установка

### Требования
- Python 3.10+
- pip/venv

### Шаги

```bash
# 1. Клонирование
git clone <url>
cd Cyber_IaaS

# 2. Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# 3. Зависимости
pip install -r requirements.txt

# 4. Конфигурация (опционально)
cp .env.example .env
# Отредактировать .env по необходимости

# 5. Миграции
python manage.py migrate

# 6. Суперпользователь
python manage.py createsuperuser

# 7. Запуск
python manage.py runserver 8986

# 8. Admin панель
# Перейти на http://localhost:8986/admin/
```

## 🧪 Тестирование

```bash
# Все тесты
python manage.py test

# Конкретное приложение
python manage.py test users
python manage.py test vm_manager

# С детальным выводом
python manage.py test --verbosity=2
```

Mock Docker Service позволяет запускать тесты без Docker.

## 📋 Модели данных

### User
```
- user_name (уникальное)
- email
- password (хеширован)
- is_staff, is_superuser
- must_change_password
- two_factor_enabled
```

### Tenant
```
- name
- owner (User)
- members (M2M User)
- cpu_cores_limit, ram_mb_limit, disk_gb_limit
- network_mbps_limit, max_vms
```

### VirtualMachine
```
- name
- tenant (ForeignKey)
- docker_image
- container_id (mock)
- status (stopped/running/starting/stopping/restarting/failed)
- cpu_cores, ram_mb, disk_gb, network_mbps
```

### VMMetricsSnapshot
```
- vm (ForeignKey)
- tenant (ForeignKey)
- cpu_percent, memory_mb
- net_rx_mb, net_tx_mb
- block_read_mb, block_write_mb
- source (real/simulated)
- created_at
```

### PeakResourceSchedule
```
- target_type (vm/tenant)
- vm, tenant (ForeignKey)
- apply_at (datetime)
- status (pending/applied/failed/canceled)
- cpu_cores_delta, ram_mb_delta, disk_gb_delta, network_mbps_delta
- max_vms_delta (только для tenant)
```

### VMActionLog
```
- vm (ForeignKey)
- actor (User)
- action (created/started/stopped/etc)
- details (JSON)
- created_at
```

## 🐳 Mock Docker Service

Вместо реальных Docker контейнеров используется Mock сервис, который:

✅ **Генерирует** уникальные container IDs (UUID)
✅ **Симулирует** метрики с реалистичными значениями
✅ **Не требует** установки Docker
✅ **Ускоряет** тестирование и разработку
✅ **Изолирует** от системных зависимостей

Методы:
- `create_and_start()` — создание VM
- `start()`, `stop()`, `restart()` — управление VM
- `delete()` — удаление VM
- `resize()` — изменение ресурсов
- `read_metrics()` — возврат симулированных метрик

## 📁 Структура проекта

```
Cyber_IaaS/
├── config/              # Django конфиг
│   ├── settings.py      # Основные настройки
│   ├── urls.py          # Маршруты
│   └── wsgi.py, asgi.py
├── users/               # Приложение Users
│   ├── models.py, views.py, serializers.py
│   ├── permissions.py, two_factor_email.py
│   ├── tests.py, urls.py, admin.py
│   └── migrations/
├── vm_manager/          # Приложение VM Manager
│   ├── models.py, views.py, serializers.py
│   ├── services.py (Mock Docker), permissions.py
│   ├── notifications.py, constants.py
│   ├── tests.py, urls.py, admin.py
│   ├── management/commands/ (фоновые задачи)
│   └── migrations/
├── manage.py            # Django CLI
├── requirements.txt     # Зависимости
├── .env.example         # Пример конфигурации
├── README.md            # Этот файл
├── CONTRIBUTING.md      # Рекомендации разработке
├── DEPLOYMENT.md        # Инструкции развертывания
├── API.md               # Справочник API
└── PROJECT_STRUCTURE.md # Подробная структура
```

## 🔧 Конфигурация

### .env переменные
```
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1

# БД
DATABASE_URL=sqlite:///db.sqlite3

# Email для 2FA
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=your-email@gmail.com
# EMAIL_HOST_PASSWORD=your-app-password

# JWT
JWT_ACCESS_TOKEN_LIFETIME=15
JWT_REFRESH_TOKEN_LIFETIME=7

# VM
VM_EMAIL_NOTIFICATIONS_ENABLED=True
```

## 🐛 Отладка и разработка

```bash
# Django shell для экспериментов
python manage.py shell

# Admin панель
http://localhost:8986/admin/

# Создание миграций (при изменении моделей)
python manage.py makemigrations
python manage.py migrate

# Сбор статических файлов (для production)
python manage.py collectstatic
```

## 📚 Дополнительная документация

- **API Reference** — `API.md` — полный справочник всех эндпоинтов с примерами
- **Contributing** — `CONTRIBUTING.md` — как внести вклад в проект
- **Deployment** — `DEPLOYMENT.md` — инструкции по развертыванию на production
- **Project Structure** — `PROJECT_STRUCTURE.md` — подробное описание структуры
- **Changelog** — `CHANGELOG.md` — история изменений
- **Users API** — `/users/POSTMAN_USERS.md` — примеры Postman для Users
- **VM Manager API** — `/vm_manager/POSTMAN_VM_MANAGER.md` — примеры для VM Manager

## 🤝 Разработка

```bash
# Создать feature branch
git checkout -b feature/my-feature

# Сделать изменения
# Запустить тесты
python manage.py test

# Коммитить
git commit -m "feat: добавить новый эндпоинт"

# Push и Pull Request
git push origin feature/my-feature
```

Стиль коммитов:
- `feat:` — новая функция
- `fix:` — исправление ошибки
- `refactor:` — переработка кода
- `test:` — тесты
- `docs:` — документация

## 📊 Проверка здоровья приложения

```bash
# Проверить все зависимости установлены
python -m pip check

# Проверить безопасность
pip install safety
safety check

# Запустить линтер (если установлен)
flake8 .
```

## 🚀 Деплой

### Development
```bash
python manage.py runserver 8986
```

### Production
```bash
# С Gunicorn
gunicorn --bind 0.0.0.0:8000 --workers 4 config.wsgi:application

# С Docker
docker-compose up -d
```

Подробнее см. `DEPLOYMENT.md`

## 📝 Лицензия

MIT License — свободно используйте в своих проектах

## ✉️ Поддержка

По вопросам откройте Issue или свяжитесь с командой разработчиков.

---

**Версия:** 1.0.0  
**Последнее обновление:** 9 марта 2026 года  
**Python:** 3.10+  
**Django:** 5.2.12
