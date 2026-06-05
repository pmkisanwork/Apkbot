import logging
import uuid
import requests
import qrcode
import io
import os
import json
import threading
import hmac
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ============ CONFIG ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 5908811700
CASHFREE_APP_ID = os.environ.get("CASHFREE_APP_ID", "")
CASHFREE_SECRET_KEY = os.environ.get("CASHFREE_SECRET_KEY", "")
RENDER_URL = "https://apkbot-rvy2.onrender.com"

# Cashfree Live URLs
CASHFREE_BASE_URL = "https://api.cashfree.com/pg"

SETTINGS_FILE = "settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "price": 49,
        "app_link": "https://www.mediafire.com/file/w497vl4346qfk3w/SG.apk/file"
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pending_payments = {}  # order_id -> {user_id, amount, status, ...}

# ============ CASHFREE ============

def create_cashfree_order(order_id, amount, user_id, user_name):
    url = f"{CASHFREE_BASE_URL}/orders"
    headers = {
        "Content-Type": "application/json",
        "x-api-version": "2023-08-01",
        "x-client-id": CASHFREE_APP_ID,
        "x-client-secret": CASHFREE_SECRET_KEY
    }
    payload = {
        "order_id": order_id,
        "order_amount": amount,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(user_id),
            "customer_name": user_name,
            "customer_email": "customer@example.com",
            "customer_phone": "9999999999"
        },
        "order_meta": {
            "notify_url": f"{RENDER_URL}/cashfree-webhook"
        }
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        logger.info(f"Cashfree order response: {data}")
        return data
    except Exception as e:
        logger.error(f"Cashfree order creation error: {e}")
        return None

def verify_cashfree_signature(post_data, signature):
    """Cashfree webhook signature verify"""
    try:
        message = post_data
        secret = CASHFREE_SECRET_KEY.encode('utf-8')
        expected = hmac.new(secret, message.encode('utf-8'), hashlib.sha256).digest()
        import base64
        expected_b64 = base64.b64encode(expected).decode('utf-8')
        return hmac.compare_digest(expected_b64, signature)
    except Exception as e:
        logger.error(f"Signature verify error: {e}")
        return False

# ============ HTTP SERVER (Webhook) ============

