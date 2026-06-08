import logging
import uuid
import requests
import qrcode
import io
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ===================== SETTINGS =====================
BOT_TOKEN = "8856006467:AAFD4TxC4iAT98pphxEYArEtLH6-ekj9cmQ"  # BotFather se naya token daalo
ADMIN_ID = 5908811700
UPI_ID = "BHARATPE.8R0K1Z0V1R62609@fbpe"
SETTINGS_FILE = "settings.json"
# ====================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
pending_payments = {}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "price": 99,
        "app_link": "https://your-app-link-here.com"
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        pass

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

def make_upi_qr(amount):
    upi_url = f"upi://pay?pa={UPI_ID}&pn=PremiumAPK&am={amount}&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = load_settings()
    user = update.effective_user
    kb = [[InlineKeyboardButton("🛒 Abhi Kharido", callback_data="pay")]]
    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 *PREMIUM APK MOD* 🔥\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 Aao *{user.first_name}*!\n\n"
        f"✅ Full Premium Unlock\n"
        f"📱 Latest Version\n"
        f"🚫 No Ads\n"
        f"⚡ Fast Download\n"
        f"🔒 100% Safe & Secure\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Sirf ₹{settings['price']}/-*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👇 Button dabao aur apna app pao!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = load_settings()
    query = update.callback_query
    await query.answer()
    user = query.from_user
    order_id = f"ORD{uuid.uuid4().hex[:8].upper()}"
    pending_payments[order_id] = {
        "user_id": user.id,
        "user_name": user.first_name,
        "amount": settings["price"],
        "status": "pending"
    }
    qr_image = make_upi_qr(settings["price"])
    kb = [[InlineKeyboardButton("✅ UTR Number Daalo", callback_data=f"utr_{order_id}")]]
    await query.message.reply_photo(
        photo=qr_image,
        caption=(
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💳 *PAYMENT DETAILS*\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 *UPI ID:*\n`{UPI_ID}`\n\n"
            f"💰 *Amount:* ₹{settings['price']}/-\n"
            f"🔖 *Order ID:* `{order_id}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📱 *Kaise pay kare?*\n"
            f"1️⃣ QR Code scan karo\n"
            f"2️⃣ Ya UPI ID copy karke pay karo\n"
            f"3️⃣ Payment ke baad UTR button dabao\n"
            f"━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def utr_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = query.data.replace("utr_", "")
    context.user_data["waiting_utr"] = order_id
    await query.message.reply_text(
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *UTR NUMBER DAALO*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔖 Order: `{order_id}`\n\n"
        f"ℹ️ *UTR kahan milega?*\n"
        f"• PhonePe → Transaction History\n"
        f"• GPay → Payment Details\n"
        f"• Paytm → Passbook\n\n"
        f"👇 *Abhi UTR number type karo:*",
        parse_mode="Markdown"
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sirf admin access kar sakta hai!")
        return
    settings = load_settings()
    kb = [
        [InlineKeyboardButton("💰 Price Change Karo", callback_data="admin_price")],
        [InlineKeyboardButton("🔗 App Link Change Karo", callback_data="admin_link")],
        [InlineKeyboardButton("📊 Current Settings", callback_data="admin_settings")]
    ]
    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👑 *ADMIN PANEL*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *Price:* ₹{settings['price']}/-\n"
        f"🔗 *Link:* `{settings['app_link'][:40]}...`\n\n"
        f"👇 Kya change karna hai?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == "pay":
        await pay(update, context)
        return

    if query.data.startswith("utr_"):
        await utr_prompt(update, context)
        return

    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Sirf admin!", show_alert=True)
        return

    await query.answer()

    if query.data == "admin_price":
        context.user_data["admin_action"] = "change_price"
        await query.message.reply_text("💰 *Naya price daalo:*\n\nSirf number (example: 149)", parse_mode="Markdown")

    elif query.data == "admin_link":
        context.user_data["admin_action"] = "change_link"
        await query.message.reply_text("🔗 *Naya app link daalo:*\n\nPura link paste karo", parse_mode="Markdown")

    elif query.data == "admin_settings":
        settings = load_settings()
        await query.message.reply_text(
            f"📊 *Current Settings:*\n\n"
            f"💰 Price: ₹{settings['price']}/-\n"
            f"🔗 Link: `{settings['app_link']}`",
            parse_mode="Markdown"
        )

    elif query.data.startswith("approve_"):
        order_id = query.data.replace("approve_", "")
        if order_id in pending_payments:
            settings = load_settings()
            user_id = pending_payments[order_id]["user_id"]
            amount = pending_payments[order_id]["amount"]
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🎉 *PAYMENT APPROVED!*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n\n"
                        f"✅ ₹{amount}/- verify ho gayi!\n"
                        f"🔖 Order: `{order_id}`\n\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🎁 *Tumhara App Link:*\n\n"
                        f"{settings['app_link']}\n"
                        f"━━━━━━━━━━━━━━━━━━━\n\n"
                        f"⚠️ Yeh link sirf tumhare liye hai!"
                    ),
                    parse_mode="Markdown"
                )
                pending_payments[order_id]["status"] = "approved"
                await query.edit_message_text(
                    f"✅ *APPROVED!*\n\nOrder: `{order_id}`\nAmount: ₹{amount}/-\nApp link bhej diya!",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Approve error: {e}")

    elif query.data.startswith("reject_"):
        order_id = query.data.replace("reject_", "")
        if order_id in pending_payments:
            user_id = pending_payments[order_id]["user_id"]
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"❌ *PAYMENT REJECTED*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n\n"
                        f"UTR verify nahi hua.\n\n"
                        f"🔄 Dobara try karo: /start"
                    ),
                    parse_mode="Markdown"
                )
                pending_payments[order_id]["status"] = "rejected"
                await query.edit_message_text(f"❌ *REJECTED*\n\nOrder: `{order_id}`", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Reject error: {e}")

    elif query.data.startswith("changeamt_"):
        order_id = query.data.replace("changeamt_", "")
        context.user_data["admin_action"] = f"change_order_amount_{order_id}"
        await query.message.reply_text(f"✏️ Naya amount daalo:\nOrder: `{order_id}`\n\nSirf number (example: 149)", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if user.id == ADMIN_ID:
        action = context.user_data.get("admin_action")

        if action == "change_price":
            try:
                new_price = int(text)
                settings = load_settings()
                settings["price"] = new_price
                save_settings(settings)
                context.user_data.pop("admin_action", None)
                await update.message.reply_text(f"✅ *Price Update!*\n\n💰 Naya Price: ₹{new_price}/-", parse_mode="Markdown")
            except:
                await update.message.reply_text("❌ Sirf number daalo!")
            return

        elif action == "change_link":
            settings = load_settings()
            settings["app_link"] = text
            save_settings(settings)
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(f"✅ *App Link Update!*\n\n🔗 `{text}`", parse_mode="Markdown")
            return

        elif action and action.startswith("change_order_amount_"):
            order_id = action.replace("change_order_amount_", "")
            try:
                new_amount = int(text)
                if order_id in pending_payments:
                    old_amount = pending_payments[order_id]["amount"]
                    pending_payments[order_id]["amount"] = new_amount
                    user_id = pending_payments[order_id]["user_id"]
                    context.user_data.pop("admin_action", None)
                    qr_image = make_upi_qr(new_amount)
                    kb = [[InlineKeyboardButton("✅ UTR Number Daalo", callback_data=f"utr_{order_id}")]]
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=qr_image,
                        caption=f"🔄 *Amount Update!*\n\n💰 Naya Amount: ₹{new_amount}/-\nUPI ID: `{UPI_ID}`\nOrder: `{order_id}`",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                    await update.message.reply_text(f"✅ Amount ₹{old_amount} se ₹{new_amount} ho gaya!")
            except:
                await update.message.reply_text("❌ Sirf number daalo!")
            return

    order_id = context.user_data.get("waiting_utr")
    if not order_id:
        return
    if order_id not in pending_payments:
        await update.message.reply_text("❌ Order nahi mila. /start karo.")
        return

    pending_payments[order_id]["utr"] = text
    pending_payments[order_id]["status"] = "utr_submitted"
    context.user_data.pop("waiting_utr", None)
    amount = pending_payments[order_id]["amount"]

    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ *VERIFICATION PENDING*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔖 Order: `{order_id}`\n"
        f"💰 Amount: ₹{amount}/-\n"
        f"🧾 UTR: `{text}`\n\n"
        f"⏰ 5-10 min mein app link milega!\n"
        f"━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

    try:
        kb = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}")
            ],
            [InlineKeyboardButton("✏️ Amount Change", callback_data=f"changeamt_{order_id}")]
        ]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🔔 *NAYA PAYMENT!*\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 User: {user.first_name}\n"
                f"🆔 ID: `{user.id}`\n"
                f"🔖 Order: `{order_id}`\n"
                f"💰 Amount: ₹{amount}/-\n"
                f"🧾 UTR: `{text}`\n\n"
                f"👇 Action lo:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        logger.error(f"Admin notification failed: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🆘 *HELP*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"/start - Bot shuru karo\n"
        f"/help - Yeh message\n"
        f"/admin - Admin panel",
        parse_mode="Markdown"
    )

def main():
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot chal raha hai!")
    app.run_polling()

if __name__ == "__main__":
    main()
