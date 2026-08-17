import os
import time
import threading
from flask import Flask, request
import telebot
from supabase import create_client, Client

# --- CONFIGURACIÓN Y VARIABLES DE ENTORNO ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
LINK_REGISTRO = os.environ.get("LINK_REGISTRO")
LINK_GRUPO_VIP = os.environ.get("LINK_GRUPO_VIP")
VIP_GROUP_ID = os.environ.get("VIP_GROUP_ID")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# Conexión a Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FUNCIONES DE BASE DE DATOS ---

def get_usuario(chat_id):
    try:
        res = supabase.table("usuarios").select("chat_id, step, trader_id, last_interaction, reminded, seguimientos_enviados").eq("chat_id", chat_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"Error en get_usuario: {e}")
        return None

def upsert_usuario(chat_id, step=1, trader_id=None, reminded=False, seguimientos_enviados=0):
    try:
        actual = get_usuario(chat_id) or {}
        data = {
            "chat_id": chat_id,
            "step": step,
            "last_interaction": time.time(),
            "reminded": reminded,
            "trader_id": trader_id if trader_id is not None else actual.get("trader_id"),
            "seguimientos_enviados": seguimientos_enviados
        }
        supabase.table("usuarios").upsert(data).execute()
    except Exception as e:
        print(f"Error en upsert_usuario: {e}")

def get_trader(trader_id):
    try:
        trader_id_str = str(trader_id).strip()
        res = supabase.table("traders").select("trader_id, registrado, depositado").eq("trader_id", trader_id_str).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"Error en get_trader: {e}")
        return None

def marcar_trader(trader_id, registrado=False, depositado=False):
    try:
        trader_id_str = str(trader_id).strip()
        res = get_trader(trader_id_str)
        if res:
            data_update = {}
            if registrado:
                data_update["registrado"] = True
            if depositado:
                data_update["depositado"] = True
            if data_update:
                supabase.table("traders").update(data_update).eq("trader_id", trader_id_str).execute()
        else:
            supabase.table("traders").insert({
                "trader_id": trader_id_str,
                "registrado": registrado,
                "depositado": depositado
            }).execute()
        return True
    except Exception as e:
        print(f"Error en marcar_trader: {e}")
        return False

# --- WEBHOOK / POSTBACK FLASK ---

@app.route('/postback', methods=['GET', 'POST'])
def affiliate_postback():
    trader_id = request.args.get('trader_id') or request.form.get('trader_id')
    event = request.args.get('event') or request.form.get('event')

    if not trader_id or not event:
        return "Missing parameters", 400

    trader_id = str(trader_id).strip()
    event = event.lower().strip()

    if event == 'registro':
        marcar_trader(trader_id, registrado=True)
        msg = f"🔔 *NUEVO REGISTRO CONFIRMADO*\n\nTrader ID: `{trader_id}`"
    elif event in ['deposito', 'deposit', 'ftd']:
        marcar_trader(trader_id, registrado=True, depositado=True)
        msg = f"💰 *NUEVO DEPÓSITO CONFIRMADO*\n\nTrader ID: `{trader_id}`"
    else:
        return "Unknown event", 400

    if ADMIN_ID:
        try:
            bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error enviando notificación al admin: {e}")

    return "OK", 200

@app.route('/')
def index():
    return "Bot Nati Running", 200

# --- HANDLERS DEL BOT DE TELEGRAM ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    upsert_usuario(chat_id, step=1)

    text = (
        "¡Hola! 👋 Bienvenido/a al canal VIP de señales.\n\n"
        "Para acceder 100% gratis, tenés que seguir estos sencillos pasos:\n\n"
        "1️⃣ Crearte una cuenta desde nuestro enlace de registro oficial.\n"
        "2️⃣ Enviarme tu **ID de Trader** por acá para verificarlo.\n"
        "3️⃣ Realizar tu primer depósito para activar la cuenta.\n\n"
        "Tocá en el botón de abajo para registrarte 👇"
    )

    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🔗 Registrarme Ahora", url=LINK_REGISTRO))
    markup.add(telebot.types.InlineKeyboardButton("✅ Ya me registré, verificar mi ID", callback_data="verificar_id"))

    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "verificar_id")
def callback_verificar(call):
    chat_id = call.message.chat.id
    upsert_usuario(chat_id, step=2)
    bot.send_message(chat_id, "Por favor, escribí y enviá tu **ID de Trader** (números solamente):", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def process_id(message):
    chat_id = message.chat.id
    usr = get_usuario(chat_id)

    if usr and usr.get("step") == 2:
        trader_id = message.text.strip()

        if not trader_id.isdigit():
            bot.send_message(chat_id, "❌ Por favor enviá un ID válido compuesto solo por números.")
            return

        upsert_usuario(chat_id, step=3, trader_id=trader_id)
        trader_info = get_trader(trader_id)

        if trader_info and trader_info.get("depositado"):
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🚀 ENTRAR AL CANAL VIP", url=LINK_GRUPO_VIP))
            bot.send_message(chat_id, "✅ ¡Felicidades! Tu ID y depósito están confirmados.\n\nPodés ingresar al VIP desde aquí:", reply_markup=markup)
        elif trader_info and trader_info.get("registrado"):
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🆔 Ya deposité, verificar mi ID", callback_data="verificar_deposito"))
            bot.send_message(
                chat_id,
                f"✅ Tu registro con ID `{trader_id}` está confirmado.\n\n"
                "📌 **Siguiente paso:** Hacé tu primer depósito en la plataforma para activar tu acceso al VIP.",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            bot.send_message(
                chat_id,
                f"❌ El ID `{trader_id}` aún no aparece registrado en nuestro sistema.\n\n"
                "Asegurate de haber creado la cuenta desde nuestro enlace de registro y aguardá unos minutos.",
                parse_mode="Markdown"
            )

@bot.callback_query_handler(func=lambda call: call.data == "verificar_deposito")
def callback_verificar_deposito(call):
    chat_id = call.message.chat.id
    usr = get_usuario(chat_id)
    trader_id = usr.get("trader_id") if usr else None

    if not trader_id:
        bot.send_message(chat_id, "No tengo registrado tu ID. Por favor mandá tu ID de trader nuevamente.")
        upsert_usuario(chat_id, step=2)
        return

    trader_info = get_trader(trader_id)
    if trader_info and trader_info.get("depositado"):
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("🚀 ENTRAR AL CANAL VIP", url=LINK_GRUPO_VIP))
        bot.send_message(chat_id, "✅ ¡Excelente! Tu depósito fue verificado con éxito.\n\nHacé clic abajo para unirte al VIP:", reply_markup=markup)
    else:
        bot.send_message(
            chat_id,
            f"⏳ Tu depósito para el ID `{trader_id}` todavía no impactó en el sistema.\n\n"
            "Si ya lo realizaste, aguardá unos minutos y volvé a presionar el botón.",
            parse_mode="Markdown"
        )

# --- EJECUCIÓN CON SERVIDOR FLASK EN HILO SECUNDARIO ---

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.remove_webhook()
    bot.infinity_polling()