bot_app = None  # global bot reference

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def do_POST(self):
        if self.path == "/cashfree-webhook":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            logger.info(f"Webhook received: {post_data}")

            try:
                data = json.loads(post_data)
                event_type = data.get("type", "")

                if event_type == "PAYMENT_SUCCESS_WEBHOOK":
                    order_data = data.get("data", {}).get("order", {})
                    payment_data = data.get("data", {}).get("payment", {})
                    order_id = order_data.get("order_id", "")
                    payment_status = payment_data.get("payment_status", "")

                    if payment_status == "SUCCESS" and order_id in pending_payments:
                        threading.Thread(
                            target=handle_payment_success,
                            args=(order_id,),
                            daemon=True
                        ).start()

            except Exception as e:
                logger.error(f"Webhook processing error: {e}")

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def handle_payment_success(order_id):
    """Payment success hone par auto approve karo"""
    import asyncio
    if bot_app and order_id in pending_payments:
        settings = load_settings()
        user_id = pending_payments[order_id]["user_id"]
        amount = pending_payments[order_id]["amount"]

        async def send_approval():
            try:
                await bot_app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🎉 *PAYMENT VERIFIED!*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n\n"
                        f"✅ ₹{amount}/- payment auto-verify ho gayi!\n"
                        f"🔖 Order: `{order_id}`\n\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🎁 *Tumhara Premium App Link:*\n\n"
                        f"👇👇👇\n"
                        f"{settings['app_link']}\n"
                        f"━━━━━━━━━━━━━━━━━━━\n\n"
                        f"⚠️ Yeh link sirf tumhare liye hai!\n"
                        f"🆘 Problem? /help likho"
                    ),
                    parse_mode="Markdown"
                )
                pending_payments[order_id]["status"] = "approved"

                # Admin ko notify karo
                await bot_app.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"✅ *AUTO PAYMENT VERIFIED*\n\n"
                        f"👤 User ID: `{user_id}`\n"
                        f"🔖 Order: `{order_id}`\n"
                        f"💰 Amount: ₹{amount}/-\n"
                        f"🤖 Cashfree se auto-verify hua!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Auto approval error: {e}")

        asyncio.run(send_approval())

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# ============ USER COMMANDS ============

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
        f"💰 *Sirf ₹{settings['price']}/-* \n"
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

    # Cashfree order create karo
    cf_order = create_cashfree_order(order_id, settings["price"], user.id, user.first_name)

    if cf_order and cf_order.get("payment_link"):
        payment_link = cf_order["payment_link"]
        kb = [[InlineKeyboardButton("💳 Pay Karo", url=payment_link)]]
        await query.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💳 *PAYMENT DETAILS*\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 *Amount:* ₹{settings['price']}/-\n"
            f"🔖 *Order ID:* `{order_id}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"👇 *Pay Karo button dabao:*\n"
            f"UPI, Card, NetBanking sab accepted!\n\n"
            f"✅ Payment ke baad *automatically* app link milega!\n"
            f"━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        # Fallback: UPI QR (agar Cashfree fail ho)
        logger.warning(f"Cashfree order failed, falling back to UPI QR")
        UPI_ID = "BHARATPE.8R0K1Z0V1R62609@fbpe"
        qr_image = make_upi_qr(UPI_ID, settings["price"])
        kb = [[InlineKeyboardButton("✅ Payment Ho Gayi - UTR Daalo", callback_data=f"utr_{order_id}")]]
        await query.message.reply_photo(
            photo=qr_image,
            caption=(
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💳 *PAYMENT DETAILS (UPI)*\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 *UPI ID:*\n`{UPI_ID}`\n\n"
                f"💰 *Amount:* ₹{settings['price']}/-\n"
                f"🔖 *Order ID:* `{order_id}`\n\n"
                f"Payment ke baad UTR button dabao\n"
                f"━━━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

def make_upi_qr(upi_id, amount):
    upi_url = f"upi://pay?pa={upi_id}&pn=PremiumAPK&am={amount}&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

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
        f"ℹ️ UTR kahan milega?\n"
        f"• PhonePe → Transaction History\n"
        f"• GPay → Payment Details\n"
        f"• Paytm → Passbook\n\n"
        f"👇 *Abhi UTR number type karo:*",
        parse_mode="Markdown"
    )

# ============ ADMIN COMMANDS ============

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
        f"💰 *Current Price:* ₹{settings['price']}/-\n"
        f"🔗 *App Link:* `{settings['app_link'][:40]}...`\n\n"
        f"👇 Kya change karna hai?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Sirf admin!", show_alert=True)
        return
    await query.answer()

    if query.data == "admin_price":
        context.user_data["admin_action"] = "change_price"
        await query.message.reply_text(
            "💰 *Naya price daalo:*\n\nSirf number likho (example: 149)",
            parse_mode="Markdown"
        )

    elif query.data == "admin_link":
        context.user_data["admin_action"] = "change_link"
        await query.message.reply_text(
            "🔗 *Naya app download link daalo:*\n\nPura link paste karo",
            parse_mode="Markdown"
        )

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
                        f"✅ ₹{amount}/- payment verify ho gayi!\n"
                        f"🔖 Order: `{order_id}`\n\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🎁 *Tumhara Premium App Link:*\n\n"
                        f"👇👇👇\n"
                        f"{settings['app_link']}\n"
                        f"━━━━━━━━━━━━━━━━━━━\n\n"
                        f"⚠️ Yeh link sirf tumhare liye hai!\n"
                        f"🆘 Problem? /help likho"
                    ),
                    parse_mode="Markdown"
                )
                pending_payments[order_id]["status"] = "approved"
                await query.edit_message_text(
                    f"✅ *APPROVED!*\n\n"
                    f"👤 User ko app link bhej diya!\n"
                    f"🔖 Order: `{order_id}`\n"
                    f"💰 Amount: ₹{amount}/-",
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
                        f"UTR verify nahi hua ya payment nahi mili.\n\n"
                        f"🔄 Dobara try karo: /start\n"
                        f"🆘 Problem? /help likho"
                    ),
                    parse_mode="Markdown"
                )
                pending_payments[order_id]["status"] = "rejected"
                await query.edit_message_text(
                    f"❌ *REJECTED*\n\nOrder: `{order_id}`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Reject error: {e}")

    elif query.data.startswith("changeamt_"):
        order_id = query.data.replace("changeamt_", "")
        context.user_data["admin_action"] = f"change_order_amount_{order_id}"
        await query.message.reply_text(
            f"✏️ *Order ka naya amount daalo:*\n"
            f"🔖 Order: `{order_id}`\n\n"
            f"Sirf number likho (example: 149)",
            parse_mode="Markdown"
        )

