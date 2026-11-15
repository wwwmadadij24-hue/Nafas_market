import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB = os.getenv("DB_PATH", "nafas_market.db")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nafas-market")

def db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY, name TEXT, role TEXT, phone TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, title TEXT,
        description TEXT, price TEXT, city TEXT, status TEXT DEFAULT 'pending')""")
    con.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, buyer_id INTEGER,
        note TEXT, status TEXT DEFAULT 'new')""")
    con.commit()
    return con

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 مشاهده کالاها", callback_data="browse")],
        [InlineKeyboardButton("➕ ثبت کالای جدید", callback_data="add")],
        [InlineKeyboardButton("👤 ثبت‌نام خریدار / فروشنده", callback_data="register")],
        [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "به نفس مارکت خوش آمدید 🌿\nبازار آنلاین خرید و فروش کالا",
        reply_markup=menu())

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if q.data == "browse":
        con = db()
        rows = con.execute("SELECT id,title,description,price,city FROM products WHERE status='approved' ORDER BY id DESC LIMIT 20").fetchall()
        con.close()
        if not rows:
            await q.message.reply_text("فعلاً کالای تأییدشده‌ای ثبت نشده است.")
            return
        for pid, title, desc, price, city in rows:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("ثبت درخواست خرید", callback_data=f"order:{pid}")]])
            await q.message.reply_text(f"🛒 {title}\n{desc}\nقیمت: {price}\nشهر: {city}", reply_markup=kb)
    elif q.data == "register":
        context.user_data["step"] = "reg_name"
        await q.message.reply_text("نام و نام خانوادگی را بنویسید:")
    elif q.data == "add":
        context.user_data["step"] = "product_title"
        await q.message.reply_text("نام کالا را بنویسید:")
    elif q.data == "orders":
        con = db()
        rows = con.execute("SELECT id,product_id,note,status FROM orders WHERE buyer_id=? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
        con.close()
        await q.message.reply_text("سفارش‌های شما:\n" + ("\n".join(map(str, rows)) if rows else "هنوز سفارشی ثبت نکرده‌اید."))
    elif q.data == "help":
        await q.message.reply_text("برای خرید، کالاها را ببینید و درخواست خرید ثبت کنید. برای فروش، ابتدا ثبت‌نام کنید و سپس کالای خود را ثبت کنید.")

    elif q.data.startswith("order:"):
        pid = int(q.data.split(":")[1])
        context.user_data["order_product"] = pid
        context.user_data["step"] = "order_note"
        await q.message.reply_text("تعداد و توضیحات درخواست خرید را بنویسید:")
    elif q.data.startswith("approve:") and uid == ADMIN_ID:
        pid = int(q.data.split(":")[1])
        con = db()
        con.execute("UPDATE products SET status='approved' WHERE id=?", (pid,))
        con.commit()
        con.close()
        await q.message.reply_text("کالا تأیید شد و در فهرست نمایش داده می‌شود.")

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    value = update.message.text.strip()
    step = context.user_data.get("step")
    if not step:
        await update.message.reply_text("از منوی اصلی استفاده کنید:", reply_markup=menu())
        return
    if step == "reg_name":
        context.user_data["reg_name"] = value
        context.user_data["step"] = "reg_role"
        await update.message.reply_text("نقش خود را بنویسید: خریدار یا فروشنده یا هر دو")
    elif step == "reg_role":
        con = db()
        con.execute("INSERT INTO users(telegram_id,name,role) VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET name=excluded.name, role=excluded.role", (uid, context.user_data["reg_name"], value))
        con.commit()
        con.close()
        context.user_data.clear()
        await update.message.reply_text("ثبت‌نام شما انجام شد.", reply_markup=menu())
    elif step == "product_title":
        context.user_data["product_title"] = value
        context.user_data["step"] = "product_desc"
        await update.message.reply_text("توضیح کالا را بنویسید:")
    elif step == "product_desc":
        context.user_data["product_desc"] = value
        context.user_data["step"] = "product_price"
        await update.message.reply_text("قیمت و واحد را بنویسید:")
    elif step == "product_price":
        context.user_data["product_price"] = value
        context.user_data["step"] = "product_city"
        await update.message.reply_text("شهر محل عرضه را بنویسید:")
    elif step == "product_city":
        con = db()
        cur = con.execute("INSERT INTO products(seller_id,title,description,price,city) VALUES(?,?,?,?,?)",
            (uid, context.user_data["product_title"], context.user_data["product_desc"], context.user_data["product_price"], value))
        pid = cur.lastrowid
        con.commit()
        con.close()
        context.user_data.clear()
        await update.message.reply_text("آگهی ثبت شد و پس از بررسی مدیر منتشر می‌شود.", reply_markup=menu())
        if ADMIN_ID:
            await context.bot.send_message(ADMIN_ID, f"آگهی جدید شماره {pid}\nبرای تأیید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("تأیید آگهی", callback_data=f"approve:{pid}")]]))
    elif step == "order_note":
        pid = context.user_data["order_product"]
        con = db()
        cur = con.execute("INSERT INTO orders(product_id,buyer_id,note) VALUES(?,?,?)", (pid, uid, value))
        oid = cur.lastrowid
        con.commit()
        con.close()
        context.user_data.clear()
        await update.message.reply_text(f"درخواست خرید شما با شماره {oid} ثبت شد. فروشنده برای هماهنگی باید از طریق مدیر/سامانه پیگیری شود.", reply_markup=menu())

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not ADMIN_ID:
        await update.message.reply_text("این بخش مخصوص مدیر سامانه است.")
        return
    con = db()
    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    products = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    orders = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    con.close()
    await update.message.reply_text(f"پنل مدیر نفس مارکت\nکاربران: {users}\nآگهی‌ها: {products}\nدرخواست‌های خرید: {orders}")

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.run_polling()

if __name__ == "__main__":
    main()
