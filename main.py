import os
import telebot
from telebot import types
from flask import Flask, request
import threading
import time

# CONFIGURACIÓN ESENCIAL (Se lee de forma segura desde Render)
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8943668513:AAHnPjS7ZfHUBlS7VpKi35hK6dJpLrEmbk0')
MI_TELEGRAM_ID = int(os.environ.get('ADMIN_ID', 1630411628))

# ENLACES OFICIALES YA INTEGRADOS
LINK_REGISTRO = "https://stockity-r3.com?a=9e29d7ed3cab&t=0"
LINK_GRUPO_VIP = "https://t.me/+CwS4WQkN6c80YTYx"
LINK_VIDEO_DRIVE = "https://docs.google.com/uc?export=download&id=16drzdOYhjaR5tVcWWwM77Sqn7RQ-v72H"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Base de datos temporal en memoria para guardar los ID que depositan
traders_aprobados = set()
user_data = {}  # Guarda el estado del usuario y la hora de su última interacción

# Función para actualizar la interacción del usuario
def actualizar_usuario(chat_id, step):
    user_data[chat_id] = {
        'step': step,
        'last_interaction': time.time(),
        'reminded': False  # Para no spamear más de una vez
    }

# 📥 WEBHOOK / POSTBACK: Aquí golpea la puerta Affiliate Top
@app.route('/postback', methods=['GET'])
def affiliate_postback():
    trader_id = request.args.get('trader_id')
    evento = request.args.get('event', 'deposito') # Registro o Depósito
    
    if trader_id:
        trader_id = trader_id.strip()
        traders_aprobados.add(trader_id)
        
        # Aviso silencioso a tu Telegram para que sepas que entró un dato
        try:
            bot.send_message(MI_TELEGRAM_ID, f"💰 ¡Postback Recibido!\nID de Trader: {trader_id} realizó un {evento}.")
        except Exception:
            pass
            
    return "OK", 200

# 1. BIENVENIDA DEL BOT
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    actualizar_usuario(chat_id, 1)
    
    markup = types.InlineKeyboardMarkup()
    btn_registro = types.InlineKeyboardButton("🔗 Registrarme en la Plataforma", url=LINK_REGISTRO)
    btn_siguiente = types.InlineKeyboardButton("✅ Ya me registré, ¿cómo depósito?", callback_data="paso_deposito")
    markup.add(btn_registro)
    markup.add(btn_siguiente)
    
    texto = (
        "¡Hola! 👋 Bienvenido/a al sistema de acceso automático para el **Grupo VIP**.\n\n"
        "Para ingresar, el primer paso es crearte una cuenta usando nuestro enlace oficial.\n\n"
        "👉 Tocá el botón de abajo para registrarte:"
    )
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")

