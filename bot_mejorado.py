import os
import time
import logging
import threading

import telebot
from telebot import types
from flask import Flask, request
from supabase import create_client, Client

# ----------------------- CONFIG -----------------------
TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_ID_RAW = os.environ.get('ADMIN_ID')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

for var_name, var_val in [
    ('TELEGRAM_TOKEN', TOKEN),
    ('ADMIN_ID', ADMIN_ID_RAW),
    ('SUPABASE_URL', SUPABASE_URL),
    ('SUPABASE_KEY', SUPABASE_KEY),
]:
    if not var_val:
        raise RuntimeError(f"Falta la variable de entorno {var_name}")

MI_TELEGRAM_ID = int(ADMIN_ID_RAW)

LINK_REGISTRO = os.environ.get('LINK_REGISTRO', "https://stockity-r3.com?a=9e29d7ed3cab&t=0")
LINK_GRUPO_VIP = os.environ.get('LINK_GRUPO_VIP', "https://t.me/+CwS4WQkN6c80YTYx")
VIDEO_FILE_ID = os.environ.get('VIDEO_FILE_ID', "")

# ----------------------- LOGGING -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("bot_vip")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------------------- HELPERS DE BASE DE DATOS -----------------------

def get_usuario(chat_id):
    res = supabase.table("usuarios").select("*").eq("chat_id", chat_id).execute()
    return res.data[0] if res.data else None


def upsert_usuario(chat_id, step=None, last_interaction=None, reminded=None, trader_id=None, seguimientos_enviados=None):
    actual = get_usuario(chat_id) or {}
    payload = {
        "chat_id": chat_id,
        "step": step if step is not None else actual.get("step", 1),
        "last_interaction": last_interaction if last_interaction is not None else time.time(),
        "reminded": reminded if reminded is not None else actual.get("reminded", False),
        "trader_id": trader_id if trader_id is not None else actual.get("trader_id"),
        "seguimientos_enviados": seguimientos_enviados if seguimientos_enviados is not None else actual.get("seguimientos_enviados", 0),
    }
    supabase.table("usuarios").upsert(payload).execute()


def trader_registrado(trader_id):
    res = supabase.table("traders").select("*").eq("trader_id", trader_id).execute()
    return bool(res.data and res.data[0].get("registrado"))


def trader_depositado(trader_id):
    res = supabase.table("traders").select("*").eq("trader_id", trader_id).execute()
    return bool(res.data and res.data[0].get("depositado"))


def marcar_trader(trader_id, registrado=None, depositado=None):
    res = supabase.table("traders").select("*").eq("trader_id", trader_id).execute()
    actual = res.data[0] if res.data else {}
    payload = {
        "trader_id": trader_id,
        "registrado": registrado if registrado is not None else actual.get("registrado", False),
        "depositado": depositado if depositado is not None else actual.get("depositado", False),
    }
    supabase.table("traders").upsert(payload).execute()


def guardar_mensaje(chat_id, texto):
    try:
        supabase.table("mensajes").insert({
            "chat_id": chat_id,
            "texto": texto,
            "fecha": time.time(),
        }).execute()
    except Exception as e:
        logger.error(f"Error guardando mensaje de {chat_id}: {e}")


# ----------------------- CAPTURADOR DE FILE ID -----------------------
@bot.message_handler(content_types=['video'])
def capturar_file_id(message):
    file_id = message.video.file_id
    guardar_mensaje(message.chat.id, "[envió un video]")
    logger.info(f"Video recibido, file_id: {file_id}")
    bot.reply_to(message, f"✅ Video recibido. file_id:\n`{file_id}`", parse_mode="Markdown")


# ----------------------- WEBHOOK / POSTBACK -----------------------
@app.route('/postback', methods=['GET'])
def affiliate_postback():
    trader_id = request.args.get('trader_id')
    evento = request.args.get('event', 'registro')

    if not trader_id:
        logger.warning("Postback recibido sin trader_id")
        return "trader_id faltante", 400

    trader_id = trader_id.strip()

    if evento == 'registro':
        marcar_trader(trader_id, registrado=True)
    elif evento == 'deposito':
        marcar_trader(trader_id, registrado=True, depositado=True)
    else:
        logger.warning(f"Evento desconocido en postback: {evento}")
        return "evento inválido", 400

    logger.info(f"Postback: trader {trader_id} -> {evento}")

    try:
        bot.send_message(MI_TELEGRAM_ID, f"💰 Postback: trader {trader_id} realizó {evento}.")
    except Exception as e:
        logger.error(f"No se pudo notificar al admin: {e}")

    return "OK", 200


