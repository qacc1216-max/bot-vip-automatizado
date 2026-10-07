"""
Módulo de "handoff" (toma de control manual) para el bot VIP de Telegram.

Qué hace:
- Cada mensaje de un alumno se reenvía a tu chat de administración,
  con sus datos y el historial reciente de la conversación.
- Si respondés (con "reply") a ese mensaje reenviado, tu respuesta se
  le manda al alumno correspondiente, como si fuera el bot.
- Podés pausar el flujo automático para un alumno puntual con /pausar,
  y reanudarlo con /reanudar, para que el bot no te pise mientras
  estás hablando vos.

Cómo integrarlo a tu bot actual (Flask + pyTelegramBotAPI):

    import handoff

    @bot.message_handler(func=lambda m: True, content_types=['text'])
    def handle_incoming(message):
        if message.chat.id == handoff.ADMIN_CHAT_ID:
            if handoff.handle_admin_reply(bot, message):
                return
            return  # otros mensajes tuyos en el chat de admin se ignoran

        handoff.forward_to_admin(bot, message)

        if handoff.is_paused(message.chat.id):
            return  # estás contestando vos manualmente, el bot no interviene

        # ACÁ VA TU LÓGICA ACTUAL DEL FLUJO VIP
        run_vip_flow(message)

    handoff.register_commands(bot)
"""

import os
from datetime import datetime, timezone

import requests

HISTORY_LIMIT = 10  # cuántos mensajes previos mostrar al reenviar

ADMIN_CHAT_ID = None
SUPABASE_URL = None
SUPABASE_SERVICE_KEY = None


def configure(admin_chat_id: int, supabase_url: str | None = None,
              supabase_service_key: str | None = None) -> None:
    """Llamar una vez al arrancar el bot, antes de usar el resto del módulo.
    supabase_url y supabase_service_key son opcionales acá porque también
    se pueden tomar de las variables de entorno SUPABASE_URL / SUPABASE_SERVICE_KEY."""
    global ADMIN_CHAT_ID, SUPABASE_URL, SUPABASE_SERVICE_KEY
    ADMIN_CHAT_ID = admin_chat_id
    SUPABASE_URL = supabase_url or os.environ["SUPABASE_URL"]
    SUPABASE_SERVICE_KEY = supabase_service_key or os.environ["SUPABASE_SERVICE_KEY"]


def _headers(extra: dict | None = None) -> dict:
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def log_message(student_chat_id: int, student_name: str, student_username: str,
                 direction: str, text: str) -> None:
    requests.post(
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


def get_history(student_chat_id: int, limit: int = HISTORY_LIMIT) -> list[dict]:
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
    resp.raise_for_status()
    return list(reversed(resp.json()))  # orden cronológico, más viejo primero


def is_paused(student_chat_id: int) -> bool:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/paused_students",
        headers=_headers(),
        params={"student_chat_id": f"eq.{student_chat_id}", "select": "student_chat_id"},
        timeout=10,
    )
    resp.raise_for_status()
    return len(resp.json()) > 0


def set_paused(student_chat_id: int, paused: bool) -> None:
    if paused:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/paused_students",
            headers=_headers({"Prefer": "resolution=merge-duplicates"}),
            json={"student_chat_id": student_chat_id},
            timeout=10,
        )
    else:
        requests.delete(
            f"{SUPABASE_URL}/rest/v1/paused_students",
            headers=_headers(),
            params={"student_chat_id": f"eq.{student_chat_id}"},
            timeout=10,
        )


def _save_handoff_map(admin_message_id: int, student_chat_id: int) -> None:
    requests.post(
        f"{SUPABASE_URL}/rest/v1/handoff_map",
        headers=_headers({"Prefer": "return=minimal"}),
        json={"admin_message_id": admin_message_id, "student_chat_id": student_chat_id},
        timeout=10,
    )


def _get_student_from_handoff(admin_message_id: int) -> int | None:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/handoff_map",
        headers=_headers(),
        params={"admin_message_id": f"eq.{admin_message_id}", "select": "student_chat_id"},
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0]["student_chat_id"] if rows else None


def forward_to_admin(bot, message) -> None:
    """Reenvía el mensaje del alumno a tu chat de admin, con historial."""
    student_chat_id = message.chat.id
    student_name = message.from_user.first_name or ""
    student_username = message.from_user.username or ""
    text = message.text or "[mensaje sin texto]"

    log_message(student_chat_id, student_name, student_username, "in", text)

    history = get_history(student_chat_id)
    history_lines = []
    for row in history[-6:-1]:  # el último ya se muestra aparte abajo
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
    sent = bot.send_message(ADMIN_CHAT_ID, admin_text)
    _save_handoff_map(sent.message_id, student_chat_id)


def handle_admin_reply(bot, message) -> bool:
    """Si es un reply a un mensaje reenviado, manda tu texto al alumno. Devuelve True si lo manejó."""
    if not message.reply_to_message:
        return False

    student_chat_id = _get_student_from_handoff(message.reply_to_message.message_id)
    if not student_chat_id:
        return False

    bot.send_message(student_chat_id, message.text)
    log_message(student_chat_id, "", "", "out", message.text)
    bot.reply_to(message, "✅ Enviado al alumno.")
    return True


def register_commands(bot) -> None:
    """Registra /pausar y /reanudar. Llamalo una vez al armar el bot."""

    @bot.message_handler(commands=["pausar"])
    def cmd_pausar(message):
        if message.chat.id != ADMIN_CHAT_ID:
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Uso: /pausar <id_del_alumno>")
            return
        set_paused(int(parts[1]), True)
        bot.reply_to(message, f"⏸️ Bot pausado para {parts[1]}. Solo recibirá tus respuestas manuales.")

    @bot.message_handler(commands=["reanudar"])
    def cmd_reanudar(message):
        if message.chat.id != ADMIN_CHAT_ID:
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Uso: /reanudar <id_del_alumno>")
            return
        set_paused(int(parts[1]), False)
        bot.reply_to(message, f"▶️ Bot reanudado para {parts[1]}.")
