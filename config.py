import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота (получить у @BotFather в Telegram)
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# ID администратора (можно узнать у @userinfobot)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