# ----------------------- 1. /start -----------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    guardar_mensaje(chat_id, "/start")
    upsert_usuario(chat_id, step=1, last_interaction=time.time(), reminded=False, seguimientos_enviados=0)
    logger.info(f"Nuevo /start de {chat_id}")

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔗 Registrarme en la Plataforma", url=LINK_REGISTRO))
    markup.add(types.InlineKeyboardButton("✅ Ya me registré, verificar mi ID", callback_data="pedir_id_registro"))

    texto = (
        "¡Hola! 👋 Bienvenido/a al sistema de acceso automático para el **Grupo VIP**.\n\n"
        "Para ingresar, el primer paso es crearte una cuenta usando nuestro enlace oficial.\n\n"
        "🎬 **Mirá el video de abajo paso a paso antes de registrarte** para asegurarte de hacerlo bien. "
        "Luego, tocá el botón para crear tu cuenta:"
    )
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")

    if VIDEO_FILE_ID:
        try:
            bot.send_video(chat_id, VIDEO_FILE_ID, caption="🎬 Tutorial completo de registro paso a paso.")
        except Exception as e:
            logger.error(f"No se pudo enviar el video a {chat_id}: {e}")
    else:
        logger.warning("VIDEO_FILE_ID no está configurado, no se envía video")


# ----------------------- 2. Pide el ID -----------------------
@bot.callback_query_handler(func=lambda call: call.data == "pedir_id_registro")
def pedir_id_registro(call):
    chat_id = call.message.chat.id
    upsert_usuario(chat_id, step=2, last_interaction=time.time(), seguimientos_enviados=0)
    bot.answer_callback_query(call.id)  # saca el "relojito" de carga del botón
    bot.send_message(
        chat_id,
        "📝 Por favor, **escribí tu ID de la plataforma** acá abajo para verificar que tu cuenta se haya creado "
        "correctamente con nuestro enlace:",
        parse_mode="Markdown",
    )