# ============ MESSAGE HANDLER ============

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
                await update.message.reply_text(
                    f"✅ *Price Update Ho Gaya!*\n\n"
                    f"💰 Naya Price: ₹{new_price}/-",
                    parse_mode="Markdown"
                )
            except:
                await update.message.reply_text("❌ Sirf number daalo! Example: 149")
            return

        elif action == "change_link":
            settings = load_settings()
            settings["app_link"] = text
            save_settings(settings)
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(
                f"✅ *App Link Update Ho Gaya!*\n\n"
                f"🔗 Naya Link:\n`{text}`",
                parse_mode="Markdown"
            )
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

                    # Naya Cashfree order banao updated amount ke saath
                    cf_order = create_cashfree_order(
                        f"{order_id}U",
                        new_amount,
                        user_id,
                        pending_payments[order_id]["user_name"]
                    )
                    if cf_order and cf_order.get("payment_link"):
                        payment_link = cf_order["payment_link"]
                        kb = [[InlineKeyboardButton("💳 Pay Karo", url=payment_link)]]
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"🔄 *Amount Update Ho Gaya!*\n\n"
                                f"💰 Naya Amount: ₹{new_amount}/-\n"
                                f"🔖 Order: `{order_id}`\n\n"
                                f"Naye link se pay karo!"
                            ),
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
                    await update.message.reply_text(
                        f"✅ Amount ₹{old_amount} se ₹{new_amount} ho gaya!"
                    )
            except:
                await update.message.reply_text("❌ Sirf number daalo!")
            return

    # User UTR submit (fallback UPI ke liye)
    order_id = context.user_data.get("waiting_utr")
    if not order_id:
        return
    if order_id not in pending_payments:
        await update.message.reply_text("❌ Order nahi mila. /start dobara karo.")
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
        f"✅ Admin verify karega!\n"
        f"⏰ 5-10 minutes mein app link milega\n\n"
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
                f"🔔 *MANUAL UTR REQUEST*\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 *User:* {user.first_name}\n"
                f"🆔 *User ID:* `{user.id}`\n"
                f"🔖 *Order:* `{order_id}`\n"
                f"💰 *Amount:* ₹{amount}/-\n"
                f"🧾 *UTR:* `{text}`\n\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
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
        f"/help - Yeh message\n\n"
        f"📞 *Support:* @YourUsername",
        parse_mode="Markdown"
    )

def main():
    global bot_app

    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()
    logger.info("HTTP server started!")

    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("admin", admin_panel))
    bot_app.add_handler(CallbackQueryHandler(pay, pattern="^pay$"))
    bot_app.add_handler(CallbackQueryHandler(utr_prompt, pattern="^utr_"))
    bot_app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_|^approve_|^reject_|^changeamt_"))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("✅ Bot chal raha hai!")
    bot_app.run_polling()

if __name__ == "__main__":
    main()
