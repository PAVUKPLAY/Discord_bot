import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Импортируем библиотеку. Обратите внимание: class battlemetrics с маленькой буквы!
from battlemetrics import battlemetrics

# ================= НАСТРОЙКИ ========================================
# Получаем токены из переменных окружения
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not DISCORD_BOT_TOKEN:
    logging.error("❌ Discord Bot Token не найден! Установите переменную окружения DISCORD_BOT_TOKEN")
    sys.exit(1)

BATTLEMETRICS_TOKEN = os.getenv('BATTLEMETRICS_TOKEN')
if not BATTLEMETRICS_TOKEN:
    logging.error("❌ BattleMetrics API Token не найден! Установите переменную окружения BATTLEMETRICS_TOKEN")
    sys.exit(1)

# ID вашего сервера в BattleMetrics
BATTLEMETRICS_SERVER_ID = "32115022"  # ЗАМЕНИТЕ НА ID ВАШЕГО СЕРВЕРА!
CHANNEL_ID = 1490763178513141892               # ID канала для мониторинга

RESTART_ROLE_IDS = [
    1333192664199205005,   # Командир
    1333193701064839198,   # Зам. Командира
    1333195904387387434    # Смотряга
]
# ====================================================================

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

status_message = None
players_message = None
server_online_since = None

# ------------------------------------------------------------
# Получение статуса сервера через BattleMetrics API
# ------------------------------------------------------------
async def get_server_status() -> Optional[Dict[str, Any]]:
    try:
        # Создаём клиент. Обратите внимание: battlemetrics с маленькой буквы!
        client = battlemetrics(BATTLEMETRICS_TOKEN)
        
        # Получаем информацию о сервере по его ID
        server = await client.get_server(BATTLEMETRICS_SERVER_ID)
        
        # Получаем список игроков на сервере
        players = await client.list_players(server_id=BATTLEMETRICS_SERVER_ID)
        
        status = {
            "name": server["data"]["attributes"]["name"],
            "map": server["data"]["attributes"]["details"]["map"],
            "players_online": server["data"]["attributes"]["players"],
            "players_max": server["data"]["attributes"]["maxPlayers"],
            "players_list": [p["attributes"]["name"] for p in players["data"]]
        }
        logging.info(f"Статус получен: {status['players_online']}/{status['players_max']} игроков")
        return status
    except Exception as e:
        logging.error(f"Ошибка при запросе к BattleMetrics API: {e}")
        return None

# ------------------------------------------------------------
# Форматирование времени работы
# ------------------------------------------------------------
def format_uptime(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0 or days > 0:
        parts.append(f"{hours}ч")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}м")
    parts.append(f"{secs}с")
    return " ".join(parts)

# ------------------------------------------------------------
# Прогресс‑бар
# ------------------------------------------------------------
def make_progress_bar(percent, length=15, filled="█", empty="░"):
    filled_count = round(length * percent / 100)
    return filled * filled_count + empty * (length - filled_count)

# ------------------------------------------------------------
# Embed статуса сервера
# ------------------------------------------------------------
def create_status_embed(status_data):
    global server_online_since
    if status_data is None:
        return discord.Embed(
            title="🔴 СЕРВЕР НЕДОСТУПЕН",
            description="Не удаётся получить данные через BattleMetrics API. Возможно, сервер выключен.",
            color=discord.Color.red()
        )

    percent = round(status_data['players_online'] / status_data['players_max'] * 100)
    if percent >= 80:
        color = discord.Color.red()
        status_emoji = "🔴"
        status_text = "Высокая нагрузка"
    elif percent >= 40:
        color = discord.Color.orange()
        status_emoji = "🟠"
        status_text = "Средняя нагрузка"
    else:
        color = discord.Color.green()
        status_emoji = "🟢"
        status_text = "Низкая нагрузка"

    bar_precise = make_progress_bar(percent, 15)
    g4s_count = sum(1 for name in status_data['players_list'] if "[g4s]" in name.lower())

    embed = discord.Embed(
        title=f"🖥️ **{status_data['name']}**",
        color=color,
        description=f"**{status_emoji} Состояние:** {status_text}"
    )

    embed.add_field(name="👥 Игроки", value=f"**{status_data['players_online']}** / {status_data['players_max']}", inline=True)
    embed.add_field(name="🗺️ Карта", value=f"**{status_data['map']}**", inline=True)
    embed.add_field(name="🎖️ Бойцы [G4S]", value=f"**{g4s_count}** игроков", inline=True)

    embed.add_field(name="📊 Загруженность сервера", value=f"{bar_precise} `{percent}%`", inline=True)
    if server_online_since is not None:
        uptime_seconds = int((datetime.now(timezone.utc) - server_online_since).total_seconds())
        uptime_str = format_uptime(uptime_seconds)
        embed.add_field(name="⏱️ Время работы", value=f"**{uptime_str}**", inline=True)
    else:
        embed.add_field(name="⏱️ Время работы", value="Неизвестно", inline=True)

    embed.set_footer(text="🔄 Обновление было")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

