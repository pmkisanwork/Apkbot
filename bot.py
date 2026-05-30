import logging
import uuid
import requests
import qrcode
import io
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8858208936:AAHw-GRB0rFNf04lmir_6pvPgpt56bjQWe0"
ADMIN_ID = 5908811700
UPI_ID = "BHARATPE.8R0K1Z0V1R62609@fbpe"
APP_DOWNLOAD_LINK = "https://www.mediafire.com/file/w497vl4346qfk3w/SG.apk/file"
DEFAULT_PRICE = 99

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pending_payments = {}

# Render ke liye dummy HTTP server
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

def make_upi_qr(upi_id, amount, name="Premium APK"):
    upi_url = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    kb = [[InlineKeyboardButton("Abhi Kharido - Rs99", callback_data="pay")]]
    await update.message.reply_text(
        f"Aao {user.first_name}!\n\nPremium APK Mod\n\nFull Premium Unlock\nLatest Version\nNo Ads\n\nSirf Rs{DEFAULT_PRICE}/-\n\nButton dabao!",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    order_id = f"UPI_{user.id}_{uuid.uuid4().hex[:6].upper()}"
    pending_payments[order_id] = {"user_id": user.id, "user_name": user.first_name, "amount": DEFAULT_PRICE, "status": "pending"}
    qr_image = make_upi_qr(UPI_ID, DEFAULT_PRICE)
    kb = [[InlineKeyboardButton("UTR Number Daalo", callback_data=f"utr_{order_id}")]]
    await query.message.reply_photo(
        photo=qr_image,
        caption=f"Payment Details:\n\nUPI ID: {UPI_ID}\nAmount: Rs{DEFAULT_PRICE}/-\nOrder: {order_id}\n\nQR scan karo ya UPI ID pe pay karo!\n\nPayment ke baad UTR button dabao!",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def utr_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = query.data.replace("utr_", "")
    context.user_data["waiting_utr"] = order_id
    await query.message.reply_text(f"Apna UTR / Transaction ID daalo:\n\nOrder: {order_id}\n\nUTR number aapke UPI app mein transaction details mein milega")

async def receive_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if user.id == ADMIN_ID and context.user_data.get("changing_amount"):
        order_id = context.user_data.get("changing_amount")
        try:
            new_amount = int(text)
            if order_id in pending_payments:
                old_amount = pending_payments[order_id]["amount"]
                pending_payments[order_id]["amount"] = new_amount
                user_id = pending_payments[order_id]["user_id"]
                context.user_data.pop("changing_amount", None)
                qr_image = make_upi_qr(UPI_ID, new_amount)
                kb = [[InlineKeyboardButton("UTR Number Daalo", callback_data=f"utr_{order_id}")]]
                await context.bot.send_photo(chat_id=user_id, photo=qr_image, caption=f"Amount Update!\n\nNaya Amount: Rs{new_amount}/-\nUPI ID: {UPI_ID}\nOrder: {order_id}\n\nNaya QR scan karo!", reply_markup=InlineKeyboardMarkup(kb))
                await update.message.reply_text(f"Amount Rs{old_amount} se Rs{new_amount} ho gaya!")
        except:
            await update.message.reply_text("Sirf number daalo! Example: 149")
        return

    order_id = context.user_data.get("waiting_utr")
    if not order_id:
        return
    if order_id not in pending_payments:
        await update.message.reply_text("Order nahi mila. /start dobara karo.")
        return

    pending_payments[order_id]["utr"] = text
    pending_payments[order_id]["status"] = "utr_submitted"
    context.user_data.pop("waiting_utr", None)
    amount = pending_payments[order_id]["amount"]

    await update.message.reply_text(f"Payment Verification Pending...\n\nOrder: {order_id}\nAmount: Rs{amount}/-\nUTR: {text}\n\nAdmin verify karega!\nThoda wait karo...")

    try:
        kb = [[InlineKeyboardButton("Approve", callback_data=f"approve_{order_id}"), InlineKeyboardButton("Reject", callback_data=f"reject_{order_id}")], [InlineKeyboardButton("Amount Change Karo", callback_data=f"changeamt_{order_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"Naya Payment!\n\nUser: {user.first_name}\nID: {user.id}\nOrder: {order_id}\nAmount: Rs{amount}/-\nUTR: {text}\n\nAction lo:", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        logger.error(f"Admin notification failed: {e}")

async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Sirf admin kar sakta hai!", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data.startswith("approve_"):
        order_id = data.replace("approve_", "")
        if order_id in pending_payments:
            user_id = pending_payments[order_id]["user_id"]
            amount = pending_payments[order_id]["amount"]
            try:
                await context.bot.send_message(chat_id=user_id, text=f"Payment Approved!\n\nRs{amount}/- verify ho gayi!\n\nApp Link:\n{APP_DOWNLOAD_LINK}\n\nYeh link sirf tumhare liye hai!")
                pending_payments[order_id]["status"] = "approved"
                await query.edit_message_text(f"APPROVED\n\nOrder: {order_id}\nAmount: Rs{amount}/-")
            except Exception as e:
                logger.error(f"Approve error: {e}")

    elif data.startswith("reject_"):
        order_id = data.replace("reject_", "")
        if order_id in pending_payments:
            user_id = pending_payments[order_id]["user_id"]
            try:
                await context.bot.send_message(chat_id=user_id, text="Payment Verify Nahi Hui!\n\nDobara try karo: /start")
                pending_payments[order_id]["status"] = "rejected"
                await query.edit_message_text(f"REJECTED\n\nOrder: {order_id}")
            except Exception as e:
                logger.error(f"Reject error: {e}")

    elif data.startswith("changeamt_"):
        order_id = data.replace("changeamt_", "")
        context.user_data["changing_amount"] = order_id
        await query.message.reply_text(f"Naya amount daalo:\nOrder: {order_id}\n\nSirf number likho (example: 149)")

def main():
    # HTTP server background mein chalao
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()
    logger.info("HTTP server started!")

    # Bot chalao
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(pay, pattern="^pay$"))
    app.add_handler(CallbackQueryHandler(utr_prompt, pattern="^utr_"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^approve_|^reject_|^changeamt_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_utr))
    logger.info("Bot chal raha hai!")
    app.run_polling()

if __name__ == "__main__":
    main()
