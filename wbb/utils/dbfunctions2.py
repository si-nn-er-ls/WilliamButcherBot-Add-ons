from wbb import db

afkdb = db.afk
ecapdb = db.emoji_captcha


async def captcha_mode(chat_id: int):
    data = await ecapdb.find_one({"chat_id": chat_id})
    if data:
        return data.get("mode")
    return "text"


async def ecap_on(chat_id: int, mode: str):
    return await ecapdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"mode": mode}},
        upsert=True,
    )

async def ecap_off(chat_id: int):
    return await ecapdb.delete_one({"chat_id": chat_id})


async def is_cleanmode_on(chat_id: int) -> bool:
    mode = cleanmode.get(chat_id)
    if not mode:
        user = await cleandb.find_one({"chat_id": chat_id})
        if not user:
            cleanmode[chat_id] = True
            return True
        cleanmode[chat_id] = False
        return False
    return mode

async def cleanmode_on(chat_id: int):
    cleanmode[chat_id] = True
    user = await cleandb.find_one({"chat_id": chat_id})
    if user:
        return await cleandb.delete_one({"chat_id": chat_id})

async def cleanmode_off(chat_id: int):
    cleanmode[chat_id] = False
    user = await cleandb.find_one({"chat_id": chat_id})
    if not user:
        return await cleandb.insert_one({"chat_id": chat_id})

async def is_afk(user_id: int) -> bool:
    user = await afkdb.find_one({"user_id": user_id})
    return (True, user["reason"]) if user else (False, {})

async def add_afk(user_id: int, mode):
    await afkdb.update_one(
        {"user_id": user_id}, {"$set": {"reason": mode}}, upsert=True
    )

async def remove_afk(user_id: int):
    user = await afkdb.find_one({"user_id": user_id})
    if user:
        return await afkdb.delete_one({"user_id": user_id})

async def get_afk_users() -> list:
    users = afkdb.find({"user_id": {"$gt": 0}})
    return list(await users.to_list(length=1000000000)) if users else []