# ------------------------------------------------------------
# Embed списка игроков
# ------------------------------------------------------------
def create_players_embed(players_list):
    if not players_list:
        return discord.Embed(
            title="🎮 Список игроков",
            description="На сервере сейчас никого нет.",
            color=discord.Color.blue()
        )
    players_list = [f"🎮 `{name}`" for name in players_list]
    embed = discord.Embed(
        title=f"🎮 Список игроков ({len(players_list)})",
        color=discord.Color.blue()
    )
    half = (len(players_list) + 1) // 2
    left = players_list[:half]
    right = players_list[half:]

    def add_inline_field_no_name(embed, content, inline=True):
        if not content:
            return
        block = "\n".join(content)
        if len(block) > 1024:
            lines = content
            chunks = []
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > 1000:
                    chunks.append(current)
                    current = line
                else:
                    current += "\n" + line if current else line
            if current:
                chunks.append(current)
            for i, chunk in enumerate(chunks):
                embed.add_field(name="\u200b", value=chunk, inline=inline)
        else:
            embed.add_field(name="\u200b", value=block, inline=inline)

    add_inline_field_no_name(embed, left, inline=True)
    add_inline_field_no_name(embed, right, inline=True)
    embed.set_footer(text="Полные ники, без обрезания")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

# ------------------------------------------------------------
# Фоновое задание
# ------------------------------------------------------------
@tasks.loop(minutes=1)
async def auto_update():
    global status_message, players_message, server_online_since

    status_data = await get_server_status()

    if status_data is not None:
        if server_online_since is None:
            server_online_since = datetime.now(timezone.utc)
            logging.info("Сервер онлайн, uptime начат")
    else:
        if server_online_since is not None:
            logging.info("Сервер не отвечает, uptime сброшен")
            server_online_since = None

    if status_data:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{status_data['players_online']}/{status_data['players_max']} игроков"
        )
        await bot.change_presence(activity=activity)
    else:
        activity = discord.Activity(type=discord.ActivityType.watching, name="за сервером Arma 3...")
        await bot.change_presence(activity=activity)

    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        logging.error(f"Канал {CHANNEL_ID} не найден!")
        return

    embed_status = create_status_embed(status_data)
    if status_message is None:
        async for msg in channel.history(limit=20):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title and "🖥️" in msg.embeds[0].title:
                status_message = msg
                break
        if status_message is None:
            status_message = await channel.send(embed=embed_status)
            logging.info("Создано сообщение со статусом")
    else:
        try:
            await status_message.edit(embed=embed_status)
        except discord.NotFound:
            status_message = await channel.send(embed=embed_status)
            logging.warning("Статус-сообщение потеряно, создано новое")
        except Exception as e:
            logging.error(f"Ошибка редактирования статуса: {e}")

    players_list = status_data["players_list"] if status_data else []
    embed_players = create_players_embed(players_list)
    if players_message is None:
        async for msg in channel.history(limit=20):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title and "Список игроков" in msg.embeds[0].title:
                players_message = msg
                break
        if players_message is None:
            players_message = await channel.send(embed=embed_players)
            logging.info("Создано сообщение со списком игроков")
    else:
        try:
            await players_message.edit(embed=embed_players)
        except discord.NotFound:
            players_message = await channel.send(embed=embed_players)
            logging.warning("Сообщение со списком потеряно, создано новое")
        except Exception as e:
            logging.error(f"Ошибка редактирования списка: {e}")

# ------------------------------------------------------------
# Команда /restart
# ------------------------------------------------------------
@bot.tree.command(name="restart", description="Перезапустить бота (только для определённых ролей)")
async def restart_command(interaction: discord.Interaction):
    user_role_ids = [role.id for role in interaction.user.roles]
    if not any(role_id in user_role_ids for role_id in RESTART_ROLE_IDS):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды.", ephemeral=True)
        return
    await interaction.response.send_message("🔄 Перезапуск бота...", ephemeral=True)
    logging.info(f"Бот перезапущен пользователем {interaction.user} (ID: {interaction.user.id})")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ------------------------------------------------------------
# Событие готовности
# ------------------------------------------------------------
@bot.event
async def on_ready():
    logging.info(f"Бот {bot.user} запущен!")
    try:
        synced = await bot.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} команд(ы)")
    except Exception as e:
        logging.error(f"Ошибка синхронизации команд: {e}")
    auto_update.start()

# ------------------------------------------------------------
# Запуск
# ------------------------------------------------------------
if __name__ == "__main__":
    if BATTLEMETRICS_SERVER_ID == "ВАШ_ID_СЕРВЕРА":
        print("⚠️ ВНИМАНИЕ: Укажите ID вашего сервера в переменной BATTLEMETRICS_SERVER_ID!")
    else:
        bot.run(DISCORD_BOT_TOKEN)