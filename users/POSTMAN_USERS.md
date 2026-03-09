# Users API: проверка через Postman

## База
- Base URL: `http://localhost:8986/api`
- Для JSON-запросов: `Content-Type: application/json`
- Все URL со слэшем в конце: `/.../`

## Авторизация
1. Сначала получите JWT через `POST /api/login/`.
2. Если ответ содержит `mfa_required=true`, подтвердите вход через:
   - `POST /api/login/2fa/` с `mfa_token` и `code` из email.
3. Для повторной отправки кода используйте:
   - `POST /api/login/2fa/resend/` с `mfa_token`.
4. Для защищенных запросов добавляйте заголовок:
   - `Authorization: Bearer <access_token>`

## Политика 2FA
- Email 2FA обязательна для всех пользователей, кроме `is_superuser=true`.
- Супер-админ входит только по логину/паролю (без второго шага).
- Обычный пользователь не может отключить 2FA (`POST /api/users/2fa/disable/` вернет `403 Forbidden`).

## Права доступа
- `POST /api/login/` — без токена
- `POST /api/login/2fa/` — без токена (второй шаг, если требуется)
- `POST /api/login/2fa/resend/` — без токена (повторная отправка кода)
- `POST /api/refresh/` — без токена (по refresh)
- `POST /api/register/` — только `IsAdminUser` (токен staff/admin)
- Все `GET/POST/PUT/PATCH/DELETE /api/users/...` — только `IsAdminUser`
- Исключение: `POST /api/users/change-my-password/` — любой аутентифицированный пользователь

## Сценарий временного пароля
1. Админ вызывает `POST /api/users/{id}/generate-temp-password/`.
2. API возвращает временный пароль (`temporary_password`) один раз.
3. Пользователь логинится с этим временным паролем.
4. Пока `must_change_password=true`, все endpoint-ы (кроме `change-my-password`) блокируются.
5. Пользователь вызывает `POST /api/users/change-my-password/` и задаёт постоянный пароль.
6. Флаг `must_change_password` сбрасывается, доступ к API восстанавливается.

---

## 1) Логин
**POST** `{{baseUrl}}/login/`

Body:
```json
{
  "user_name": "admin",
  "password": "AdminPass123"
}
```

Ожидается:
- для супер-админа: `200 OK`, поля `access`, `refresh`;
- для остальных: `200 OK`, поля `mfa_required=true`, `mfa_token`.

### 1.1 Подтверждение входа кодом из email
**POST** `{{baseUrl}}/login/2fa/`

Body:
```json
{
  "mfa_token": "<mfa_token>",
  "code": "123456"
}
```

Ожидается: `200 OK`, поля `access`, `refresh`.

### 1.2 Повторная отправка кода
**POST** `{{baseUrl}}/login/2fa/resend/`

Body:
```json
{
  "mfa_token": "<mfa_token>"
}
```

Ожидается: `200 OK`, `{"detail":"Verification code resent to email."}`.

---

## 2) Обновление access токена
**POST** `{{baseUrl}}/refresh/`

Body:
```json
{
  "refresh": "<refresh_token>"
}
```

Ожидается: `200 OK`, новый `access`.

---

## 3) Регистрация пользователя (только админ/стафф)
**POST** `{{baseUrl}}/register/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Body:
```json
{
  "user_name": "newuser",
  "email": "newuser@example.com",
  "password": "StrongPass123"
}
```

Ожидается: `201 Created`.

Проверка прав:
- без токена: `401 Unauthorized`
- с не-админ токеном: `403 Forbidden`

---

## 4) Список пользователей
**GET** `{{baseUrl}}/users/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Ожидается: `200 OK`.

---

## 5) Создание пользователя админом
**POST** `{{baseUrl}}/users/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Body:
```json
{
  "user_name": "user2",
  "email": "user2@example.com",
  "password": "StrongPass123",
  "is_active": true,
  "is_staff": false
}
```

Ожидается: `201 Created`.

---

## 6) Получить пользователя по ID
**GET** `{{baseUrl}}/users/1/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Ожидается: `200 OK`.

---

## 7) Полное обновление пользователя
**PUT** `{{baseUrl}}/users/1/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Body:
```json
{
  "user_name": "user2_new",
  "email": "user2_new@example.com",
  "is_active": true,
  "is_staff": false
}
```

Ожидается: `200 OK`.

---

## 8) Частичное обновление пользователя
**PATCH** `{{baseUrl}}/users/1/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Body:
```json
{
  "email": "patched@example.com"
}
```

Ожидается: `200 OK`.

---

## 9) Удаление пользователя
**DELETE** `{{baseUrl}}/users/1/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Ожидается: `204 No Content`.

---

## 10) Текущий пользователь (`me`)
### 10.1 Получить профиль
**GET** `{{baseUrl}}/users/me/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Ожидается: `200 OK`.

### 10.2 Обновить профиль
**PATCH** `{{baseUrl}}/users/me/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Body:
```json
{
  "email": "admin_new@example.com"
}
```

Ожидается: `200 OK`.

---

## 11) Активация пользователя
**POST** `{{baseUrl}}/users/1/activate/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Ожидается: `200 OK`, пример:
```json
{
  "detail": "User activated"
}
```

---

## 12) Деактивация пользователя
**POST** `{{baseUrl}}/users/1/deactivate/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Ожидается: `200 OK`, пример:
```json
{
  "detail": "User deactivated"
}
```

---

## 13) Смена пароля пользователя
**POST** `{{baseUrl}}/users/1/set-password/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Body:
```json
{
  "password": "NewStrongPass123"
}
```

Ожидается: `200 OK`, пример:
```json
{
  "detail": "Password updated"
}
```

---

## 14) Генерация временного пароля (админ)
**POST** `{{baseUrl}}/users/1/generate-temp-password/`

Headers:
- `Authorization: Bearer <admin_access_token>`

Ожидается: `200 OK`, пример:
```json
{
  "detail": "Temporary password generated. User must change password after login.",
  "temporary_password": "gQv...temporary..."
}
```

Сохраните `temporary_password` сразу: повторно API его не покажет.

---

## 15) Смена своего пароля после временного
**POST** `{{baseUrl}}/users/change-my-password/`

Headers:
- `Authorization: Bearer <access_token>`

Body:
```json
{
  "current_password": "temporary_password_from_admin",
  "new_password": "NewStrongPass123"
}
```

Ожидается: `200 OK`:
```json
{
  "detail": "Password changed"
}
```

---

## Рекомендация по переменным Postman
Создайте Environment-переменные:
- `baseUrl` = `http://localhost:8986/api`
- `admin_access_token`
- `admin_refresh_token`

После логина сохраните токены в переменные и используйте их в следующих запросах.
