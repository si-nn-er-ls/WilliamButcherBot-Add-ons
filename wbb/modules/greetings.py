"""
MIT License

Copyright (c) 2023 TheHamkerCat

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import os
from re import findall
from datetime import datetime, timedelta
from random import shuffle

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors.exceptions.bad_request_400 import (
    ChatAdminRequired,
    UserNotParticipant,
)
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.types import (
    Chat,
    ChatPermissions,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from wbb import BOT_USERNAME, SUDOERS, WELCOME_DELAY_KICK_SEC, app
from wbb.core.decorators.errors import capture_err
from wbb.core.decorators.permissions import adminsOnly
from wbb.core.keyboard import ikb
from wbb.modules.notes import extract_urls
from wbb.utils.dbfeds import check_banned_user, get_fed_id
from wbb.utils.dbfunctions import (
    captcha_off,
    captcha_on,
    del_welcome,
    get_captcha_cache,
    get_welcome,
    has_solved_captcha_once,
    is_captcha_on,
    is_gbanned_user,
    save_captcha_solved,
    set_welcome,
    update_captcha_cache,
)
from wbb.utils.dbfunctions2 import (
    ecap_on,
    ecap_off,
    captcha_mode,
)
from wbb.utils.captcha import (
    make_captcha,
    generate_rnd_id,
    make_captcha_markup,
)
from wbb.utils.filter_groups import welcome_captcha_group
from wbb.utils.functions import (
    check_format,
    extract_text_and_keyb,
    generate_captcha,
)
from wbb.modules.admin import member_permissions

CaptchaDB = {}

__MODULE__ = "Greetings"
__HELP__ = """
/captcha [ENABLE|DISABLE] - Enable/Disable captcha.

/set_welcome - Reply this to a message containing correct
format for a welcome message, check end of this message.

/del_welcome - Delete the welcome message.
/get_welcome - Get the welcome message.

**SET_WELCOME ->**

**To set a photo or gif as welcome message. Add your welcome message as caption to the photo or gif. The caption muse be in the format given below.**

For text welcome message just send the text. Then reply with the command 

The format should be something like below.

```
**Hi** {name} [{id}] Welcome to {chat}

~ #This separater (~) should be there between text and buttons, remove this comment also

button=[Duck, https://duckduckgo.com]
button2=[Github, https://github.com]
```

**NOTES ->**

