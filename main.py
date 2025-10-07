import os, json, asyncio, aiohttp, datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8034372475:AAHgi7kwLVziS40cbuITLiLrW_tXETaRSS0")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://ReverseXpert:mahe1406@cluster0.mjdvdzy.mongodb.net/")
DB_NAME   = "modx_bot_db"
API_BASE  = "https://codewairth.vercel.app/upi?upi_id="

ADMIN_ID  = 7612935302
BOT_NAME  = "MOD•X FANTOM DELUXE"
DEVELOPER_LINK = "https://t.me/ReverseXpert"

CHANNELS = [
    {"id": -1002734447292, "link": "https://t.me/teamezra", "label":"Ezra"},
    {"id": -1002578772434, "link": "https://t.me/+vP7GkUuScbs4OWZl", "label":"Group2"}
]

# ---------------- INIT ----------------
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]

# ---------------- HELPERS ----------------
async def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    doc = await db.admins.find_one({"user_id": user_id})
    return doc is not None

async def is_banned(user_id):
    doc = await db.bans.find_one({"user_id": user_id})
    return doc is not None

async def check_membership(user_id):
    unjoined = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ["left","kicked"]:
                unjoined.append(ch)
        except:
            unjoined.append(ch)
    return unjoined

async def add_log(user_id, upi):
    await db.logs.insert_one({"user_id": user_id, "upi": upi, "time": datetime.datetime.utcnow()})

async def fetch_upi_info(upi_id):
    url = API_BASE + upi_id
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as resp:
            if resp.status == 200:
                return await resp.json()
            return {"error":"API Request failed"}

def build_result_message(data, upi_id):
    bank = data.get("bank_details_raw", {})
    vpa = data.get("vpa_details", {})
    msg = f"🟥 <b>{BOT_NAME} — UPI INFO</b> 🟥\n"
    msg += f"📌 <b>VPA:</b> {vpa.get('vpa','—')}\n"
    msg += f"👤 <b>Name:</b> {vpa.get('name','—')}\n"
    msg += f"🏦 <b>Bank:</b> {bank.get('BANK','—')}\n"
    msg += f"📍 <b>Branch:</b> {bank.get('BRANCH','—')}, {bank.get('CITY','—')}\n"
    msg += f"🏘️ <b>Address:</b> {bank.get('ADDRESS','—')}\n"
    msg += f"📞 <b>Contact:</b> {bank.get('CONTACT','—')}\n"
    msg += f"🆔 <b>IFSC:</b> {bank.get('IFSC','—')}\n"
    return msg

def referral_message(complete, left):
    return f"✅ {complete} Refer Complete! {left} Left to get 30 credits"

# ---------------- /start HANDLER ----------------
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    args = message.get_args().split()
    referrer_id = int(args[0]) if args else None

    if await is_banned(user_id):
        await message.answer("⛔️ <b>ACCESS BLOCKED</b>\n\nYou are banned.")
        return

    # save user
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        await db.users.insert_one({
            "user_id": user_id,
            "name": name,
            "joined_at": datetime.datetime.utcnow(),
            "credits": 3,  # free credits
            "refer_count": 0,
            "referred_by": referrer_id,
            "verified": False
        })

        # handle referral
        if referrer_id:
            ref_user = await db.users.find_one({"user_id": referrer_id})
            if ref_user:
                await db.users.update_one(
                    {"user_id": referrer_id},
                    {"$inc": {"pending_refers": 1}}
                )

    # check channel join
    unjoined = await check_membership(user_id)
    if unjoined:
        kb = InlineKeyboardMarkup()
        for ch in unjoined:
            kb.add(InlineKeyboardButton(f"📌 JOIN {ch['label']}", url=ch["link"]))
        kb.add(InlineKeyboardButton("✅ I Joined", callback_data="joined"))
        kb.add(InlineKeyboardButton("🛠 Contact Developer", url=DEVELOPER_LINK))
        await message.answer("⛔️ <b>ACCESS DENIED</b>\n\nJoin required channel(s) to use the bot:", reply_markup=kb)
        return

    await message.answer(f"🟥 WELCOME AGENT — {BOT_NAME}\n\n🔐 Send a UPI ID to get info.\n\n💰 You have 3 free credits.")

