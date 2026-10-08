"""
Módulo de "handoff" (toma de control manual) para el bot VIP de Telegram.

- Cada mensaje de un alumno se reenvía a tu chat de administración,
  con sus datos y el historial reciente de la conversación.
- Si respondés (reply) a ese mensaje reenviado, tu texto le llega al alumno
  desde el bot.
- /pausar <id> y /reanudar <id> frenan / reactivan el flujo automático
  para un alumno puntual.

Robustez: si Supabase falla (URL mal cargada, clave incorrecta, tablas sin
crear), el bot NO se cae ni se corta el flujo VIP: se pierde el historial,
pero el reenvío y las respuestas siguen funcionando (con respaldo en memoria),
y el motivo exacto queda escrito en los logs de Render con el prefijo [handoff].
"""

import os
from datetime import datetime, timezone

import requests

HISTORY_LIMIT = 10  # cuántos mensajes previos mostrar al reenviar

ADMIN_CHAT_ID = None
SUPABASE_URL = ""
SUPABASE_SERVICE_KEY = ""

# Respaldo en memoria por si Supabase falla
_handoff_cache: dict = {}
_paused_cache: set = set()


def _log(msg: str) -> None:
    print(f"[handoff] {msg}", flush=True)


def configure(admin_chat_id: int, supabase_url: str | None = None,
              supabase_service_key: str | None = None) -> None:
    """Llamar una vez al arrancar el bot."""
    global ADMIN_CHAT_ID, SUPABASE_URL, SUPABASE_SERVICE_KEY
    ADMIN_CHAT_ID = admin_chat_id
    SUPABASE_URL = (supabase_url or os.environ.get("SUPABASE_URL", "")).strip().rstrip("/")
    SUPABASE_SERVICE_KEY = (supabase_service_key or os.environ.get("SUPABASE_SERVICE_KEY", "")).strip()

    if not SUPABASE_URL.startswith("https://") or not SUPABASE_SERVICE_KEY:
        _log("ATENCION: SUPABASE_URL o SUPABASE_SERVICE_KEY faltan o son invalidas. "
             "El historial no se va a guardar. SUPABASE_URL debe verse como https://xxxx.supabase.co")
    else:
        _log(f"Supabase configurado en {SUPABASE_URL}")


def _headers(extra: dict | None = None) -> dict:
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _check(resp, action: str) -> bool:
    if not resp.ok:
        _log(f"Supabase respondio {resp.status_code} al {action}: {resp.text[:200]}")
        return False
    return True


def log_message(student_chat_id, student_name, student_username, direction, text) -> None:
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/conversation_log",
            headers=_headers({"Prefer": "return=minimal"}),
            json={
                "student_chat_id": student_chat_id,
                "student_name": student_name,
                "student_username": student_username,
                "direction": direction,
                "message_text": text,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=10,
        )
        _check(resp, "guardar el mensaje")
    except Exception as exc:
        _log(f"No se pudo guardar el mensaje: {exc}")


def get_history(student_chat_id, limit: int = HISTORY_LIMIT) -> list:
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/conversation_log",
            headers=_headers(),
            params={
                "student_chat_id": f"eq.{student_chat_id}",
                "order": "created_at.desc",
                "limit": limit,
            },
            timeout=10,
        )
        if not _check(resp, "leer el historial"):
            return []
        return list(reversed(resp.json()))  # cronologico, mas viejo primero
    except Exception as exc:
        _log(f"No se pudo leer el historial: {exc}")
        return []


def is_paused(student_chat_id) -> bool:
    if student_chat_id in _paused_cache:
        return True
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/paused_students",
            headers=_headers(),
            params={"student_chat_id": f"eq.{student_chat_id}", "select": "student_chat_id"},
            timeout=10,
        )
        if not _check(resp, "leer el estado de pausa"):
            return False
        paused = len(resp.json()) > 0
        if paused:
            _paused_cache.add(student_chat_id)
        return paused
    except Exception as exc:
        _log(f"No se pudo leer el estado de pausa: {exc}")
        return False


def set_paused(student_chat_id, paused: bool) -> None:
    if paused:
        _paused_cache.add(student_chat_id)
    else:
        _paused_cache.discard(student_chat_id)
    try:
        if paused:
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/paused_students",
                headers=_headers({"Prefer": "resolution=merge-duplicates"}),
                json={"student_chat_id": student_chat_id},
                timeout=10,
            )
        else:
            resp = requests.delete(
                f"{SUPABASE_URL}/rest/v1/paused_students",
                headers=_headers(),
                params={"student_chat_id": f"eq.{student_chat_id}"},
                timeout=10,
            )
        _check(resp, "actualizar la pausa")
    except Exception as exc:
        _log(f"No se pudo actualizar la pausa: {exc}")


