import discord
from discord import ButtonStyle, TextStyle
from discord import app_commands
from discord.ui import Modal, TextInput, View, button

from bot import bot
from config import (
    ROLE_SETUP_CHANNEL_ID,
    GUEST_ROLE_ID,
    FIGHTER_ROLE_ID,
    ALLOWED_ROLE_IDS_FOR_BUTTONS,
    INVITE_CHANNEL_ID,
)


class RoleModal(Modal, title='Выдача роли'):
    def __init__(self, role_name: str, role_id: int):
        super().__init__()
        self.role_name = role_name
        self.role_id = role_id

    user_input = TextInput(
        label='ID пользователя или упоминание',
        placeholder='Введите ID или @упомяните пользователя',
        required=True,
        style=TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.check_permissions(interaction):
            await interaction.response.send_message("❌ У вас нет прав на выдачу ролей.", ephemeral=True)
            return

        # Парсим целевого пользователя
        input_text = self.user_input.value.strip()
        target_user = None
        if input_text.startswith('<@') and input_text.endswith('>'):
            user_id = int(input_text.strip('<@!>'))
            target_user = interaction.guild.get_member(user_id) or await bot.fetch_user(user_id)
        elif input_text.isdigit():
            user_id = int(input_text)
            target_user = interaction.guild.get_member(user_id) or await bot.fetch_user(user_id)
        else:
            # Попытка найти по имени
            for member in interaction.guild.members:
                if member.name.lower() == input_text.lower() or member.display_name.lower() == input_text.lower():
                    target_user = member
                    break
            if not target_user:
                try:
                    target_user = await bot.fetch_user(int(input_text))
                except:
                    pass

        if target_user is None:
            await interaction.response.send_message("❌ Пользователь не найден. Укажите корректный ID или упоминание.", ephemeral=True)
            return

        # Проверяем, есть ли пользователь уже на сервере
        member = interaction.guild.get_member(target_user.id)
        if member:
            role = interaction.guild.get_role(self.role_id)
            if role is None:
                await interaction.response.send_message("❌ Роль не найдена.", ephemeral=True)
                return
            if role in member.roles:
                await interaction.response.send_message(f"ℹ️ У пользователя {member.mention} уже есть роль **{role.name}**.", ephemeral=True)
                return
            try:
                await member.add_roles(role, reason=f"Выдано через кнопку {self.role_name} пользователем {interaction.user}")
                await interaction.response.send_message(f"✅ Роль **{role.name}** выдана {member.mention} (он уже был на сервере).", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Ошибка выдачи роли: {e}", ephemeral=True)
            return

        # Если пользователь не на сервере – создаём приглашение
        invite_channel = interaction.guild.get_channel(INVITE_CHANNEL_ID)
        if invite_channel is None:
            await interaction.response.send_message("❌ Канал для приглашений не найден. Обратитесь к администратору.", ephemeral=True)
            return

        try:
            invite = await invite_channel.create_invite(
                max_age=3600,
                max_uses=1,
                reason=f"Приглашение для {target_user} от {interaction.user}"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось создать приглашение: {e}", ephemeral=True)
            return

        # Сохраняем ожидающую роль
        bot.pending_roles[target_user.id] = self.role_id

        # Создаём красивый embed
        embed = discord.Embed(
            title=f"🎫 Вас приглашают на сервер {interaction.guild.name}!",
            description=f"**{interaction.user.display_name}** приглашает вас на сервер.\n"
                        f"Вам будет выдана роль **{self.role_name}** сразу после входа.",
            color=discord.Color.green()
        )
        embed.add_field(name="Приглашение от", value=interaction.user.mention, inline=True)
        embed.add_field(name="Роль", value=self.role_name, inline=True)
        embed.add_field(name="Срок действия", value="1 час", inline=True)
        embed.set_footer(text="Нажмите кнопку ниже, чтобы принять приглашение")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="✅ Принять приглашение", url=invite.url, style=ButtonStyle.link))

        try:
            await target_user.send(embed=embed, view=view)
            await interaction.response.send_message(
                f"✅ Приглашение отправлено пользователю {target_user.mention} в личные сообщения!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Не удалось отправить сообщение {target_user.mention} – возможно, у него закрыты ЛС.",
                ephemeral=True
            )
            bot.pending_roles.pop(target_user.id, None)

    async def check_permissions(self, interaction: discord.Interaction) -> bool:
        if not ALLOWED_ROLE_IDS_FOR_BUTTONS:
            return True
        user_role_ids = [role.id for role in interaction.user.roles]
        return any(role_id in user_role_ids for role_id in ALLOWED_ROLE_IDS_FOR_BUTTONS)


class RoleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label='👤 Гость', style=ButtonStyle.primary, custom_id='give_guest')
    async def guest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RoleModal(role_name='Гость', role_id=GUEST_ROLE_ID)
        await interaction.response.send_modal(modal)

    @button(label='⚔️ Боец', style=ButtonStyle.success, custom_id='give_fighter')
    async def fighter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RoleModal(role_name='Боец', role_id=FIGHTER_ROLE_ID)
        await interaction.response.send_modal(modal)


@bot.tree.command(name="setup_roles", description="Создать сообщение с кнопками для выдачи ролей (только администраторы)")
@app_commands.default_permissions(administrator=True)
async def setup_roles(interaction: discord.Interaction):
    channel = bot.get_channel(ROLE_SETUP_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message(f"❌ Канал с ID {ROLE_SETUP_CHANNEL_ID} не найден. Проверьте ROLE_SETUP_CHANNEL_ID.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎫 Выдача ролей",
        description="Нажмите на кнопку ниже, чтобы выдать роль новому игроку.\n"
                    "В открывшемся окне укажите ID пользователя или упомяните его.\n"
                    "Если пользователь не на сервере, ему будет отправлено приглашение в ЛС.",
        color=discord.Color.gold()
    )
    embed.add_field(name="🟦 Гость", value="Базовая роль для новичков", inline=True)
    embed.add_field(name="🟩 Боец", value="Роль для опытных игроков", inline=True)
    embed.set_footer(text="Бот выдаст роль только при наличии прав")

    view = RoleView()
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Сообщение с кнопками отправлено в канал {channel.mention}", ephemeral=True)
