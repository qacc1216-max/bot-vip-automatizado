import os
import telebot
from telebot import types
from flask import Flask, request

# CONFIGURACIÓN ESENCIAL (Se lee de forma segura desde Render)
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8943668513:AAHnPjS7ZfHUBlS7VpKi35hK6dJpLrEmbk0')
MI_TELEGRAM_ID = int(os.environ.get('ADMIN_ID', 1630411628))

# Enlaces (Configurá tus reales cuando los tengas)
LINK_REGISTRO = "https://www.google.com"
LINK_GRUPO_VIP = "LINK_DE_TU_GRUPO_VIP_ACA"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Base de datos temporal en memoria para guardar los ID que depositan
traders_aprobados = set()
user_data = {}

# 📥 WEBHOOK / POSTBACK: Aquí golpea la puerta Affiliate Top
@app.route('/postback', methods=['GET'])
def affiliate_postback():
    # Recibimos el Trader ID que nos manda la plataforma
    trader_id = request.args.get('trader_id')
    evento = request.args.get('event', 'deposito') # Registro o Depósito
    
    if trader_id:
        trader_id = trader_id.strip()
        # Guardamos el ID en la lista de aprobados
        traders_aprobados.add(trader_id)
        
        # Te mandamos un aviso silencioso a vos para que sepas que entró plata
        try:
            bot.send_message(MI_TELEGRAM_ID, f"💰 ¡Postback Recibido!\nID de Trader: {trader_id} realizó un {evento}.")
        except Exception:
            pass
            
    return "OK", 200

# 1. BIENVENIDA DEL BOT
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'step': 1}
    
    markup = types.InlineKeyboardMarkup()
    btn_registro = types.InlineKeyboardButton("🔗 Registrarme en Binomo", url=LINK_REGISTRO)
    btn_siguiente = types.InlineKeyboardButton("✅ Ya me registré, ¿cómo deposito?", callback_data="paso_deposito")
    markup.add(btn_registro)
    markup.add(btn_siguiente)
    
    texto = (
        "¡Hola! 👋 Bienvenido/a al sistema de acceso automático para el **Grupo VIP**.\n\n"
        "Para ingresar, el primer paso es crearte una cuenta en Binomo usando nuestro enlace oficial.\n\n"
        "👉 Tocá el botón de abajo para registrarte:"
    )
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")

# 2. EXPLICACIÓN DEL DEPÓSITO
@bot.callback_query_handler(func=lambda call: call.data == "paso_deposito")
def paso_deposito(call):
    chat_id = call.message.chat.id
    user_data[chat_id]['step'] = 2
    
    markup = types.InlineKeyboardMarkup()
    btn_id = types.InlineKeyboardButton("🆔 Ya deposité, ingresar mi ID", callback_data="pedir_id")
    markup.add(btn_id)
    
    texto = (
        "💵 **Paso 2: Realizá tu depósito**\n\n"
        "Para activar tu cuenta en el VIP, realizá el depósito mínimo en la plataforma.\n\n"
        "Una vez hecho, tocá el botón de abajo para que el sistema valide tu cuenta al instante."
    )
    bot.edit_message_text(texto, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# 3. PEDIR EL ID PARA VALIDACIÓN AUTOMÁTICA
@bot.callback_query_handler(func=lambda call: call.data == "pedir_id")
def pedir_id(call):
    chat_id = call.message.chat.id
    user_data[chat_id]['step'] = 3
    
    bot.edit_message_text(
        "📝 Por favor, **escribí tu ID de Binomo** acá abajo. Nuestro sistema comprobará tu depósito en el acto:", 
        chat_id, 
        call.message.message_id, 
        parse_mode="Markdown"
    )

# 4. CAPTURA DEL ID Y VERIFICACIÓN AUTOMÁTICA
@bot.message_handler(func=lambda msg: True, content_types=['text'])
def verificar_id_automatico(message):
    chat_id = message.chat.id
    if chat_id not in user_data or user_data[chat_id].get('step') != 3:
        return
        
    id_ingresado = message.text.strip()
    
    # El bot revisa si el ID ya impactó en el Postback de Affiliate Top
    if id_ingresado in traders_aprobados:
        texto_exito = (
            "🎉 ¡Cuenta Verificada Automáticamente! 🎉\n\n"
            "Comprobamos tu registro y depósito correctamente. Podés unirte al canal VIP ingresando al siguiente enlace:\n\n"
            f"{LINK_GRUPO_VIP}\n\n"
            "¡Bienvenido al equipo!"
        )
        bot.send_message(chat_id, texto_exito)
        user_data[chat_id]['step'] = 4
    else:
        # Si todavía no impactó, le da instrucciones claras
        texto_error = (
            "❌ **El ID ingresado aún no registra el depósito mínimo.**\n\n"
            "Recuerde que el proceso puede tardar unos minutos en impactar. "
            "Asegúrese de haber realizado el depósito correctamente bajo nuestro enlace.\n\n"
            "Si ya lo hizo, aguarde un momento y **vuelva a escribir su ID** aquí para reintentar:"
        )
        bot.send_message(chat_id, texto_error, parse_mode="Markdown")

# Entrada para el servidor de Render
@app.route('/')
def home():
    return "Bot en línea 24/7", 200

if __name__ == "__main__":
    # Arrancamos el bot en segundo plano para que no bloquee la web
    bot.remove_webhook()
    import threading
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types)).start()
    
    # Iniciamos el servidor web
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