def _save_handoff_map(admin_message_id, student_chat_id) -> None:
    _handoff_cache[admin_message_id] = student_chat_id
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/handoff_map",
            headers=_headers({"Prefer": "return=minimal"}),
            json={"admin_message_id": admin_message_id, "student_chat_id": student_chat_id},
            timeout=10,
        )
        _check(resp, "guardar la relacion mensaje-alumno")
    except Exception as exc:
        _log(f"No se pudo guardar la relacion mensaje-alumno: {exc}")


def _get_student_from_handoff(admin_message_id):
    if admin_message_id in _handoff_cache:
        return _handoff_cache[admin_message_id]
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/handoff_map",
            headers=_headers(),
            params={"admin_message_id": f"eq.{admin_message_id}", "select": "student_chat_id"},
            timeout=10,
        )
        if not _check(resp, "buscar el alumno de ese mensaje"):
            return None
        rows = resp.json()
        return rows[0]["student_chat_id"] if rows else None
    except Exception as exc:
        _log(f"No se pudo buscar el alumno de ese mensaje: {exc}")
        return None


def forward_to_admin(bot, message) -> None:
    """Reenvía el mensaje del alumno a tu chat de admin, con historial."""
    student_chat_id = message.chat.id
    student_name = message.from_user.first_name or ""
    student_username = message.from_user.username or ""
    text = message.text or "[mensaje sin texto]"

    log_message(student_chat_id, student_name, student_username, "in", text)

    history = get_history(student_chat_id)
    history_lines = []
    for row in history[-6:-1]:  # el ultimo (el actual) se muestra aparte
        arrow = "👉" if row["direction"] == "in" else "🤖"
        history_lines.append(f"{arrow} {row['message_text']}")
    history_block = "\n".join(history_lines) if history_lines else "(sin historial previo)"

    username_part = f"@{student_username}" if student_username else "(sin usuario)"
    paused_note = "\n⏸️ Bot PAUSADO para este alumno." if is_paused(student_chat_id) else ""

    admin_text = (
        f"📩 Mensaje de: {student_name} {username_part}\n"
        f"🆔 ID: {student_chat_id}{paused_note}\n\n"
        f"🕓 Historial reciente:\n{history_block}\n\n"
        f"💬 Ahora escribió:\n\"{text}\"\n\n"
        f"Respondé a ESTE mensaje (reply) para contestarle directamente."
    )
    try:
        sent = bot.send_message(ADMIN_CHAT_ID, admin_text)
        _save_handoff_map(sent.message_id, student_chat_id)
    except Exception as exc:
        _log(f"No se pudo reenviar el mensaje al admin: {exc}")


def handle_admin_reply(bot, message) -> bool:
    """Si es un reply a un mensaje reenviado, manda tu texto al alumno."""
    if not message.reply_to_message:
        return False

    student_chat_id = _get_student_from_handoff(message.reply_to_message.message_id)
    if not student_chat_id:
        bot.reply_to(message, "⚠️ No pude identificar a qué alumno corresponde ese mensaje. "
                              "Respondé (reply) a uno de los mensajes que empiezan con '📩 Mensaje de:'.")
        return True

    try:
        bot.send_message(student_chat_id, message.text)
    except Exception as exc:
        bot.reply_to(message, f"❌ No pude enviarlo al alumno: {exc}")
        return True

    log_message(student_chat_id, "", "", "out", message.text)
    bot.reply_to(message, "✅ Enviado al alumno.")
    return True


def register_commands(bot) -> None:
    """Registra /pausar y /reanudar. Llamarlo una vez al armar el bot."""

    def _parse_id(message):
        parts = message.text.split()
        if len(parts) < 2:
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    @bot.message_handler(commands=["pausar"])
    def cmd_pausar(message):
        if message.chat.id != ADMIN_CHAT_ID:
            return
        student_id = _parse_id(message)
        if student_id is None:
            bot.reply_to(message, "Uso: /pausar <id_del_alumno> (el ID es un número)")
            return
        set_paused(student_id, True)
        bot.reply_to(message, f"⏸️ Bot pausado para {student_id}. Solo recibirá tus respuestas manuales.")

    @bot.message_handler(commands=["reanudar"])
    def cmd_reanudar(message):
        if message.chat.id != ADMIN_CHAT_ID:
            return
        student_id = _parse_id(message)
        if student_id is None:
            bot.reply_to(message, "Uso: /reanudar <id_del_alumno> (el ID es un número)")
            return
        set_paused(student_id, False)
        bot.reply_to(message, f"▶️ Bot reanudado para {student_id}.")