# ---------------- UPI SCAN ----------------
@dp.message_handler(lambda m: "@" in m.text)
async def upi_scan(message: types.Message):
    user_id = message.from_user.id
    upi_id = message.text.strip()

    user = await db.users.find_one({"user_id": user_id})
    if not user or await is_banned(user_id):
        await message.answer("⛔️ Banned or Not Registered.")
        return

    # check credits
    if user.get("credits",0) <=0:
        await message.answer("❌ Not enough credits. Refer friends to earn more.")
        return

    # check channel join
    unjoined = await check_membership(user_id)
    if unjoined:
        kb = InlineKeyboardMarkup()
        for ch in unjoined:
            kb.add(InlineKeyboardButton(f"📌 JOIN {ch['label']}", url=ch["link"]))
        kb.add(InlineKeyboardButton("✅ I Joined", callback_data="joined"))
        await message.answer("⛔️ Join required channels first:", reply_markup=kb)
        return

    # fetch UPI info
    data = await fetch_upi_info(upi_id)
    if data.get("error"):
        await message.answer("❌ API fetch failed.")
        return

    # deduct credit
    await db.users.update_one({"user_id": user_id}, {"$inc": {"credits": -1}})

    # log scan
    await add_log(user_id, upi_id)

    # send result
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📂 Raw JSON", callback_data=f"raw|{upi_id}"))
    kb.add(InlineKeyboardButton("🔄 Rescan", callback_data=f"rescan|{upi_id}"))
    kb.add(InlineKeyboardButton("🛠 Contact Developer", url=DEVELOPER_LINK))
    msg = build_result_message(data, upi_id)
    await message.answer(msg, reply_markup=kb)

# ---------------- CALLBACKS ----------------
@dp.callback_query_handler(lambda c: True)
async def callbacks(cb: types.CallbackQuery):
    data = cb.data
    user_id = cb.from_user.id

    if data.startswith("raw|"):
        upi_id = data.split("|")[1]
        info = await fetch_upi_info(upi_id)
        await cb.message.answer(f"<b>RAW JSON:</b>\n<pre>{json.dumps(info, indent=2)}</pre>")
        await cb.answer()
    elif data.startswith("rescan|"):
        upi_id = data.split("|")[1]
        await upi_scan(types.Message(from_user=cb.from_user, text=upi_id, chat=cb.message.chat))
        await cb.answer()
    elif data=="joined":
        await cb.message.answer("✅ Thanks — you can now use the bot.")
        await cb.answer()

# ---------------- ADMIN COMMANDS ----------------
@dp.message_handler(commands=["ban","unban","stats","addcredit"])
async def admin_commands(message: types.Message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    cmd = message.text.split()[0][1:]
    args = message.text.split()[1:]

    if cmd=="ban" and args:
        uid = int(args[0])
        await db.bans.update_one({"user_id": uid}, {"$set":{"user_id":uid}}, upsert=True)
        await message.answer(f"✅ User {uid} banned.")
    elif cmd=="unban" and args:
        uid = int(args[0])
        await db.bans.delete_one({"user_id": uid})
        await message.answer(f"✅ User {uid} unbanned.")
    elif cmd=="stats":
        users = await db.users.count_documents({})
        logs = await db.logs.count_documents({})
        bans = await db.bans.count_documents({})
        await message.answer(f"📊 Stats:\nUsers: {users}\nScans: {logs}\nBanned: {bans}")
    elif cmd=="addcredit" and len(args)>=2:
        uid = int(args[0])
        credit = int(args[1])
        await db.users.update_one({"user_id":uid}, {"$inc":{"credits":credit}})
        await message.answer(f"✅ Added {credit} credits to {uid}")

# ---------------- RUN BOT ----------------
if __name__ == "__main__":
    import logging
    from aiogram import executor
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp, skip_updates=True)