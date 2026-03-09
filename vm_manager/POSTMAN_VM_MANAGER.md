# VM Manager API: проверка через Postman

## База
- Base URL: `http://localhost:8986/api`
- Для JSON-запросов: `Content-Type: application/json`
- Все URL со слэшем в конце: `/.../`

## Авторизация
1. Получите JWT через `POST /api/login/`.
2. Для защищенных запросов добавляйте:
   - `Authorization: Bearer <access_token>`

## Роли и доступы
- `is_staff=true` (админ):
  - полный доступ ко всем tenant и VM;
  - создает tenant;
  - выдает/забирает доступ к tenant;
  - переносит owner tenant;
  - переносит VM между tenant.
- Не-админ:
  - видит и управляет только VM в tenant, куда ему выдан доступ.
  - может создавать peak-schedule только для своих VM.

## Peak Scheduler (планировщик пиков)
- Создает задачу, которая в заданные дату/время увеличивает ресурсы:
  - `target_type=vm`: увеличивает `cpu_cores/ram_mb/disk_gb/network_mbps` у VM.
  - `target_type=tenant`: увеличивает лимиты tenant (`cpu/ram/disk/network/max_vms`), только для админа.
- Все значения задаются как `*_delta`:
  - `+` значение = увеличить ресурс;
  - `-` значение = уменьшить ресурс.
- Статусы задач:
  - `pending` -> ожидает времени применения;
  - `applied` -> успешно применено;
  - `failed` -> ошибка при применении (причина в `error_message`);
  - `canceled` -> отменено.

## Модель лимитов tenant
- Лимиты считаются по всем VM, которые есть в tenant в БД.
- При переносе VM в перегруженный tenant перенос разрешен.
- Но `start/restart` VM в перегруженном tenant вернет ошибку.

## Важно про backend VM
- VM создаются через Docker.
- Перед тестом убедитесь, что установлен и запущен Docker (`docker ps`).
- Порядок создания: сначала контейнер запускается в runtime, потом запись в БД.
- Для `ubuntu_small` используется долгоживущая команда `sleep infinity`, поэтому VM остается `running` до явной остановки.
- Метрики VM теперь собираются автоматически в фоне после старта backend (доп. команда не обязательна).

---

## Рекомендуемые переменные Postman
Создайте Environment переменные:
- `baseUrl` = `http://localhost:8986/api`
- `admin_access_token`
- `admin_refresh_token`
- `user1_access_token`
- `user2_access_token`
- `tenant1_id`
- `tenant2_id`
- `vm_id`
- `metrics_minutes` (например `60`)
- `metrics_limit` (например `500`)

---

## 1) Логин админа
**POST** `{{baseUrl}}/login/`

Body:
```json
{
  "user_name": "admin",
  "password": "AdminPass123"
}
```

Ожидается: `200 OK`, поля `access`, `refresh`.

---

## 2) Создать tenant #1 (админ)
**POST** `{{baseUrl}}/tenants/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "name": "tenant-1",
  "owner_id": 2,
  "cpu_cores_limit": 8,
  "ram_mb_limit": 8192,
  "disk_gb_limit": 200,
  "network_mbps_limit": 1000,
  "max_vms": 10
}
```

Ожидается: `201 Created`.
Сохраните `id` в `tenant1_id`.

---

## 3) Создать tenant #2 с маленькими лимитами (админ)
**POST** `{{baseUrl}}/tenants/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "name": "tenant-2",
  "owner_id": 3,
  "cpu_cores_limit": 1,
  "ram_mb_limit": 512,
  "disk_gb_limit": 4,
  "network_mbps_limit": 100,
  "max_vms": 1
}
```

Ожидается: `201 Created`.
Сохраните `id` в `tenant2_id`.

---

## 4) Выдать доступ пользователю к tenant (админ)
**POST** `{{baseUrl}}/tenants/{{tenant1_id}}/members/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "user_id": 3
}
```

Ожидается: `200 OK`, `{"detail": "Member added"}`.

---

