import os
import json
import time
import logging
import threading

import telebot
from telebot import types
from flask import Flask, request

# ----------------------- CONFIG -----------------------
# El bot NO arranca si faltan estas variables de entorno.
# En Render: Settings -> Environment -> agregá TELEGRAM_TOKEN y ADMIN_ID.
TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_ID_RAW = os.environ.get('ADMIN_ID')

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno TELEGRAM_TOKEN")
if not ADMIN_ID_RAW:
    raise RuntimeError("Falta la variable de entorno ADMIN_ID")

MI_TELEGRAM_ID = int(ADMIN_ID_RAW)

# Enlaces (estos no son secretos, está bien que queden en el código)
LINK_REGISTRO = os.environ.get('LINK_REGISTRO', "https://stockity-r3.com?a=9e29d7ed3cab&t=0")
LINK_GRUPO_VIP = os.environ.get('LINK_GRUPO_VIP', "https://t.me/+CwS4WQkN6c80YTYx")
VIDEO_FILE_ID = os.environ.get('VIDEO_FILE_ID', "")

DATA_FILE = "data.json"

# ----------------------- LOGGING -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("bot_vip")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ----------------------- PERSISTENCIA SIMPLE (JSON) -----------------------
# Evita perder todo si Render reinicia el servicio.
# Para volúmenes más grandes de usuarios, conviene pasar a SQLite/Postgres,
# pero para empezar esto alcanza y no agrega infraestructura.

_lock = threading.Lock()


def cargar_datos():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                data["user_data"] = {int(k): v for k, v in data.get("user_data", {}).items()}
                data["traders_registrados"] = set(data.get("traders_registrados", []))
                data["traders_depositados"] = set(data.get("traders_depositados", []))
                return data
        except Exception as e:
            logger.error(f"Error cargando {DATA_FILE}: {e}")
    return {"user_data": {}, "traders_registrados": set(), "traders_depositados": set()}


def guardar_datos():
    with _lock:
        try:
            with open(DATA_FILE, "w") as f:
                json.dump({
                    "user_data": user_data,
                    "traders_registrados": list(traders_registrados),
                    "traders_depositados": list(traders_depositados),
                }, f)
        except Exception as e:
            logger.error(f"Error guardando {DATA_FILE}: {e}")


_estado = cargar_datos()
user_data = _estado["user_data"]
traders_registrados = _estado["traders_registrados"]
traders_depositados = _estado["traders_depositados"]


def actualizar_usuario(chat_id, step):
    user_data[chat_id] = {
        'step': step,
        'last_interaction': time.time(),
        'reminded': False,
        'trader_id': user_data.get(chat_id, {}).get('trader_id'),
    }
    guardar_datos()


# ----------------------- CAPTURADOR DE FILE ID -----------------------
@bot.message_handler(content_types=['video'])
def capturar_file_id(message):
    file_id = message.video.file_id
    logger.info(f"Video recibido, file_id: {file_id}")
    bot.reply_to(
        message,
        f"✅ Video recibido. file_id:\n`{file_id}`",
        parse_mode="Markdown",
    )


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
        traders_registrados.add(trader_id)
    elif evento == 'deposito':
        traders_depositados.add(trader_id)
        traders_registrados.add(trader_id)
    else:
        logger.warning(f"Evento desconocido en postback: {evento}")
        return "evento inválido", 400

    guardar_datos()
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
    actualizar_usuario(chat_id, 1)
    logger.info(f"Nuevo /start de {chat_id}")

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔗 Registrarme en la Plataforma", url=LINK_REGISTRO))
    markup.add(types.InlineKeyboardButton("✅ Ya me registré, verificar mi ID", callback_data="pedir_id_registro"))

    texto = (
        "¡Hola! 👋 Bienvenido/a al sistema de acceso al Grupo VIP.\n\n"
        "Para ingresar, el primer paso es crear tu cuenta con nuestro enlace oficial.\n\n"
        "Mirá el video de abajo antes de registrarte. Luego tocá el botón para crear tu cuenta:"
    )
    bot.send_message(chat_id, texto, reply_markup=markup)

    if VIDEO_FILE_ID:
        try:
            bot.send_video(chat_id, VIDEO_FILE_ID, caption="Tutorial de registro paso a paso.")
        except Exception as e:
            logger.error(f"No se pudo enviar el video a {chat_id}: {e}")


