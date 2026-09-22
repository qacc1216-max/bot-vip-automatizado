import os
import telebot
from telebot import types
from flask import Flask, request
import threading
import time

# CONFIGURACIÓN ESENCIAL
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8943668513:AAHnPjS7ZfHUBlS7VpKi35hK6dJpLrEmbk0')
MI_TELEGRAM_ID = int(os.environ.get('ADMIN_ID', 1630411628))

# ENLACES OFICIALES
LINK_REGISTRO = "https://stockity-r3.com?a=9e29d7ed3cab&t=0"
LINK_GRUPO_VIP = "https://t.me/+8E9efv0SxMlhNGI5"
VIDEO_FILE_ID = "BAACAgEAAxkBAAMialGwteT-YHVgaHhNTRPl5aReFucAAloIAAKgVpFGObGcQkEezi88BA"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Listas de memoria
traders_registrados = set()
traders_depositados = set()
user_data = {}
chats_conocidos = set()

def actualizar_usuario(chat_id, step):
    chats_conocidos.add(chat_id)
    user_data[chat_id] = {
        'step': step,
        'last_interaction': time.time(),
        'reminded': False
    }

# 🎬 CAPTURADOR DE FILE ID (Por si querés mandarle videos nuevos)
@bot.message_handler(content_types=['video'])
def capturar_file_id(message):
    file_id = message.video.file_id
    bot.reply_to(message, f"✅ **FILE ID:**\n\n`{file_id}`", parse_mode="Markdown")

# 📢 COMANDO MASIVO /difundir PARA EL ADMINISTRADOR (Ubicado correctamente)
@bot.message_handler(commands=['difundir'])
def difundir_mensaje(message):
    if message.chat.id != MI_TELEGRAM_ID:
        return

    texto_anuncio = (
        "¡Aviso rápido por acá! 🚨\n\n"
        "Si de verdad quieres empezar a operar en serio y llevarte un ingreso extra, escríbeme hoy. "
        "Estoy haciendo la reestructuración del grupo VIP para octubre y solo le daré acceso a los que estén activos.\n\n"
        "Si te activas hoy, te meto de una a:\n\n"
        "💰 El sorteo exclusivo de $200 USD en efectivo entre los miembros VIP\n"
        "📊 Las señales VIP con las mejores entradas del día\n"
        "🔴 Las sesiones en vivo para operar juntos en tiempo real\n"
        "📈 El análisis del mercado para ir siempre un paso adelante\n"
        "🛡️ La plantilla de gestión de riesgo para cuidar tu capital\n"
        "🎁 Un bono extra del 70% en tu recarga\n\n"
        "⚠️ **Dato clave:** Hasta este miércoles te sumas con el depósito mínimo de la plataforma ($25 USD). "
        "Después del miércoles el mínimo de ingreso sube a $50 USD.\n\n"
        "Tengo un par de cupos para las próximas sesiones, así que mándame un mensaje directo con la palabra "
        "\"ACTIVO\" y te paso los pasos para entrar de una. ¡Nos vemos adentro!"
    )

    markup = types.InlineKeyboardMarkup()
    btn_continuar = types.InlineKeyboardButton("🚀 Continuar mi registro", callback_data="pedir_id_registro")
    markup.add(btn_continuar)

    destinatarios = chats_conocidos.union(set(user_data.keys()))
    
    if not destinatarios:
        bot.send_message(MI_TELEGRAM_ID, "⚠️ No hay usuarios registrados en la sesión actual para difundir.")
        return

    enviados = 0
    for cid in destinatarios:
        try:
            bot.send_message(cid, texto_anuncio, reply_markup=markup, parse_mode="Markdown")
            enviados += 1
            time.sleep(0.05)
        except Exception:
            pass

    bot.send_message(MI_TELEGRAM_ID, f"📢 Difusión completada. Mensaje enviado a {enviados} usuario(s).")

# 📥 POSTBACK
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

# 1. BIENVENIDA
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

# 2. PEDIR ID
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

# 3. PROCESAR ID
@bot.message_handler(func=lambda msg: True, content_types=['text'])
def procesar_texto(message):
    chat_id = message.chat.id
    actualizar_usuario(chat_id, user_data.get(chat_id, {}).get('step', 1))
    
    id_ingresado = message.text.strip()
    step_actual = user_data[chat_id].get('step')
    
    if step_actual == 2:
        if id_ingresado in traders_registrados:
            user_data[chat_id]['step'] = 3
            user_data[chat_id]['last_interaction'] = time.time()
            user_data[chat_id]['trader_id'] = id_ingresado
            
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

# 4. BOTÓN VERIFICAR DEPÓSITO
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

# ⏰ RECORDATORIO
def verificar_usuarios_colgados():
    while True:
        time.sleep(3600)
        ahora = time.time()
        for chat_id, data in list(user_data.items()):
            if data['step'] in [1, 2, 3] and not data.get('reminded', False):
                if ahora - data['last_interaction'] > 7200:
                    try:
                        markup = types.InlineKeyboardMarkup()
                        btn_continuar = types.InlineKeyboardButton("🚀 Continuar mi registro", callback_data="pedir_id_registro")
                        markup.add(btn_continuar)
                        
                        texto_recordatorio = (
                            "¡Aviso rápido por acá! 🚨\n\n"
                            "Si de verdad quieres empezar a operar en serio y llevarte un ingreso extra, escríbeme hoy. "
                            "Estoy haciendo la reestructuración del grupo VIP para octubre y solo le daré acceso a los que estén activos.\n\n"
                            "Si te activas hoy, te meto de una a:\n\n"
                            "💰 El sorteo exclusivo de $200 USD en efectivo entre los miembros VIP\n"
                            "📊 Las señales VIP con las mejores entradas del día\n"
                            "🔴 Las sesiones en vivo para operar juntos en tiempo real\n"
                            "📈 El análisis del mercado para ir siempre un paso adelante\n"
                            "🛡️ La plantilla de gestión de riesgo para cuidar tu capital\n"
                            "🎁 Un bono extra del 70% en tu recarga\n\n"
                            "⚠️ **Dato clave:** Hasta este miércoles te sumas con el depósito mínimo de la plataforma ($25 USD). "
                            "Después del miércoles el mínimo de ingreso sube a $50 USD.\n\n"
                            "Tengo un par de cupos para las próximas sesiones, así que mándame un mensaje directo con la palabra "
                            "\"ACTIVO\" y te paso los pasos para entrar de una. ¡Nos vemos adentro!"
                        )
                        bot.send_message(chat_id, texto_recordatorio, reply_markup=markup, parse_mode="Markdown")
                        user_data[chat_id]['reminded'] = True
                    except Exception:
                        pass

@app.route('/')
def home():
    return "Bot VIP Activo 24/7", 200

if __name__ == "__main__":
    try:
        bot.delete_webhook()
    except Exception:
        pass
        
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types)).start()
    threading.Thread(target=verificar_usuarios_colgados, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
