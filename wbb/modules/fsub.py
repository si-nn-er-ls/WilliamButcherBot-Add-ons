import asyncio
import os
import re
from datetime import datetime
from random import shuffle

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors.exceptions.bad_request_400 import (
    ChatAdminRequired,
    UserNotParticipant,
)
from pyrogram.types import (
    Chat,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from wbb import BOT_USERNAME, SUDOERS, app, BOT_ID
from wbb.core.decorators.errors import capture_err
from wbb.core.decorators.permissions import adminsOnly
from wbb.modules.admin import member_permissions
from wbb.utils.dbfunctions2 import (
    check_fsub,
    add_fsub,
    update_fsub,
    rem_fsub,
    fsub_chats,
)

__MODULE__ = "Fsub"
__HELP__ = """
Set Fsub channel / group for Groups

Usage: /fsub chat-id 

To remove: /remfsub
"""


fsub_group = 15
PERMISSION = "can_restrict_members"


async def check_join(user_id, chat_id):
    try:
        await app.get_chat_member(chat_id, user_id)
        return True
    except UserNotParticipant:
        return False


@app.on_message(filters.command("fsub") & ~filters.private)
@adminsOnly("can_restrict_members")
async def fsub_cmd_handler(_, message):
    msg = await message.reply_text("⏳")
    chat_id = message.chat.id
    checks = await member_permissions(chat_id, BOT_ID)
    if not checks:
        await msg.edit("**i am not an admin here, make me an admin and try again.**")
        await asyncio.sleep(600)
        await msg.delete()
        return
    try:
        if len(message.command) < 2:
            check = await check_fsub(chat_id)
            if not check:
                await msg.edit(
                    "**Usage:** /fsub chat-id (__Fsub chat-id__)\nTo remove: /remfsub"
                )
                await asyncio.sleep(600)
                await msg.delete()
                return
            keyboard = [
                [InlineKeyboardButton("❌ Disable Fsub", callback_data="fsub#fsubrem")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit(
                f"**✅ Fsub already enabled for this chat**\nFsub Chat ID: `{check}`\n\nTo remove: /remfsub",
                reply_markup=reply_markup,
            )
            await asyncio.sleep(600)
            await msg.delete()
            return

        fsub_id = int(message.text.split(" ", 1)[1].strip())
        check = await member_permissions(fsub_id, BOT_ID)
        if not check:
            await msg.edit("Make sure i am admin in the channel / group")
            await asyncio.sleep(600)
            await msg.delete()
            return

        check = await check_fsub(chat_id)
        if check:
            await msg.edit("**Removing old Fsub ID and adding new ID...**")
            await update_fsub(chat_id, fsub_id)
        else:
            await msg.edit("**Adding Fsub for this chat...**")
            await add_fsub(chat_id, fsub_id)
        await msg.edit(f"✅ **Fsub enabled for this chat**")
        await asyncio.sleep(600)
        await msg.delete()
    except Exception as e:
        err = await message.reply_text(e)
        await msg.edit(
            "**Oops, an error occured. Make sure i am admin in that Channel/chat**"
        )
        await asyncio.sleep(600)
        await msg.delete()
        await err.delete()


@app.on_message(
    filters.group & ~filters.bot & ~filters.via_bot & ~filters.service,
    group=fsub_group,
)
@capture_err
async def fsub_watcher_func(_, message):
    if not message.from_user:
        return
    chat_id = message.chat.id
    user = message.from_user
    user_id = user.id
    member = await app.get_chat_member(chat_id, user_id)
    if (
        member.status == ChatMemberStatus.OWNER
        or member.status == ChatMemberStatus.ADMINISTRATOR
    ):
        return
    check = await check_fsub(chat_id)
    if not check:
        return
    joined = await check_join(user_id, check)
    if joined:
        return
    link = (await app.get_chat(check)).invite_link
    if not link:
        text = "**Could not import link from Fsub chat. Reported to admins**"
        admin_data = [
            i
            async for i in app.get_chat_members(
                chat_id=chat_id, filter=ChatMembersFilter.ADMINISTRATORS
            )
        ]
        for admin in admin_data:
            if admin.user.is_bot or admin.user.is_deleted:
                continue
            text += f"[\u2063](tg://user?id={admin.user.id})"
        await app.send_message(chat_id=chat_id, text=text)
        return

    keyboard = [
        [InlineKeyboardButton("Join Now", url=link)],
        [InlineKeyboardButton("Unmute Me", callback_data=f"fsub#unmute#{user_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    mention = user.mention
    msg = await app.send_message(
        chat_id,
        f"🔻**Hey** {mention} __You have to join here to message in this chat__",
        reply_markup=reply_markup,
    )
    await app.restrict_chat_member(
        chat_id, user_id, ChatPermissions(can_send_messages=False)
    )
    await asyncio.sleep(1800)
    await msg.delete()


@app.on_callback_query(filters.regex(r"^fsub"))
@capture_err
async def fsub_callbacks_handler(_, query):
    action = query.data.split("#")[1]
    if action == "unmute":
        user_id = int(query.data.split("#")[2])
        chat_id = query.message.chat.id
        clicked = query.from_user.id
        if clicked != user_id:
            await query.answer("⚠️ This button is not for you", show_alert=True)
            return
        fsub_id = await check_fsub(chat_id)
        check = await check_join(user_id, fsub_id)
        if check:
            await app.unban_chat_member(chat_id, user_id)
            await query.message.delete()
        else:
            await query.answer("⚠️ Join via the link and try again", show_alert=True)
    elif action == "fsubrem":
        try:
            msg = await query.message.edit("⏳")
            user_id = query.from_user.id
            chat_id = query.message.chat.id
            check = await check_fsub(chat_id)
            perm = await member_permissions(query.message.chat.id, user_id)
            if PERMISSION not in perm:
                await query.answer("⚠️ This button is not for you", show_alert=True)
                return
            if not check:
                return await msg.edit(
                    "⚠️ **No Fsub found for this chat. Set using /fsub Command**"
                )
            await rem_fsub(chat_id)
            await msg.edit("✅ **Fsub removed successfully**")
            await asyncio.sleep(600)
            await msg.delete()
        except Exception as e:
            await query.message.reply_text(f"```Error:\n{e}```")


@app.on_message(filters.command("remfsub") & ~filters.private)
@adminsOnly("can_restrict_members")
async def fsubrem_cmd_handler(_, message):
    msg = await message.reply_text("⏳")
    chat_id = message.chat.id
    check = await check_fsub(chat_id)
    if not check:
        return await msg.edit(
            "⚠️ **No Fsub found for this chat. Set using /fsub Command**"
        )
    await rem_fsub(chat_id)
    await msg.edit("✅ **Fsub removed successfully**")
    await asyncio.sleep(600)
    await msg.delete()
