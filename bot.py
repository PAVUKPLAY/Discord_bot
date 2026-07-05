import discord
from discord.ext import commands
import aiohttp
import logging
from config import DISCORD_BOT_TOKEN, GUEST_ROLE_ID, FIGHTER_ROLE_ID

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True          # нужно для отслеживания входов
bot = commands.Bot(command_prefix="!", intents=intents)

# Хранилище состояния
bot.session = None
bot.status_message = None
bot.players_message = None
bot.server_online_since = None
bot.pending_roles = {}          # {user_id: role_id}


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


@bot.event
async def on_member_join(member):
    """При входе пользователя выдаём ожидающую роль, если есть."""
    if member.id in bot.pending_roles:
        role_id = bot.pending_roles.pop(member.id)
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Принятие приглашения через бота")
                logging.info(f"Пользователю {member} выдана роль {role.name}")
            except Exception as e:
                logging.error(f"Не удалось выдать роль {role.name}: {e}")
        else:
            logging.warning(f"Роль с ID {role_id} не найдена")


# Импортируем модули с командами (регистрируются в дереве)
import status   # noqa
import roles    # noqa
import admin    # noqa
