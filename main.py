import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# ================= НАСТРОЙКИ ========================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not DISCORD_BOT_TOKEN:
    logging.error("❌ Discord Bot Token не найден!")
    sys.exit(1)

BATTLEMETRICS_TOKEN = os.getenv('BATTLEMETRICS_TOKEN')
if not BATTLEMETRICS_TOKEN:
    logging.error("❌ BattleMetrics API Token не найден!")
    sys.exit(1)

BATTLEMETRICS_SERVER_ID = "32115022"          # ID вашего сервера
CHANNEL_ID = 1490763178513141892

RESTART_ROLE_IDS = [
    1333192664199205005,
    1333193701064839198,
    1333195904387387434
]

# Приоритетные теги (регистр не важен, ищется вхождение в ник)
PRIORITY_TAGS = ["[G4S]", "[ОМОН]", "[Полиция]", "[Мед]"]
# ====================================================================

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

status_message = None
players_message = None
server_online_since = None

# Единая HTTP-сессия для всех запросов
session = None

# ------------------------------------------------------------
# HTTP запрос к BattleMetrics API (с переиспользованием сессии)
# ------------------------------------------------------------
async def fetch_battlemetrics(endpoint: str):
    global session
    url = f"https://api.battlemetrics.com/{endpoint}"
    headers = {
        "Authorization": f"Bearer {BATTLEMETRICS_TOKEN}",
        "Accept": "application/json"
    }
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                text = await resp.text()
                logging.error(f"BattleMetrics API error {resp.status}: {text[:200]}")
                return None
            return await resp.json()
    except asyncio.TimeoutError:
        logging.error("BattleMetrics API timeout")
        return None
    except Exception as e:
        logging.error(f"BattleMetrics request error: {e}")
        return None

# ------------------------------------------------------------
# Получение статуса сервера и списка игроков с временем сессии
# ------------------------------------------------------------
async def get_server_status() -> Optional[Dict[str, Any]]:
    try:
        # Запрашиваем сервер вместе с игроками и их сессиями
        data = await fetch_battlemetrics(
            f"servers/{BATTLEMETRICS_SERVER_ID}?include=player,session"
        )
        if not data:
            return None

        attrs = data["data"]["attributes"]

        # Словарь: player_id -> длительность сессии в секундах
        session_times = {}

        # Сначала находим все активные сессии
        for item in data.get("included", []):
            if item.get("type") == "session":
                player_id = item["relationships"]["player"]["data"]["id"]
                start_str = item["attributes"].get("start")
                if start_str:
                    start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    duration = int((now - start_time).total_seconds())
                    session_times[player_id] = duration

        # Собираем игроков
        players = []
        for item in data.get("included", []):
            if item.get("type") == "player" and "attributes" in item:
                name = item["attributes"].get("name")
                player_id = item["id"]
                if name:
                    duration = session_times.get(player_id, 0)
                    players.append({"name": name, "duration": duration})

        # Сортировка: сначала игроки с приоритетными тегами, затем остальные по алфавиту
        def priority_key(p):
            name_upper = p["name"].upper()
            for idx, tag in enumerate(PRIORITY_TAGS):
                if tag.upper() in name_upper:
                    return (0, idx, name_upper)  # группа 0, сортировка по индексу тега, затем по имени
            return (1, name_upper)  # группа 1, остальные по алфавиту

        players.sort(key=priority_key)

        status = {
            "name": attrs["name"],
            "map": attrs["details"].get("map", "Unknown"),
            "players_online": attrs["players"],
            "players_max": attrs["maxPlayers"],
            "players_list": players,
        }
        logging.info(f"Статус: {status['players_online']}/{status['players_max']} игроков, в списке: {len(players)}")
        return status
    except Exception as e:
        logging.error(f"Ошибка запроса: {e}")
        return None

# ------------------------------------------------------------
# Форматирование времени (uptime сервера)
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
# Форматирование времени пребывания игрока
# ------------------------------------------------------------
def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}с"
    minutes = seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    if hours > 0:
        return f"{hours}ч {minutes}м"
    return f"{minutes}м"

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
            description="Не удаётся получить данные через BattleMetrics API.",
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
    # Подсчёт игроков с тегом [G4S] (регистронезависимо)
    g4s_count = sum(1 for p in status_data['players_list'] if "[g4s]" in p["name"].lower())

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
# Embed списка игроков с временем на сервере
# ------------------------------------------------------------
def create_players_embed(players_list):
    if not players_list:
        return discord.Embed(
            title="🎮 Список игроков",
            description="На сервере сейчас никого нет.",
            color=discord.Color.blue()
        )

    lines = []
    for p in players_list:
        name = p["name"]
        duration_sec = p["duration"]
        if duration_sec > 0:
            time_str = format_duration(duration_sec)
        else:
            time_str = "только зашёл"
        lines.append(f"🎮 `{name}` — ⏱️ {time_str}")

    embed = discord.Embed(
        title=f"🎮 Список игроков ({len(players_list)})",
        color=discord.Color.blue()
    )

    # Разбиваем на две колонки
    half = (len(lines) + 1) // 2
    left = lines[:half]
    right = lines[half:]

    def add_field_no_name(embed, content, inline=True):
        if not content:
            return
        block = "\n".join(content)
        if len(block) > 1024:
            # Если слишком длинно, разбиваем на несколько полей
            for i in range(0, len(content), 20):
                chunk_block = "\n".join(content[i:i+20])
                embed.add_field(name="\u200b", value=chunk_block, inline=inline)
        else:
            embed.add_field(name="\u200b", value=block, inline=inline)

    add_field_no_name(embed, left, inline=True)
    add_field_no_name(embed, right, inline=True)

    embed.set_footer(text="🔄 Обновление было")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

# ------------------------------------------------------------
# Фоновое обновление (каждую минуту)
# ------------------------------------------------------------
@tasks.loop(minutes=1)
async def auto_update():
    global status_message, players_message, server_online_since
    status_data = await get_server_status()

    # Логика uptime сервера (сбрасываем при недоступности)
    if status_data is not None:
        if server_online_since is None:
            server_online_since = datetime.now(timezone.utc)
            logging.info("Сервер онлайн, uptime начат")
    else:
        if server_online_since is not None:
            logging.info("Сервер не отвечает, uptime сброшен")
            server_online_since = None

    # Статус бота (Activity)
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

    # Обновление статус-сообщения
    embed_status = create_status_embed(status_data)
    if status_message is None:
        async for msg in channel.history(limit=50):
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

    # Обновление сообщения со списком игроков
    players_list = status_data["players_list"] if status_data else []
    embed_players = create_players_embed(players_list)
    if players_message is None:
        async for msg in channel.history(limit=50):
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
    # Корректное завершение для автоматического перезапуска хостингом
    await bot.close()
    sys.exit(0)

# ------------------------------------------------------------
# Событие готовности
# ------------------------------------------------------------
@bot.event
async def on_ready():
    global session
    logging.info(f"Бот {bot.user} запущен!")
    # Создаём единую сессию aiohttp
    session = aiohttp.ClientSession()
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
    if BATTLEMETRICS_SERVER_ID == "32115022":
        print("✅ ID сервера указан, запускаем бота...")
    bot.run(DISCORD_BOT_TOKEN)