# ----------------------- 3. Procesa el ID -----------------------
@bot.message_handler(func=lambda msg: not msg.text.startswith('/'), content_types=['text'])
def procesar_texto(message):
    chat_id = message.chat.id
    guardar_mensaje(chat_id, message.text)
    usuario = get_usuario(chat_id)
    if not usuario:
        return

    id_ingresado = message.text.strip()

    if usuario.get('step') == 2:
        if trader_registrado(id_ingresado):
            upsert_usuario(chat_id, step=3, last_interaction=time.time(), trader_id=id_ingresado, seguimientos_enviados=0)

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🆔 Ya deposité, ingresar al VIP", callback_data="verificar_id_deposito"))

            texto_depo = (
                "✅ **Registro confirmado**\n\n"
                "Para unirte al canal VIP y acceder a nuestras mentorías privadas diarias (en TikTok y por mensaje), "
                "solo necesitas realizar una inversión en tu cuenta. Puedes comenzar con cualquier cantidad que te "
                "resulte cómoda. Esta inversión es completamente tuya, no es una cuota fija, y puedes retirarla en "
                "cualquier momento.❗️❗️"
            )
            bot.send_message(chat_id, texto_depo, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(
                chat_id,
                "❌ **El ID ingresado aún no aparece en nuestros registros de afiliados.**\n\n"
                "Asegurate de haber completado tu registro con el enlace oficial del paso 1. "
                "Si lo acabás de hacer, aguardá un minutito y **volvé a escribir tu ID** aquí abajo para reintentar:",
                parse_mode="Markdown",
            )


# ----------------------- 4. Verifica el depósito -----------------------
@bot.callback_query_handler(func=lambda call: call.data == "verificar_id_deposito")
def verificar_id_deposito(call):
    chat_id = call.message.chat.id
    usuario = get_usuario(chat_id)
    trader_id = usuario.get('trader_id') if usuario else None

    if not trader_id:
        bot.send_message(chat_id, "Por favor, ingresá tu ID de registro primero usando /start.")
        return

    if trader_depositado(trader_id):
        texto_exito = (
            "🎉 ¡Cuenta Verificada Automáticamente! 🎉\n\n"
            "Comprobamos tu registro y depósito correctamente. Podés unirte al canal VIP ingresando al "
            f"siguiente enlace:\n\n{LINK_GRUPO_VIP}\n\n"
            "¡Bienvenido al equipo!"
        )
        bot.send_message(chat_id, texto_exito)
        upsert_usuario(chat_id, step=4, last_interaction=time.time())
        logger.info(f"Usuario {chat_id} (trader {trader_id}) accedió al VIP")
    else:
        bot.send_message(
            chat_id,
            "❌ **Tu ID aún no registra la inversión mínima en el sistema.**\n\n"
            "Recuerda que el proceso puede tardar unos minutos en impactar tras realizar el depósito. "
            "Si ya lo hiciste, aguardá un momento y volvé a tocar el botón de verificar.",
            parse_mode="Markdown",
        )


# ----------------------- COMANDO DE ADMIN: RECORDATORIO MANUAL -----------------------
# Solo vos (MI_TELEGRAM_ID) podés usar este comando.
# Manda un mensaje a todos los que están en step=3 (registrados, sin depositar todavía).
@bot.message_handler(commands=['avisar_deposito'])
def avisar_deposito(message):
    if message.chat.id != MI_TELEGRAM_ID:
        return  # ignora silenciosamente si no sos vos

    texto_recordatorio = (
        "Ya diste el primer paso registrándote — no dejes pasar la oportunidad de empezar esta semana. "
        "Solo falta tu depósito para tener acceso completo al VIP. ¿Ya lo hiciste?"
    )

    try:
        res = supabase.table("usuarios").select("*").eq("step", 3).execute()
        usuarios = res.data
    except Exception as e:
        bot.reply_to(message, f"Error consultando usuarios: {e}")
        return

    enviados = 0
    fallidos = 0
    for usuario in usuarios:
        try:
            bot.send_message(usuario["chat_id"], texto_recordatorio)
            enviados += 1
        except Exception as e:
            logger.error(f"No se pudo avisar a {usuario['chat_id']}: {e}")
            fallidos += 1

    bot.reply_to(message, f"✅ Recordatorio enviado a {enviados} personas. Fallidos: {fallidos}.")
    logger.info(f"Recordatorio manual de depósito: {enviados} enviados, {fallidos} fallidos")


# ----------------------- SECUENCIA DE SEGUIMIENTO -----------------------
# Cada elemento: (segundos desde la última interacción, texto del mensaje)
# EDITÁ estos textos con contenido real tuyo (testimonios/resultados que vos
# tengas y puedas mostrar). Los que dejé acá son genéricos, a modo de ejemplo.
SEGUIMIENTOS = [
    (
        7200,  # 2 horas sin avanzar
        "👋 ¡Hola! Vi que te interesó sumarte a nuestra comunidad VIP pero no completaste "
        "los pasos. 📈\n\n"
        "Tocá abajo para continuar donde te quedaste:",
    ),
    (
        86400,  # 24 horas sin avanzar
        "PLACEHOLDER: acá va tu segundo mensaje de seguimiento. Reemplazá este texto por "
        "contenido real (por ejemplo, algo que ya le hayas mostrado a otros interesados).",
    ),
    (
        259200,  # 72 horas sin avanzar
        "PLACEHOLDER: tercer y último mensaje de seguimiento. Ajustalo vos con contenido real.",
    ),
]


def verificar_usuarios_colgados():
    CHEQUEO_SEGUNDOS = 300

    while True:
        time.sleep(CHEQUEO_SEGUNDOS)
        ahora = time.time()
        try:
            res = supabase.table("usuarios").select("*").in_("step", [1, 2, 3]).execute()
            for usuario in res.data:
                chat_id = usuario["chat_id"]
                enviados = usuario.get("seguimientos_enviados", 0)
                if enviados >= len(SEGUIMIENTOS):
                    continue  # ya se mandaron todos los mensajes de la secuencia

                umbral_segundos, texto = SEGUIMIENTOS[enviados]
                if ahora - usuario["last_interaction"] > umbral_segundos:
                    try:
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("🚀 Continuar proceso", callback_data="pedir_id_registro"))
                        bot.send_message(chat_id, texto, reply_markup=markup)
                        upsert_usuario(chat_id, seguimientos_enviados=enviados + 1)
                        logger.info(f"Seguimiento #{enviados + 1} enviado a {chat_id}")
                    except Exception as e:
                        logger.error(f"Error mandando seguimiento a {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Error revisando usuarios colgados: {e}")


@app.route('/')
def home():
    return "Bot VIP activo (Supabase)", 200


if __name__ == "__main__":
    try:
        bot.delete_webhook()
    except Exception as e:
        logger.error(f"Error borrando webhook viejo: {e}")

    threading.Thread(
        target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types),
        daemon=True,
    ).start()
    threading.Thread(target=verificar_usuarios_colgados, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
