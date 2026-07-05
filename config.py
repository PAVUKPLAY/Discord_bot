import os
import sys
import logging
from dotenv import load_dotenv

# Загружаем .env файл (для локальной разработки)
load_dotenv()

# ================= ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ =================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not DISCORD_BOT_TOKEN:
    logging.error("❌ Discord Bot Token не найден! Установите DISCORD_BOT_TOKEN.")
    sys.exit(1)

BATTLEMETRICS_TOKEN = os.getenv('BATTLEMETRICS_TOKEN')
if not BATTLEMETRICS_TOKEN:
    logging.error("❌ BattleMetrics API Token не найден! Установите BATTLEMETRICS_TOKEN.")
    sys.exit(1)

# ================= ОПЦИОНАЛЬНЫЕ (НО РЕКОМЕНДУЕМЫЕ) =================
BATTLEMETRICS_SERVER_ID = os.getenv('BATTLEMETRICS_SERVER_ID', '32115022')
STATUS_CHANNEL_ID = int(os.getenv('STATUS_CHANNEL_ID', '0'))
if STATUS_CHANNEL_ID == 0:
    logging.error("❌ STATUS_CHANNEL_ID не задан. Бот не сможет отправлять статус.")
    sys.exit(1)

ROLE_SETUP_CHANNEL_ID = int(os.getenv('ROLE_SETUP_CHANNEL_ID', '0'))
GUEST_ROLE_ID = int(os.getenv('GUEST_ROLE_ID', '0'))
FIGHTER_ROLE_ID = int(os.getenv('FIGHTER_ROLE_ID', '0'))

# ID ролей для /restart (через запятую)
restart_roles_str = os.getenv('RESTART_ROLE_IDS', '')
RESTART_ROLE_IDS = [int(x.strip()) for x in restart_roles_str.split(',') if x.strip()]

# Приоритетные теги (через запятую)
priority_tags_str = os.getenv('PRIORITY_TAGS', '')
PRIORITY_TAGS = [tag.strip() for tag in priority_tags_str.split(',') if tag.strip()]
if not PRIORITY_TAGS:
    PRIORITY_TAGS = ["[G4S]", "[ОМОН]", "[Полиция]", "[Мед]"]   # значения по умолчанию

# Роли, которые могут использовать кнопки (через запятую; пусто – все)
allowed_roles_str = os.getenv('ALLOWED_ROLE_IDS_FOR_BUTTONS', '')
ALLOWED_ROLE_IDS_FOR_BUTTONS = [int(x.strip()) for x in allowed_roles_str.split(',') if x.strip()]

# Логируем загруженные настройки (без токенов)
logging.info("✅ Конфигурация загружена из окружения.")
logging.info(f"   BATTLEMETRICS_SERVER_ID = {BATTLEMETRICS_SERVER_ID}")
logging.info(f"   STATUS_CHANNEL_ID = {STATUS_CHANNEL_ID}")
logging.info(f"   RESTART_ROLE_IDS = {RESTART_ROLE_IDS}")
logging.info(f"   PRIORITY_TAGS = {PRIORITY_TAGS}")