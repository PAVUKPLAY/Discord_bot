import discord
from discord.ext import commands
import aiohttp
import logging
from config import DISCORD_BOT_TOKEN

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Хранилище состояния (атрибуты бота)
bot.session = None
bot.status_message = None
bot.players_message = None
bot.server_online_since = None


@bot.event
async def on_ready():
    logging.info(f"Бот {bot.user} запущен!")
    bot.session = aiohttp.ClientSession()
    try:
        synced = await bot.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} команд(ы)")
    except Exception as e:
        logging.error(f"Ошибка синхронизации команд: {e}")

    from status import auto_update
    auto_update.start()


# Импортируем модули с командами (регистрируются в дереве)
import status   # noqa
import roles    # noqa
import admin    # noqa