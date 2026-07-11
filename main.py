import os
import telebot
from telebot import types
from flask import Flask, request
import threading
import time

# CONFIGURACIÓN ESENCIAL (Se lee de forma segura desde Render)
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8943668513:AAHnPjS7ZfHUBlS7VpKi35hK6dJpLrEmbk0')
MI_TELEGRAM_ID = int(os.environ.get('ADMIN_ID', 1630411628))

# ENLACES OFICIALES INTEGRADOS
LINK_REGISTRO = "https://stockity-r3.com?a=9e29d7ed3cab&t=0"
LINK_GRUPO_VIP = "https://t.me/+CwS4WQkN6c80YTYx"

# 🎬 PEGA AQUÍ EL FILE ID CUANDO EL BOT TE LO ENVIE
VIDEO_FILE_ID = "TU_FILE_ID_DE_TELEGRAM_AQUI"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Listas para guardar lo que llega de Affiliate Top
traders_registrados = set()
traders_depositados = set()
user_data = {}

def actualizar_usuario(chat_id, step):
    user_data[chat_id] = {
        'step': step,
        'last_interaction': time.time(),
        'reminded': False
    }

# 🛠️ CAPTURADOR DE FILE ID MEJORADO (Responde directo en el chat sin importar el ID)
@bot.message_handler(content_types=['video'])
def capturar_file_id(message):
    file_id = message.video.file_id
    text_id = (
        "✅ **¡VIDEO RECIBIDO EN EL SERVIDOR!**\n\n"
        "Copiá este código largo de abajo y pegalo en la línea 15 de tu GitHub:\n\n"
        f"`{file_id}`"
    )
    bot.reply_to(message, text_id, parse_mode="Markdown")

# 📥 WEBHOOK / POSTBACK: Recibe alertas de Affiliate Top
@app.route('/postback', methods=['GET'])
def affiliate_postback():
    trader_id = request.args.get('trader_id')
    evento = request.args.get('event', 'registro')
    
    if trader_id:
        trader_id = trader_id.strip()
        if evento == 'registro':
            traders_registrados.add(trader_id)
        elif evento == 'deposito':
            traders_depositados.add(trader_id)
            traders_registrados.add(trader_id)
        
        try:
            bot.send_message(MI_TELEGRAM_ID, f"💰 ¡Postback Recibido!\nID de Trader: {trader_id} realizó un {evento}.")
        except Exception:
            pass
            
    return "OK", 200

# 1. BIENVENIDA DEL BOT + ENVÍO DEL VIDEO TUTORIAL COMPLETO
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    actualizar_usuario(chat_id, 1)
    
    markup = types.InlineKeyboardMarkup()
    btn_registro = types.InlineKeyboardButton("🔗 Registrarme en la Plataforma", url=LINK_REGISTRO)
    btn_siguiente = types.InlineKeyboardButton("✅ Ya me registré, verificar mi ID", callback_data="pedir_id_registro")
    markup.add(btn_registro)
    markup.add(btn_siguiente)
    
    texto = (
        "¡Hola! 👋 Bienvenido/a al sistema de acceso automático para el **Grupo VIP**.\n\n"
        "Para ingresar, el primer paso es crearte una cuenta usando nuestro enlace oficial.\n\n"
        "🎬 **Mirá el video de abajo paso a paso antes de registrarte** para asegurarte de hacerlo bien. "
        "Luego, tocá el botón para crear tu cuenta:"
    )
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")
    
    if VIDEO_FILE_ID != "TU_FILE_ID_DE_TELEGRAM_AQUI":
        try:
            bot.send_video(chat_id, VIDEO_FILE_ID, caption="🎬 Tutorial completo de registro paso a paso.")
        except Exception:
            pass

# 2. BOT PIDE EL ID PARA VERIFICAR EL REGISTRO
@bot.callback_query_handler(func=lambda call: call.data == "pedir_id_registro")
def pedir_id_registro(call):
    chat_id = call.message.chat.id
    actualizar_usuario(chat_id, 2)
    
    bot.edit_message_text(
        "📝 Por favor, **escribí tu ID de la plataforma** acá abajo para verificar que tu cuenta se haya creado correctamente con nuestro enlace:", 
        chat_id, 
        call.message.message_id,
        parse_mode="Markdown"
    )