# ----------------------- 2. Pide el ID -----------------------
@bot.callback_query_handler(func=lambda call: call.data == "pedir_id_registro")
def pedir_id_registro(call):
    chat_id = call.message.chat.id
    actualizar_usuario(chat_id, 2)
    bot.edit_message_text(
        "Escribí tu ID de la plataforma acá abajo para verificar tu registro:",
        chat_id,
        call.message.message_id,
    )


# ----------------------- 3. Procesa el ID -----------------------
@bot.message_handler(func=lambda msg: True, content_types=['text'])
def procesar_texto(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        return

    id_ingresado = message.text.strip()
    step_actual = user_data[chat_id].get('step')

    if step_actual == 2:
        if id_ingresado in traders_registrados:
            user_data[chat_id]['step'] = 3
            user_data[chat_id]['last_interaction'] = time.time()
            user_data[chat_id]['trader_id'] = id_ingresado
            guardar_datos()

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Ya deposité, ingresar al VIP", callback_data="verificar_id_deposito"))

            bot.send_message(
                chat_id,
                "Registro confirmado ✅\n\nPara unirte al grupo VIP, realizá una inversión en tu cuenta.",
                reply_markup=markup,
            )
        else:
            bot.send_message(
                chat_id,
                "El ID ingresado aún no aparece en nuestros registros.\n"
                "Si acabás de registrarte, esperá un momento y volvé a escribir tu ID.",
            )


# ----------------------- 4. Verifica el depósito -----------------------
@bot.callback_query_handler(func=lambda call: call.data == "verificar_id_deposito")
def verificar_id_deposito(call):
    chat_id = call.message.chat.id
    trader_id = user_data.get(chat_id, {}).get('trader_id')

    if not trader_id:
        bot.send_message(chat_id, "Por favor, ingresá tu ID de registro primero usando /start.")
        return

    if trader_id in traders_depositados:
        bot.send_message(
            chat_id,
            f"Cuenta verificada ✅. Podés unirte al canal VIP acá:\n\n{LINK_GRUPO_VIP}",
        )
        actualizar_usuario(chat_id, 4)
        logger.info(f"Usuario {chat_id} (trader {trader_id}) accedió al VIP")
    else:
        bot.send_message(
            chat_id,
            "Tu ID aún no registra la inversión mínima. Esperá unos minutos tras el depósito y volvé a intentar.",
        )


# ----------------------- RECORDATORIO AUTOMÁTICO -----------------------
def verificar_usuarios_colgados():
    CHEQUEO_SEGUNDOS = 300       # revisa cada 5 min (antes: 1 hora)
    UMBRAL_SEGUNDOS = 7200       # recuerda tras 2hs sin avanzar

    while True:
        time.sleep(CHEQUEO_SEGUNDOS)
        ahora = time.time()
        for chat_id, data in list(user_data.items()):
            if data.get('step') in [1, 2, 3] and not data.get('reminded'):
                if ahora - data['last_interaction'] > UMBRAL_SEGUNDOS:
                    try:
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("Continuar proceso", callback_data="pedir_id_registro"))
                        bot.send_message(
                            chat_id,
                            "Viste que empezaste el proceso para el VIP pero no lo terminaste. "
                            "Tocá abajo para continuar donde quedaste:",
                            reply_markup=markup,
                        )
                        user_data[chat_id]['reminded'] = True
                        guardar_datos()
                        logger.info(f"Recordatorio enviado a {chat_id}")
                    except Exception as e:
                        logger.error(f"Error mandando recordatorio a {chat_id}: {e}")


@app.route('/')
def home():
    return "Bot VIP activo", 200


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
