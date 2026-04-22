import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import flask
from flask import request, jsonify
import sqlite3
import threading
import os
import re

# === CẤU HÌNH ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8743099227:AAGXQH4f9SUndwnCjahZ9b_Tsa-yQUGOq4g")
ADMIN_ID = os.environ.get("ADMIN_ID", "7816353760") # Để nhận thông báo
PORT = int(os.environ.get("PORT", 5000))

bot = telebot.TeleBot(BOT_TOKEN)
app = flask.Flask(__name__)

# === KHỞI TẠO DATABASE ===
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)''')
    # products: type (1: Group, 2: Channel)
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, type INTEGER, name TEXT, price INTEGER, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_name TEXT, price INTEGER, target_username TEXT, status TEXT)''')
    
    # Thêm dữ liệu mẫu nếu bảng products trống
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO products (type, name, price, description) VALUES (1, 'Group Crypto 10k Mem', 500000, 'Tương tác siêu cao')")
        c.execute("INSERT INTO products (type, name, price, description) VALUES (2, 'Kênh Giải Trí 50k Sub', 1200000, 'Đang kéo view tốt')")
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('bot_data.db', check_same_thread=False)
    return conn

# === WEBHOOK SEPAY NẠP TIỀN TỰ ĐỘNG ===
@app.route('/sepay-webhook', methods=['POST'])
def sepay_webhook():
    try:
        data = request.json
        # API SePay trả về các trường như transferAmount, content, gate...
        amount = int(data.get('transferAmount', 0))
        content = str(data.get('content', '')).upper()
        
        # Cú pháp chuyển khoản: NAP [USER_ID]
        match = re.search(r'NAP\s+(\d+)', content)
        if match and amount > 0:
            user_id = int(match.group(1))
            conn = get_db()
            c = conn.cursor()
            
            # Cộng tiền
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            if c.rowcount == 0: # Nếu user chưa có trong DB, thêm mới
                c.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, amount))
            conn.commit()
            conn.close()
            
            # Gửi thông báo cho khách
            bot.send_message(user_id, f"✅ <b>NẠP TIỀN THÀNH CÔNG</b>\n\nBạn vừa được cộng <b>{amount:,} VNĐ</b> vào tài khoản từ giao dịch ngân hàng!", parse_mode="HTML")
        
        return jsonify({"status": "success", "message": "Webhook processed"}), 200
    except Exception as e:
        print(f"Webhook Error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/')
def home():
    return "Bot is running 24/7 on Render!"

# === CHỨC NĂNG BOT TELEGRAM ===

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
    conn.commit()
    
    markup = InlineKeyboardMarkup(row_width=2)
    btn_group = InlineKeyboardButton("👥 Mua Group", callback_data="catalog_1")
    btn_channel = InlineKeyboardButton("📢 Mua Channel", callback_data="catalog_2")
    btn_topup = InlineKeyboardButton("💳 Nạp Tiền (Auto)", callback_data="topup")
    btn_profile = InlineKeyboardButton("👤 Tài Khoản", callback_data="profile")
    btn_support = InlineKeyboardButton("🎧 Hỗ Trợ", url="https://t.me/YOUR_ADMIN_USERNAME")
    
    markup.add(btn_group, btn_channel, btn_topup, btn_profile, btn_support)
    
    welcome_text = (
        f"👋 Xin chào <b>{message.from_user.first_name}</b>!\n\n"
        f"🌟 Chào mừng đến với <b>Hệ Thống Mua Bán Group & Channel VIP</b>.\n"
        f"⚡️ Hệ thống nạp tiền tự động qua MSB, giao dịch 24/7.\n\n"
        f"Vui lòng chọn chức năng bên dưới:"
    )
    bot.send_message(user_id, welcome_text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    conn = get_db()
    c = conn.cursor()
    
    if call.data.startswith("catalog_"):
        p_type = int(call.data.split("_")[1])
        type_name = "Group" if p_type == 1 else "Channel"
        
        c.execute("SELECT id, name, price FROM products WHERE type = ?", (p_type,))
        products = c.fetchall()
        
        markup = InlineKeyboardMarkup(row_width=1)
        for p in products:
            markup.add(InlineKeyboardButton(f"🛒 {p[1]} - {p[2]:,} VNĐ", callback_data=f"buy_{p[0]}"))
        markup.add(InlineKeyboardButton("🔙 Quay lại", callback_data="back_home"))
        
        bot.edit_message_text(f"🛍 <b>Danh mục {type_name}</b>\nChọn sản phẩm bạn muốn mua:", user_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

    elif call.data == "topup":
        topup_text = (
            "🏦 <b>NẠP TIỀN TỰ ĐỘNG</b>\n\n"
            "Ngân hàng: <b>MSB (Maritime Bank)</b>\n"
            "Số tài khoản: <code>123456789</code>\n" # Thay STK của bạn
            "Chủ tài khoản: <b>NGUYEN VAN A</b>\n\n"
            f"📝 Nội dung chuyển khoản: <code>NAP {user_id}</code>\n\n"
            "<i>(Nhấn vào nội dung để copy. Tiền sẽ được cộng tự động từ 5-10 giây sau khi chuyển khoản thành công)</i>"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Quay lại", callback_data="back_home"))
        bot.edit_message_text(topup_text, user_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

    elif call.data == "profile":
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = c.fetchone()[0]
        profile_text = f"👤 <b>Thông Tin Của Bạn</b>\n\nID: <code>{user_id}</code>\nSố dư: <b>{balance:,} VNĐ</b>"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Quay lại", callback_data="back_home"))
        bot.edit_message_text(profile_text, user_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

    elif call.data.startswith("buy_"):
        product_id = int(call.data.split("_")[1])
        c.execute("SELECT name, price, description FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        
        if not product:
            bot.answer_callback_query(call.id, "Sản phẩm không tồn tại!")
            return
            
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Xác nhận mua", callback_data=f"confirm_{product_id}"),
            InlineKeyboardButton("❌ Hủy", callback_data="back_home")
        )
        detail_text = (
            f"📦 <b>Xác nhận đơn hàng</b>\n\n"
            f"Tên: <b>{product[0]}</b>\n"
            f"Mô tả: {product[2]}\n"
            f"Giá: <b>{product[1]:,} VNĐ</b>\n\n"
            f"Bạn có chắc chắn muốn mua?"
        )
        bot.edit_message_text(detail_text, user_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

    elif call.data.startswith("confirm_"):
        product_id = int(call.data.split("_")[1])
        c.execute("SELECT name, price FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = c.fetchone()[0]
        
        if balance < product[1]:
            bot.answer_callback_query(call.id, "❌ Số dư không đủ. Vui lòng nạp thêm tiền!", show_alert=True)
        else:
            msg = bot.send_message(user_id, "⚠️ <b>YÊU CẦU QUAN TRỌNG:</b>\n\nVui lòng nhập `@username` Telegram của bạn để Admin tiến hành chuyển nhượng quyền Owner:", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_username_step, product[0], product[1])

    elif call.data == "back_home":
        send_welcome(call.message)

    conn.close()

def process_username_step(message, product_name, price):
    user_id = message.from_user.id
    target_username = message.text.strip()
    
    if not target_username.startswith("@"):
        msg = bot.send_message(user_id, "❌ Username không hợp lệ. Vui lòng bắt đầu bằng chữ '@' (Ví dụ: @my_username). Thử lại:")
        bot.register_next_step_handler(msg, process_username_step, product_name, price)
        return

    conn = get_db()
    c = conn.cursor()
    # Kiểm tra lại số dư lần cuối
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = c.fetchone()[0]
    
    if balance >= price:
        # Trừ tiền
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
        # Lưu đơn hàng
        c.execute("INSERT INTO orders (user_id, product_name, price, target_username, status) VALUES (?, ?, ?, ?, 'PENDING')", (user_id, product_name, price, target_username))
        conn.commit()
        
        bot.send_message(user_id, f"✅ <b>MUA THÀNH CÔNG!</b>\n\nBạn đã mua <b>{product_name}</b>.\nHệ thống đã ghi nhận username <code>{target_username}</code>.\n\nAdmin sẽ tiến hành chuyển nhượng (Transfer Ownership) cho bạn trong vài phút tới.", parse_mode="HTML")
        
        # Bắn thông báo về cho Admin
        admin_msg = (
            f"🚨 <b>CÓ ĐƠN HÀNG MỚI</b> 🚨\n\n"
            f"👤 Khách hàng ID: <code>{user_id}</code>\n"
            f"📦 Sản phẩm: <b>{product_name}</b>\n"
            f"💰 Giá trị: {price:,} VNĐ\n"
            f"🎯 <b>Username nhận:</b> {target_username}"
        )
        try:
            bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
        except:
            pass # Bỏ qua nếu chưa cài ADMIN_ID
    else:
        bot.send_message(user_id, "❌ Giao dịch thất bại. Số dư đột nhiên không đủ.")
    
    conn.close()

# === CHẠY ĐỒNG THỜI FLASK VÀ BOT ===
def run_flask():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    print("Bot is starting...")
    bot.infinity_polling()
    