## 5) Список tenant
### 5.1 Админ видит все tenant
**GET** `{{baseUrl}}/tenants/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Ожидается: `200 OK` + все tenant.

### 5.2 Обычный пользователь видит только свои tenant
**GET** `{{baseUrl}}/tenants/`

Headers:
- `Authorization: Bearer {{user2_access_token}}`

Ожидается: `200 OK` + tenant, где user2 в members.

---

## 6) Создать VM в tenant (участник tenant или админ)
**POST** `{{baseUrl}}/vms/`

Headers:
- `Authorization: Bearer {{user1_access_token}}`

Body:
```json
{
  "tenant_id": {{tenant1_id}},
  "cpu_cores": 2,
  "ram_mb": 1024,
  "disk_gb": 10,
  "network_mbps": 200
}
```

Ожидается: `201 Created`.
Сохраните `id` в `vm_id`.

Примечание:
- Все поля кроме `tenant_id` необязательны
- Значения по умолчанию: `cpu_cores=1`, `ram_mb=512`, `disk_gb=4`, `network_mbps=100`

---

## 7) Проверка доступа к VM
### 7.1 Участник tenant видит VM
**GET** `{{baseUrl}}/vms/`

Headers:
- `Authorization: Bearer {{user1_access_token}}`

Ожидается: `200 OK` + VM tenant1.

### 7.2 Не-участник tenant не видит VM
**GET** `{{baseUrl}}/vms/{{vm_id}}/`

Headers:
- `Authorization: Bearer {{user_not_in_tenant_access_token}}`

Ожидается: `404 Not Found`.

---

## 8) Получить VM конкретного tenant
**GET** `{{baseUrl}}/tenants/{{tenant1_id}}/vms/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Ожидается: `200 OK` + список VM tenant1.

---

## 9) Перенос VM в другой tenant (только админ)
**POST** `{{baseUrl}}/vms/{{vm_id}}/move-tenant/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "tenant_id": {{tenant2_id}}
}
```

Ожидается: `200 OK`, у VM меняется `tenant_id`.

---

## 10) Проверка блокировки запуска при перегрузе tenant
Если после переноса tenant2 превысил лимиты, запуск/рестарт VM блокируются.

### 10.1 Запуск VM
**POST** `{{baseUrl}}/vms/{{vm_id}}/start/`

Headers:
- `Authorization: Bearer {{user2_access_token}}`

Ожидается: `400 Bad Request`:
```json
{
  "detail": "Tenant is over limits. VM start is blocked."
}
```

### 10.2 Рестарт VM
**POST** `{{baseUrl}}/vms/{{vm_id}}/restart/`

Headers:
- `Authorization: Bearer {{user2_access_token}}`

Ожидается: `400 Bad Request` с аналогичным `detail`.

---

## 11) Перенос владельца tenant (только админ)
**POST** `{{baseUrl}}/tenants/{{tenant1_id}}/transfer-owner/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "new_owner_id": 3
}

---

## 12) Создать peak-schedule для VM
**POST** `{{baseUrl}}/peak-schedules/`

Headers:
- `Authorization: Bearer {{user1_access_token}}` (или admin)

Body:
```json
{
  "target_type": "vm",
  "vm_id": {{vm_id}},
  "cpu_cores_delta": 2,
  "ram_mb_delta": 1024,
  "disk_gb_delta": 5,
  "network_mbps_delta": 100,
  "apply_at": "2026-03-05T18:30:00+03:00"
}
```

Ожидается: `201 Created`, статус `pending`.

---

## 13) Создать peak-schedule для tenant (только админ)
**POST** `{{baseUrl}}/peak-schedules/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "target_type": "tenant",
  "tenant_id": {{tenant1_id}},
  "cpu_cores_delta": 4,
  "ram_mb_delta": 4096,
  "disk_gb_delta": 50,
  "network_mbps_delta": 200,
  "max_vms_delta": 3,
  "apply_at": "2026-03-05T19:00:00+03:00"
}
```

Ожидается: `201 Created`, статус `pending`.

---

## 14) Список peak-schedules
**GET** `{{baseUrl}}/peak-schedules/`

Headers:
- `Authorization: Bearer {{admin_access_token}}` или user token

Ожидается:
- админ видит все задачи;
- обычный пользователь видит только свои.

---

## 15) Отмена pending задачи
**DELETE** `{{baseUrl}}/peak-schedules/{id}/`

Headers:
- `Authorization: Bearer {{admin_access_token}}` или автор задачи

Ожидается: `204 No Content`.
```

Ожидается: `200 OK`, `{"detail": "Tenant owner transferred"}`.

Проверка:
- новый owner автоматически имеет доступ;
- прошлый owner теряет доступ (удален из members).

---