# 3. PROCESA EL ID Y PIDE EL DEPÓSITO
@bot.message_handler(func=lambda msg: True, content_types=['text'])
def procesar_texto(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        return
        
    id_ingresado = message.text.strip()
    step_actual = user_data[chat_id].get('step')
    
    if step_actual == 2:
        if id_ingresado in traders_registrados:
            user_data[chat_id]['trader_id'] = id_ingresado
            actualizar_usuario(chat_id, 3)
            
            markup = types.InlineKeyboardMarkup()
            btn_verificar_depo = types.InlineKeyboardButton("🆔 Ya deposité, ingresar al VIP", callback_data="verificar_id_deposito")
            markup.add(btn_verificar_depo)
            
            texto_depo = (
                "✅ **Registro confirmado**\n\n"
                "Para unirte al canal VIP y acceder a nuestras mentorías privadas diarias (en TikTok y por mensaje), "
                "solo necesitas realizar una inversión en tu cuenta. Puedes comenzar con cualquier cantidad que te resulte cómoda. "
                "Esta inversión es completamente tuya, no es una cuota fija, y puedes retirarla en cualquier momento.❗️❗️"
            )
            bot.send_message(chat_id, texto_depo, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(
                chat_id,
                "❌ **El ID ingresado aún no aparece en nuestros registros de afiliados.**\n\n"
                "Asegurate de haber completado tu registro con el enlace oficial del paso 1. "
                "Si lo acabás de hacer, aguardá un minutito y **volvé a escribir tu ID** aquí abajo para reintentar:"
            )

# 4. BOTÓN CUANDO YA DEPOSITÓ
@bot.callback_query_handler(func=lambda call: call.data == "verificar_id_deposito")
def verificar_id_deposito(call):
    chat_id = call.message.chat.id
    trader_id = user_data.get(chat_id, {}).get('trader_id')
    
    if not trader_id:
        bot.send_message(chat_id, "Por favor, ingresá tu ID de registro primero usando /start.")
        return
        
    if trader_id in traders_depositados:
        texto_exito = (
            "🎉 ¡Cuenta Verificada Automáticamente! 🎉\n\n"
            "Comprobamos tu registro y depósito correctamente. Podés unirte al canal VIP ingresando al siguiente enlace:\n\n"
            f"{LINK_GRUPO_VIP}\n\n"
            "¡Bienvenido al equipo!"
        )
        bot.send_message(chat_id, texto_exito)
        actualizar_usuario(chat_id, 4)
    else:
        bot.send_message(
            chat_id,
            "❌ **Tu ID aún no registra la inversión mínima en el sistema.**\n\n"
            "Recuerda que el proceso puede tardar unos minutos en impactar tras realizar el depósito. "
            "Si ya lo hiciste, aguardá un momento y volvé a tocar el botón de verificar."
        )

# ⏰ RECORDATORIO AUTOMÁTICO
def verificar_usuarios_colgados():
    while True:
        time.sleep(3600)
        ahora = time.time()
        for chat_id, data in list(user_data.items()):
            if data['step'] in [1, 2, 3] and not data['reminded']:
                if ahora - data['last_interaction'] > 7200:
                    try:
                        markup = types.InlineKeyboardMarkup()
                        btn_reintentar = types.InlineKeyboardButton("🚀 Continuar proceso", callback_data="pedir_id_registro")
                        markup.add(btn_reintentar)
                        
                        texto_reminder = (
                            "👋 ¡Hola! Vi que te interesó sumarte a nuestra comunidad VIP pero no completaste los pasos. 📈\n\n"
                            "Recordá que los cupos semanales son limitados y te estás perdiendo las operaciones.\n\n"
                            "Tocá abajo para continuar donde te quedaste:"
                        )
                        bot.send_message(chat_id, texto_reminder, reply_markup=markup)
                        user_data[chat_id]['reminded'] = True
                    except Exception:
                        pass

@app.route('/')
def home():
    return "Bot VIP con Captura Directa Activo", 200

if __name__ == "__main__":
    # Forzamos a borrar cualquier conexión vieja de Telegram para liberar el bot
    try:
        bot.delete_webhook()
    except Exception:
        pass
        
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types)).start()
    threading.Thread(target=verificar_usuarios_colgados, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