Checkout /markdownhelp to know more about formattings and other syntax.
"""

answers_dicc = []
loop = asyncio.get_running_loop()


async def get_initial_captcha_cache():
    global answers_dicc
    answers_dicc = await get_captcha_cache()
    return answers_dicc


loop.create_task(get_initial_captcha_cache())


async def handle_new_member(member, chat):
    global answers_dicc

    # Get cached answers from mongodb in case of bot's been restarted or crashed.
    answers_dicc = await get_captcha_cache()

    # Mute new member and send message with button
    try:
        if member.id in SUDOERS:
            return  # Ignore sudo users
        fed_id = await get_fed_id(chat.id)
        if fed_id:
            check_user = await check_banned_user(fed_id, member.id)
            if check_user:
                reason = check_user["reason"]
                date = check_user["date"]
                await chat.ban_member(member.id)
                return await app.send_message(
                    chat.id,
                    f"**User {member.mention} was Fed Banned.\n\nReason: {reason}.\nDate: {date}.**",
                )
        if await is_gbanned_user(member.id):
            await chat.ban_member(member.id)
            await app.send_message(
                chat.id,
                f"{member.mention} was globally banned, and got removed,"
                + " if you think this is a false gban, you can appeal"
                + " for this ban in support chat.",
            )
            return
        if member.is_bot:
            return  # Ignore bots
        if not await is_captcha_on(chat.id):
            return await send_welcome_message(
                chat, member.id
            )

        # Ignore user if he has already solved captcha in this group
        # someday
        if await has_solved_captcha_once(chat.id, member.id):
            return
            
        mode = await captcha_mode(chat.id)
        if mode == "emoji":
            return await emoji_handler(member, chat)

        await chat.restrict_member(member.id, ChatPermissions())
        text = (
            f"{(member.mention())} Are you human?\n"
            f"Solve this captcha in {WELCOME_DELAY_KICK_SEC} "
            "seconds and 4 attempts or you'll be kicked."
        )
    except ChatAdminRequired:
        return

    # Generate a captcha image, answers, and some wrong answers
    captcha = generate_captcha()
    captcha_image = captcha[0]
    captcha_answer = captcha[1]
    wrong_answers = captcha[2]  # This consists of 8 wrong answers
    correct_button = InlineKeyboardButton(
        f"{captcha_answer}",
        callback_data=f"pressed_button {captcha_answer} {member.id}",
    )
    temp_keyboard_1 = [correct_button]  # Button row 1
    temp_keyboard_2 = []  # Botton row 2
    temp_keyboard_3 = []
    for i in range(2):
        temp_keyboard_1.append(
            InlineKeyboardButton(
                f"{wrong_answers[i]}",
                callback_data=f"pressed_button {wrong_answers[i]} {member.id}",
            )
        )
    for i in range(2, 5):
        temp_keyboard_2.append(
            InlineKeyboardButton(
                f"{wrong_answers[i]}",
                callback_data=f"pressed_button {wrong_answers[i]} {member.id}",
            )
        )
    for i in range(5, 8):
        temp_keyboard_3.append(
            InlineKeyboardButton(
                f"{wrong_answers[i]}",
                callback_data=f"pressed_button {wrong_answers[i]} {member.id}",
            )
        )

    shuffle(temp_keyboard_1)
    keyboard = [temp_keyboard_1, temp_keyboard_2, temp_keyboard_3]
    shuffle(keyboard)
    verification_data = {
        "chat_id": chat.id,
        "user_id": member.id,
        "answer": captcha_answer,
        "keyboard": keyboard,
        "attempts": 0,
    }
    keyboard = InlineKeyboardMarkup(keyboard)
    # Append user info, correct answer, and
    answers_dicc.append(verification_data)
    # keyboard for later use with callback query
    button_message = await app.send_photo(
        chat_id=chat.id,
        photo=captcha_image,
        caption=text,
        reply_markup=keyboard,
    )
    os.remove(captcha_image)

    # Save captcha answers etc in mongodb in case the bot gets crashed or restarted.
    await update_captcha_cache(answers_dicc)

    asyncio.create_task(
        kick_restricted_after_delay(
            WELCOME_DELAY_KICK_SEC, button_message, member
        )
    )
    await asyncio.sleep(0.5)
    
async def emoji_handler(member, chat):
    try:
        user_ = await app.get_chat_member(chat.id, member.id)
        await chat.restrict_member(member.id, ChatPermissions())
        data, emoji_path_ = make_captcha(generate_rnd_id())
        print("Done!")
        markup = [[], [], []]
        __emojis = data.split(": ", 1)[-1].split()
        print(__emojis)
        _emojis = ['🐻', '🐔', '☁️', '🔮', '🌀', '🌚', '💎', '🐶', '🍩', '🌏', '🐸', '🌕', '🍏', '🐵', '🌙',
                   '🐧', '🍎', '😀', '🐍', '❄️', '🐚', '🐢', '🌝', '🍺', '🍔', '🍒', '🍫', '🍡', '🌑', '🍟',
                   '☕️', '🍑', '🍷', '🍧', '🍕', '🍵', '🐋', '🐱', '💄', '👠', '💰', '💸', '🎹', '📦', '📍',
                   '🐊', '🦕', '🐬', '💋', '🦎', '🦈', '🦷', '🦖', '🐠', '🐟','💀', '🎃', '👮', '⛑', '🪢', '🧶',
                   '🧵', '🪡', '🧥', '🥼', '🥻', '🎩', '👑', '🎒', '🙊', '🐗', '🦋', '🦐', '🐀', '🐿', '🦔', '🦦', 
                   '🦫', '🦡', '🦨', '🐇']
        shuffle(_emojis)
        _emojis = _emojis[:20]
        for a in range(len(__emojis)):
            if __emojis[a] in _emojis:
                _emojis.remove(__emojis[a])
        show = __emojis
        for b in range(9):
            show.append(_emojis[b])
        shuffle(show)
        count = 0
        for _ in range(5):
            markup[0].append(
                InlineKeyboardButton(
                    f"{show[count]}",
                    callback_data=f"verify_{str(member.id)}_{show[count]}",
                )
            )
            count += 1
        for _ in range(5):
            markup[1].append(
                InlineKeyboardButton(
                    f"{show[count]}",
                    callback_data=f"verify_{str(member.id)}_{show[count]}",
                )
            )
            count += 1
        for _ in range(5):
            markup[2].append(
                InlineKeyboardButton(
                    f"{show[count]}",
                    callback_data=f"verify_{str(member.id)}_{show[count]}",
                )
            )
            count += 1
        CaptchaDB[member.id] = {
            "emojis": data.split(": ", 1)[-1].split(),
            "mistakes": 0,
            "group_id": chat.id,
            "message_id": None,
        }
        __message = await app.send_photo(
            chat_id=chat.id,
            photo=emoji_path_,
            caption=f"{member.mention}, select all the emojis you can see in the picture. "
            f"You are allowed only (3) mistakes.",
            reply_markup=InlineKeyboardMarkup(markup),
        )
        os.remove(emoji_path_)
        CaptchaDB[member.id]["message_id"] = __message.id
        await asyncio.sleep(300)
        await __message.delete()
        user = await chat.get_member(member.id)
        if user.status == ChatMemberStatus.RESTRICTED:
            until_date = (datetime.now() + timedelta(seconds=300))
            await chat.ban_member(member.id, until_date=until_date)
            del CaptchaDB[member.id]
    except Exception as e:
        print(e)
        pass


@app.on_chat_member_updated(filters.group, group=welcome_captcha_group)
@capture_err
async def welcome(_, user: ChatMemberUpdated):
    if not (
        user.new_chat_member
        and user.new_chat_member.status not in {CMS.RESTRICTED}
        and not user.old_chat_member
    ):
        return

    member = user.new_chat_member.user if user.new_chat_member else user.from_user
    chat = user.chat
    return await handle_new_member(member, chat)


async def send_welcome_message(chat: Chat, user_id: int, delete: bool = False):
    welcome, raw_text, file_id = await get_welcome(chat.id)

    if not raw_text:
        return
    text = raw_text
    keyb = None
    if findall(r"\[.+\,.+\]", raw_text):
        text, keyb = extract_text_and_keyb(ikb, raw_text)

    if "{chat}" in text:
        text = text.replace("{chat}", chat.title)
    if "{name}" in text:
        text = text.replace("{name}", (await app.get_users(user_id)).mention)
    if "{id}" in text:
        text = text.replace("{id}", f"`{user_id}`")

    async def _send_wait_delete():
        if welcome == "Text":
            m = await app.send_message(
                chat.id,
                text=text,
                reply_markup=keyb,
                disable_web_page_preview=True,
            )
        elif welcome == "Photo":
            m = await app.send_photo(
                chat.id,
                photo=file_id,
                caption=text,
                reply_markup=keyb,
            )
        else:
            m = await app.send_animation(
                chat.id,
                animation=file_id,
                caption=text,
                reply_markup=keyb,
            )
        await asyncio.sleep(300)
        await m.delete()

    asyncio.create_task(_send_wait_delete())


@app.on_callback_query(filters.regex("pressed_button"))
async def callback_query_welcome_button(_, callback_query):
    """After the new member presses the correct button,
    set his permissions to chat permissions,
    delete button message and join message.
    """
    global answers_dicc
    data = callback_query.data
    pressed_user_id = callback_query.from_user.id
    pending_user_id = int(data.split(None, 2)[2])
    button_message = callback_query.message
    answer = data.split(None, 2)[1]

    correct_answer = None
    keyboard = None

    if len(answers_dicc) != 0:
        for i in answers_dicc:
            if (
                i["user_id"] == pending_user_id
                and i["chat_id"] == button_message.chat.id
            ):
                correct_answer = i["answer"]
                keyboard = i["keyboard"]

    if not (correct_answer and keyboard):
        return await callback_query.answer(
            "Something went wrong, Rejoin the " "chat!"
        )

    if pending_user_id != pressed_user_id:
        return await callback_query.answer("This is not for you")

    if answer != correct_answer:
        await callback_query.answer("Yeah, It's Wrong.")
        for iii in answers_dicc:
            if (
                iii["user_id"] == pending_user_id
                and iii["chat_id"] == button_message.chat.id
            ):
                attempts = iii["attempts"]
                if attempts >= 3:
                    answers_dicc.remove(iii)
                    await button_message.chat.ban_member(pending_user_id)
                    await asyncio.sleep(1)
                    await button_message.chat.unban_member(pending_user_id)
                    await button_message.delete()
                    return await update_captcha_cache(answers_dicc)

                iii["attempts"] += 1
                break

        shuffle(keyboard[0])
        shuffle(keyboard[1])
        shuffle(keyboard[2])
        shuffle(keyboard)
        keyboard = InlineKeyboardMarkup(keyboard)
        return await button_message.edit(
            text=button_message.caption.markdown,
            reply_markup=keyboard,
        )

    await callback_query.answer("Captcha passed successfully!")
    await button_message.chat.unban_member(pending_user_id)
    await button_message.delete()

    if len(answers_dicc) != 0:
        for ii in answers_dicc:
            if (
                ii["user_id"] == pending_user_id
                and ii["chat_id"] == button_message.chat.id
            ):
                answers_dicc.remove(ii)
                await update_captcha_cache(answers_dicc)

    chat = callback_query.message.chat

    # Save this verification in db, so we don't have to
    # send captcha to this user when he joins again.
    await save_captcha_solved(chat.id, pending_user_id)

    return await send_welcome_message(chat, pending_user_id, True)


async def kick_restricted_after_delay(
    delay, button_message: Message, user: User
):
    """If the new member is still restricted after the delay, delete
    button message and join message and then kick him
    """
    global answers_dicc
    await asyncio.sleep(delay)
    group_chat = button_message.chat
    user_id = user.id
    await button_message.delete()
    if len(answers_dicc) != 0:
        for i in answers_dicc:
            if i["user_id"] == user_id:
                answers_dicc.remove(i)
                await update_captcha_cache(answers_dicc)
    await _ban_restricted_user_until_date(group_chat, user_id, duration=delay)


async def _ban_restricted_user_until_date(
    group_chat, user_id: int, duration: int
):
    try:
        member = await group_chat.get_member(user_id)
        if member.status == ChatMemberStatus.RESTRICTED:
            until_date = (datetime.now() + timedelta(seconds=duration))
            await group_chat.ban_member(user_id, until_date=until_date)
    except UserNotParticipant:
        pass


@app.on_message(filters.command("captcha") & ~filters.private)
@adminsOnly("can_restrict_members")
async def captcha_state(_, message):
    usage = "**Usage:**\n/captcha [ENABLE|DISABLE]"
    if len(message.command) != 2:
        return await message.reply_text(usage)

    chat_id = message.chat.id
    state = message.text.split(None, 1)[1].strip()
    state = state.lower()
    if state == "enable":
        await captcha_on(chat_id)
        await message.reply_text("Enabled Captcha For New Users.")
    elif state == "disable":
        await captcha_off(chat_id)
        await message.reply_text("Disabled Captcha For New Users.")
    elif state == "mode":
        check = await captcha_mode(chat_id)
        print(check)
        if check == "text":
            buttons = {"Text": "cmode_emoji"}
        elif check == "emoji":
            buttons = {"Emoji": "cmode_text"}
        try:
            keyboard = ikb(buttons, 1)
        except UnboundLocalError:
            return await message.reply_text("Try Again after resetting captcha mode.\nUsage: `/captcha reset`")
        await message.reply_text("**Current captcha mode:**", reply_markup=keyboard)
    elif state == "reset":
        await ecap_off(chat_id)
        await message.reply("Done :-_-:") 
    else:
        await message.reply_text(usage)


# WELCOME MESSAGE


@app.on_message(filters.command("set_welcome") & ~filters.private)
@adminsOnly("can_change_info")
async def set_welcome_func(_, message):
    usage = "You need to reply to a text, gif or photo to set it as greetings.\n\nNotes: caption required for gif and photo."
    key = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="More Help",
                    url=f"t.me/{BOT_USERNAME}?start=help_greetings",
                )
            ],
        ]
    )
    replied_message = message.reply_to_message
    chat_id = message.chat.id
    try:
        if not replied_message:
            await message.reply_text(usage, reply_markup=key)
            return
        if replied_message.animation:
            welcome = "Animation"
            file_id = replied_message.animation.file_id
            text = replied_message.caption
            if not text:
                return await message.reply_text(usage, reply_markup=key)
            raw_text = text.markdown
        if replied_message.photo:
            welcome = "Photo"
            file_id = replied_message.photo.file_id
            text = replied_message.caption
            if not text:
                return await message.reply_text(usage, reply_markup=key)
            raw_text = text.markdown
        if replied_message.text:
            welcome = "Text"
            file_id = None
            text = replied_message.text
            raw_text = text.markdown
        if replied_message.reply_markup and not "~" in raw_text:
            urls = extract_urls(replied_message.reply_markup)
            if urls:
                response = "\n".join(
                    [f"{name}=[{text}, {url}]" for name, text, url in urls]
                )
                raw_text = raw_text + response
        raw_text = await check_format(ikb, raw_text)
        if raw_text:
            await set_welcome(chat_id, welcome, raw_text, file_id)
            return await message.reply_text(
                "Welcome message has been successfully set."
            )
        else:
            return await message.reply_text(
                "Wrong formatting, check the help section.\n\n**Usage:**\nText: `Text`\nText + Buttons: `Text ~ Buttons`",
                reply_markup=key,
            )
    except UnboundLocalError:
        return await message.reply_text(
            "**Only Text, Gif and Photo welcome message are supported.**"
        )


@app.on_message(filters.command("del_welcome") & ~filters.private)
@adminsOnly("can_change_info")
async def del_welcome_func(_, message):
    chat_id = message.chat.id
    await del_welcome(chat_id)
    await message.reply_text("Welcome message has been deleted.")


@app.on_message(filters.command("get_welcome") & ~filters.private)
@adminsOnly("can_change_info")
async def get_welcome_func(_, message):
    chat = message.chat
    welcome, raw_text, file_id = await get_welcome(chat.id)
    if not raw_text:
        return await message.reply_text("No welcome message set.")
    if not message.from_user:
        return await message.reply_text(
            "You're anon, can't send welcome message."
        )

    await send_welcome_message(chat, message.from_user.id)

    await message.reply_text(
        f'Welcome: {welcome}\n\nFile_id: `{file_id}`\n\n`{raw_text.replace("`", "")}`'
    )


@app.on_callback_query(filters.regex("verify_(.*)"))
async def buttons_handlers(_, cb):
    if cb.data.startswith("verify_"):
        __emoji = cb.data.rsplit("_", 1)[-1]
        __user = cb.data.split("_")[1]
        if cb.from_user.id != int(__user):
            await cb.answer("This Message is Not For You!", show_alert=True)
            return
        if cb.from_user.id not in CaptchaDB:
            await cb.answer("Try Again After Re-Join!", show_alert=True)
            await cb.message.chat.ban_member(cb.from_user.id)
            await cb.message.delete()
            await cb.message.chat.unban_member(cb.from_user.id)
        if __emoji not in CaptchaDB.get(cb.from_user.id).get("emojis"):
            CaptchaDB[cb.from_user.id]["mistakes"] += 1
            await cb.answer("You pressed wrong emoji!", show_alert=True)
            n = 3 - CaptchaDB[cb.from_user.id]["mistakes"]
            if n == 0:
                await cb.message.delete(True)
                await app.send_message(
                    chat_id=cb.message.chat.id,
                    text=f"{cb.from_user.mention}, you failed to solve the captcha!\n\n"
                    f"You can try again after 5 minutes.",
                )
                del CaptchaDB[cb.from_user.id]
                until_date = (datetime.now() + timedelta(seconds=300))
                await cb.message.chat.ban_member(cb.from_user.id, until_date=until_date)
                return
            markup = make_captcha_markup(
                cb.message.reply_markup.inline_keyboard, __emoji, "❌"
            )
            await cb.message.edit_caption(
                caption=f"{cb.from_user.mention}, select all the emojis you can see in the picture. "
                f"You are allowed only ({n}) mistakes.",
                reply_markup=InlineKeyboardMarkup(markup),
            )
            return
        else:
            CaptchaDB.get(cb.from_user.id).get("emojis").remove(__emoji)
            markup = make_captcha_markup(
                cb.message.reply_markup.inline_keyboard, __emoji, "✅"
            )
            await cb.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(markup)
            )
            if not CaptchaDB.get(cb.from_user.id).get("emojis"):
                await cb.answer("You Passed the Captcha!", show_alert=True)
                del CaptchaDB[cb.from_user.id]
                try:
                    UserOnChat = await app.get_chat_member(
                        user_id=cb.from_user.id, chat_id=cb.message.chat.id
                    )
                    if UserOnChat.restricted_by.id == (await app.get_me()).id:
                        await app.unban_chat_member(
                            chat_id=cb.message.chat.id, user_id=cb.from_user.id
                        )
                except:
                    pass
                await cb.message.delete(True)
                await send_welcome_message(cb.message.chat, cb.from_user.id, True)
            await cb.answer()


@app.on_callback_query(filters.regex("cmode_(.*)"))
async def ecap_cb(_, cb):
    chat_id = cb.message.chat.id
    from_user = cb.from_user
    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_change_info"
    if permission not in permissions:
        return await cb.answer(
            f"You don't have the required permission.\n Permission: {permission}",
            show_alert=True,
        )
    data = cb.data.split("_")[1]
    if data == "text":
        await ecap_off(chat_id)
        buttons = {"Text": "cmode_emoji"}
        keyboard = ikb(buttons, 1)
        await cb.message.edit_reply_markup(reply_markup=keyboard)
    else:
        mode = "emoji"
        await ecap_on(chat_id, mode)
        buttons = {"Emoji": "cmode_text"}
        keyboard = ikb(buttons, 1)
        await cb.message.edit_reply_markup(reply_markup=keyboard)