## 12) Удаление участника tenant (только админ)
**DELETE** `{{baseUrl}}/tenants/{{tenant1_id}}/members/3/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Ожидается: `200 OK`, `{"detail": "Member removed"}`.

Особый кейс:
- если удаляется текущий owner tenant, owner станет админ, который выполняет запрос.

---

## 13) Обновление лимитов tenant (только админ)
**PATCH** `{{baseUrl}}/tenants/{{tenant2_id}}/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "cpu_cores_limit": 4,
  "ram_mb_limit": 4096,
  "disk_gb_limit": 40,
  "network_mbps_limit": 500,
  "max_vms": 5
}
```

Ожидается: `200 OK`.

---

## 14) Удаление VM
**DELETE** `{{baseUrl}}/vms/{{vm_id}}/`

Headers:
- `Authorization: Bearer {{user2_access_token}}`

Ожидается: `204 No Content`.

Важно:
- VM удаляется физически из БД.

---

## 15) Resize ресурсов VM (только админ)
**POST** `{{baseUrl}}/vms/{{vm_id}}/resize/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "cpu_cores": 4,
  "ram_mb": 2048,
  "disk_gb": 20,
  "network_mbps": 300
}
```

Ожидается: `200 OK`.

Проверка прав:
- если не админ: `403 Forbidden`.

---

## 16) Системные ресурсы (только админ)
### 16.1 Получить
**GET** `{{baseUrl}}/system-resources/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

### 16.2 Обновить
**PATCH** `{{baseUrl}}/system-resources/1/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "total_cpu_cores": 64,
  "total_ram_mb": 131072,
  "total_disk_gb": 2000
}
```

---

## 17) Логи действий VM (только админ)
**GET** `{{baseUrl}}/vm-logs/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Фильтры:
- `?vm_id={{vm_id}}`
- `?actor_id=2`

---

## 18) Удаление tenant (только админ)
**DELETE** `{{baseUrl}}/tenants/{{tenant2_id}}/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Ожидается: `204 No Content`.

---

## 19) Сбор метрик VM для графиков (только админ)
### 19.1 Сбор из Docker (реальные метрики)
**POST** `{{baseUrl}}/system-resources/collect-metrics/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "simulate": false,
  "lightweight": true,
  "only_running": true,
  "iterations": 1,
  "interval_seconds": 1.0
}
```

Ожидается: `200 OK`, пример:
```json
{
  "detail": "Metrics collected",
  "created": 3,
  "simulate": false,
  "only_running": true
}
```

Если Docker недоступен, ожидается `400 Bad Request` с `detail`.
Если `lightweight=true`, Docker не нужен: сбор идет из `/proc` хоста.

### 19.2 Сбор в режиме эмуляции
**POST** `{{baseUrl}}/system-resources/collect-metrics/`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Body:
```json
{
  "simulate": true,
  "lightweight": true,
  "only_running": true,
  "iterations": 10,
  "interval_seconds": 2.0
}
```

Ожидается: `200 OK`, метрики будут с `source = simulated`.
Так можно за один запрос накопить несколько точек для графика.

---

## 20) Получить временной ряд метрик для фронта (только админ)
**GET** `{{baseUrl}}/system-resources/metrics/?minutes={{metrics_minutes}}&limit={{metrics_limit}}`

Headers:
- `Authorization: Bearer {{admin_access_token}}`

Опциональные фильтры:
- `&vm_id={{vm_id}}`
- `&tenant_id={{tenant1_id}}`

Ожидается: `200 OK`, пример структуры:
```json
{
  "from": "2026-03-05T18:00:00Z",
  "to": "2026-03-05T19:00:00Z",
  "points_count": 120,
  "points": [
    {
      "id": 1,
      "vm": 4,
      "vm_name": "vm-t1-a1b2c3",
      "tenant": 1,
      "source": "docker",
      "cpu_percent": 24.7,
      "memory_mb": 341.3,
      "net_rx_mb": 12.8,
      "net_tx_mb": 3.6,
      "block_read_mb": 0.9,
      "block_write_mb": 0.4,
      "created_at": "2026-03-05T18:10:01.123456Z"
    }
  ]
}
```

---

## 21) Постоянный сбор метрик внутри backend-контейнера
Если нужен непрерывный мониторинг, запускайте management command отдельным процессом:

```bash
python manage.py collect_vm_metrics --interval 5 --forever
```

Для эмуляции без Docker:

```bash
python manage.py collect_vm_metrics --simulate --interval 2 --forever
```

Для максимально эффективного режима без Docker:

```bash
python manage.py collect_vm_metrics --lightweight --interval 2 --forever
```