# 2. EXPLICACIÓN DEL DEPÓSITO (TEXTO ACTUALIZADO)
@bot.callback_query_handler(func=lambda call: call.data == "paso_deposito")
def paso_deposito(call):
    chat_id = call.message.chat.id
    actualizar_usuario(chat_id, 2)
    
    markup = types.InlineKeyboardMarkup()
    btn_id = types.InlineKeyboardButton("🆔 Ya deposité, ingresar mi ID", callback_data="pedir_id")
    markup.add(btn_id)
    
    # Tu texto personalizado integrado
    texto = (
        "✅ **Registro confirmado**\n\n"
        "Para unirte al canal VIP y acceder a nuestras mentorías privadas diarias (en TikTok y por mensaje), "
        "solo necesitas realizar una inversión en tu cuenta. Puedes comenzar con cualquier cantidad que te resulte cómoda. "
        "Esta inversión es completamente tuya, no es una cuota fija, y puedes retirarla en cualquier momento.❗️❗️"
    )
    bot.edit_message_text(texto, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# 3. PEDIR EL ID + ENVIAR VIDEO EXPLICATIVO
@bot.callback_query_handler(func=lambda call: call.data == "pedir_id")
def pedir_id(call):
    chat_id = call.message.chat.id
    actualizar_usuario(chat_id, 3)
    
    bot.edit_message_text(
        "📝 Te dejo un video cortito para que veas exactamente dónde encontrar tu ID en la plataforma. "
        "Miralo y escribí tu número acá abajo:", 
        chat_id, 
        call.message.message_id
    )
    
    # Enviamos el video de Drive convertido a descarga directa
    try:
        bot.send_video(chat_id, LINK_VIDEO_DRIVE, caption="🎬 Mirá acá cómo ver tu Trader ID.")
    except Exception:
        bot.send_message(chat_id, "💡 Podés encontrar tu ID entrando a tu perfil en la esquina superior de la plataforma de trading.")

# 4. CAPTURA DEL ID Y VERIFICACIÓN AUTOMÁTICA
@bot.message_handler(func=lambda msg: True, content_types=['text'])
def verificar_id_automatico(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('step') != 3:
        return
        
    id_ingresado = message.text.strip()
    
    if id_ingresado in traders_aprobados:
        texto_exito = (
            "🎉 ¡Cuenta Verificada Automáticamente! 🎉\n\n"
            "Comprobamos tu registro y depósito correctamente. Podés unirte al canal VIP ingresando al siguiente enlace:\n\n"
            f"{LINK_GRUPO_VIP}\n\n"
            "¡Bienvenido al equipo!"
        )
        bot.send_message(chat_id, texto_exito)
        actualizar_usuario(chat_id, 4)  # Estado Completado
    else:
        texto_error = (
            "❌ **El ID ingresado aún no registra el depósito mínimo.**\n\n"
            "Recuerde que el proceso puede tardar unos minutos en impactar. "
            "Asegúrese de haber realizado el depósito correctamente bajo nuestro enlace.\n\n"
            "Si ya lo hizo, aguarde un momento y **vuelva a escribir su ID** aquí para reintentar:"
        )
        bot.send_message(chat_id, texto_error, parse_mode="Markdown")

# ⏰ RECORDATORIO AUTOMÁTICO (Corre de fondo en el servidor cada 1 hora)
def verificar_usuarios_colgados():
    while True:
        time.sleep(3600)  # Revisa cada 60 minutos
        ahora = time.time()
        
        for chat_id, data in list(user_data.items()):
            # Si el usuario abrió el bot pero se quedó colgado en pasos previos por más de 2 horas
            if data['step'] in [1, 2, 3] and not data['reminded']:
                if ahora - data['last_interaction'] > 7200:  # 2 horas de inactividad
                    try:
                        markup = types.InlineKeyboardMarkup()
                        btn_reintentar = types.InlineKeyboardButton("🆔 Enviar mi ID ahora", callback_data="pedir_id")
                        markup.add(btn_reintentar)
                        
                        texto_reminder = (
                            "👋 ¡Hola! Vi que te interesó sumarte a nuestra comunidad VIP pero no completaste los pasos. 📈\n\n"
                            "Recordá que los cupos semanales son limited y te estás perdiendo las operaciones.\n\n"
                            "Si tuviste alguna duda con tu ID o el depósito, tocá abajo y lo resolvemos al toque:"
                        )
                        bot.send_message(chat_id, texto_reminder, reply_markup=markup)
                        user_data[chat_id]['reminded'] = True  # Marcamos para que no vuelva a molestar
                    except Exception:
                        pass

# Entrada para el servidor de Render
@app.route('/')
def home():
    return "Bot VIP Líquido y Activo 24/7", 200

if __name__ == "__main__":
    bot.remove_webhook()
    
    # Hilo para el bot de Telegram
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types)).start()
    
    # Hilo para el sistema de recordatorios automáticos
    threading.Thread(target=verificar_usuarios_colgados, daemon=True).start()
    
    # Servidor Web
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
