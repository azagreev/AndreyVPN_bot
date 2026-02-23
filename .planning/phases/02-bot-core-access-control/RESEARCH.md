# Phase 2: Bot Core & Access Control - Research

**Researched:** 2026-02-24
**Domain:** Telegram Bot (aiogram 3), Access Control, CAPTCHA
**Confidence:** HIGH

## Summary
The research focused on implementing a secure onboarding flow for `AndreyVPN_bot` using `aiogram 3` and `aiosqlite`. The flow consists of:
1. User sends `/start` -> Trigger Math CAPTCHA.
2. CAPTCHA passed -> Send approval request to Admin.
3. Admin approves -> Update DB (`is_approved = 1`) -> Notify User.
4. Access control middleware blocks any requests from users where `is_approved = 0`.

## Standard Stack
- **Framework:** `aiogram 3.x` (Standard for modern TG bots).
- **Database:** `aiosqlite` (Async SQLite wrapper).
- **FSM:** `aiogram.fsm` (For CAPTCHA state management).
- **Middleware:** `aiogram.BaseMiddleware` (For global access checks).

## Architecture Patterns
### Recommended Onboarding Flow
- **State 1:** `CaptchaStates.waiting_for_answer`.
- **State 2:** `RegistrationStates.waiting_for_approval` (Optional, or just check DB).

### Access Control Middleware
Implement a `WhitelistingMiddleware` that:
1. Fetches user from `users` table (or uses injected session).
2. If `user.is_approved` is `False` and the command is not `/start` or a CAPTCHA response, block the request and send a "Ожидайте одобрения администратором" message.

## Code Examples (Russian)

### 1. CAPTCHA Handler
```python
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    n1, n2 = random.randint(1, 10), random.randint(1, 10)
    await state.update_data(captcha=n1 + n2)
    await state.set_state(CaptchaStates.waiting_for_captcha)
    await message.answer(f"Решите пример: {n1} + {n2} = ?")
```

### 2. Admin Approval Buttons
```python
builder = InlineKeyboardBuilder()
builder.button(text="✅ Одобрить", callback_data=AdminCallback(action="approve", user_id=target_id))
builder.button(text="❌ Отклонить", callback_data=AdminCallback(action="reject", user_id=target_id))
```

## Common Pitfalls
- **Middleware Order:** The `DbMiddleware` must run before `AccessControlMiddleware` so that user data is available in `data['user']`.
- **Race Conditions:** Multiple `/start` clicks. Solution: Check if user already exists in DB or has a pending status.
- **Admin ID:** Ensure `ADMIN_ID` is loaded from environment variables and handled as an integer.

## Phase Requirements Support
| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | CAPTCHA challenge | Verified FSM-based math captcha pattern. |
| AUTH-02 | Admin approval | Verified Inline Buttons + CallbackData workflow. |
| AUTH-03 | Access control | Verified BaseMiddleware pattern for whitelisting. |
