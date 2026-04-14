import telebot
from telebot import types
import sqlite3
import requests
import threading
import random
import string
import os
import time
from datetime import datetime, date
from flask import Flask, request, jsonify

# ================= CẤU HÌNH HỆ THỐNG =================
API_TOKEN = 'TOKEN_BOT_CHINH_CUA_BAN' # Điền Token Bot Telegram vào đây
ADMIN_ID = 123456789  # Thay bằng ID Telegram của bạn

# Thông tin API lấy từ ảnh của bạn
J2PROXY_API_TOKEN = 'j2proxy3643_eb73d0215ab40bbd9a74b7998e86bff3891aa6ec882ae441631b34761971d540'
J2PROXY_MERCHANT_ID = '2e773742-dc78-4755-bd99-a9f38e9f2c0f'

MIN_BALANCE_FOR_SUBBOT = 50000 
SUBBOT_COMMISSION = 200 
WHEEL_PRICE = 500 

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
app = Flask(__name__)

MAINTENANCE_MODE = False

# ================= DATABASE LOGIC =================
def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect('j2proxy_system.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, params)
    data = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY, 
        username TEXT, 
        balance INTEGER DEFAULT 0, 
        total_deposit INTEGER DEFAULT 0,
        vip_level INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT 0,
        last_checkin DATE,
        is_banned INTEGER DEFAULT 0
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS sub_bots (
        owner_id INTEGER, 
        token TEXT UNIQUE, 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS giftcodes (
        code TEXT PRIMARY KEY,
        value INTEGER,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS history_codes (
        chat_id INTEGER,
        code TEXT
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        amount INTEGER,
        reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

init_db()

# ================= HÀM TIỆN ÍCH =================
def get_user(chat_id, username="Unknown"):
    res = db_query("SELECT balance, total_deposit, vip_level, referrer_id, last_checkin, is_banned FROM users WHERE chat_id=?", (chat_id,), True)
    if not res:
        db_query("INSERT INTO users (chat_id, username, balance) VALUES (?, ?, 0)", (chat_id, username))
        return (0, 0, 0, 0, None, 0)
    return res[0]

def log_transaction(chat_id, amount, reason):
    db_query("INSERT INTO transactions (chat_id, amount, reason) VALUES (?, ?, ?)", (chat_id, amount, reason))

def update_balance(chat_id, amount, is_deposit=False, reason="Không xác định"):
    if is_deposit and amount > 0:
        db_query("UPDATE users SET balance = balance + ?, total_deposit = total_deposit + ? WHERE chat_id = ?", (amount, amount, chat_id))
        _, total_dep, _, _, _, _ = get_user(chat_id)
        new_vip = 0
        if total_dep >= 5000000: new_vip = 3
        elif total_dep >= 1000000: new_vip = 2
        elif total_dep >= 200000: new_vip = 1
        db_query("UPDATE users SET vip_level = ? WHERE chat_id = ?", (new_vip, chat_id))
    else:
        db_query("UPDATE users SET balance = balance + ? WHERE chat_id = ?", (amount, chat_id))
    log_transaction(chat_id, amount, reason)

def get_vip_label(level):
    vips = {0: "🥉 Member", 1: "🥈 VIP 1 (-5%)", 2: "🥇 VIP 2 (-10%)", 3: "👑 DIAMOND (-20%)"}
    return vips.get(level, "🥉 Member")

# ================= J2PROXY.VN API CORE =================
def call_j2proxy_api(proxy_type="ipv4_shared"):
    """
    Kết nối chuẩn tới J2Proxy.vn sử dụng Headers xác thực
    """
    # Lưu ý: Cần đảm bảo endpoint url này khớp với tài liệu API của web (VD: /api/v1/buy-proxy)
    url = "https://j2proxy.vn/api/proxy/buy" 
    
    headers = {
        "Authorization": f"Bearer {J2PROXY_API_TOKEN}",
        "x-merchant-id": J2PROXY_MERCHANT_ID,
        "Content-Type": "application/json"
    }
    
    payload = {
        "type": proxy_type, 
        "days": 1
    }
    
    try:
        # KHI NÀO SẴN SÀNG CHẠY THẬT, HÃY MỞ KHÓA 4 DÒNG CODE DƯỚI ĐÂY BẰNG CÁCH XÓA DẤU #
        # response = requests.post(url, headers=headers, json=payload, timeout=10).json()
        # if response.get('status') == 'success' or response.get('code') == 0:
        #     return response.get('data').get('proxy')
        # return None
        
        # MOCK DATA (Chạy thử giả lập khi chưa kết nối thật)
        ip = f"{random.randint(100,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
        port = random.randint(10000, 65535)
        return f"{ip}:{port}:j2user:j2pass"
    except Exception as e:
        print(f"Lỗi API J2Proxy: {e}")
        return None

# ================= FLASK CHO RENDER & WEBHOOK SEPAY =================
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive", "time": str(datetime.now())})

@app.route('/sepay-webhook', methods=['POST'])
def sepay_webhook():
    data = request.json
    try:
        content = data.get('content', '').upper()
        amount = int(data.get('transferAmount', 0))
        if "NAP" in content:
            user_id = int(''.join(filter(str.isdigit, content)))
            update_balance(user_id, amount, is_deposit=True, reason="Nạp Auto Bank (SePay)")
            
            _, _, _, referrer_id, _, _ = get_user(user_id)
            if referrer_id != 0:
                ref_bonus = int(amount * 0.05)
                update_balance(referrer_id, ref_bonus, reason=f"Hoa hồng REF từ {user_id}")
                bot.send_message(referrer_id, f"💸 <b>TING TING!</b>\nCấp dưới <code>{user_id}</code> nạp {amount:,}đ.\nHoa hồng của bạn: <b>+{ref_bonus:,}đ</b>")
            
            bot.send_message(user_id, f"✅ <b>GIAO DỊCH THÀNH CÔNG!</b>\n💰 Đã cộng: <b>+{amount:,} VNĐ</b>")
    except Exception as e:
        print(f"Lỗi Webhook: {e}")
    return jsonify({"success": True})

# ================= GIAO DIỆN CHÍNH =================
def main_menu(chat_id):
    balance, total_dep, vip, _, _, _ = get_user(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    kb.add(
        types.InlineKeyboardButton("🛒 MUA J2PROXY", callback_data="buy_proxy"),
        types.InlineKeyboardButton("💳 NẠP TIỀN AUTO", callback_data="deposit")
    )
    kb.add(
        types.InlineKeyboardButton("👤 HỒ SƠ", callback_data="profile"),
        types.InlineKeyboardButton("🏆 TOP ĐẠI GIA", callback_data="top_spenders")
    )
    kb.add(
        types.InlineKeyboardButton("🎰 VÒNG QUAY", callback_data="lucky_wheel"),
        types.InlineKeyboardButton("🎁 GIFTCODE", callback_data="enter_giftcode")
    )
    kb.add(
        types.InlineKeyboardButton("🤖 BOT ĐẠI LÝ", callback_data="create_subbot"),
        types.InlineKeyboardButton("🔗 TUYỂN REF", callback_data="get_ref")
    )
    kb.row(
        types.InlineKeyboardButton("📅 ĐIỂM DANH (+50đ)", callback_data="daily_checkin"),
        types.InlineKeyboardButton("🧾 LỊCH SỬ", callback_data="tx_history")
    )
    
    if chat_id == ADMIN_ID:
        kb.row(types.InlineKeyboardButton("🛠 BẢNG ĐIỀU KHIỂN ADMIN 🛠", callback_data="admin_panel"))
        
    status_icon = "🔴 BẢO TRÌ" if MAINTENANCE_MODE else "🟢 HOẠT ĐỘNG"
    
    text = (
        "┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        "      🚀 <b>J2PROXY PREMIUM BOT</b> 🚀      \n"
        "┗━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"🆔 Mã Khách Hàng: <code>{chat_id}</code>\n"
        f"💰 Số Dư Khả Dụng: <b>{balance:,} VNĐ</b>\n"
        f"🎖 Cấp Bậc: <b>{get_vip_label(vip)}</b>\n"
        f"⚡️ Máy Chủ J2 API: {status_icon}\n"
        "───────────────────────\n"
        "👇 <i>Chọn dịch vụ bạn muốn sử dụng:</i>"
    )
    return text, kb

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    username = message.from_user.username
    
    res = db_query("SELECT is_banned FROM users WHERE chat_id=?", (chat_id,), True)
    if res and res[0][0] == 1:
        bot.send_message(chat_id, "🚫 Tài khoản của bạn đã bị khóa bởi Admin.")
        return

    ref_id = 0
    if len(message.text.split()) > 1:
        try: ref_id = int(message.text.split()[1])
        except: pass
        
    if not res:
        db_query("INSERT INTO users (chat_id, username, balance, referrer_id) VALUES (?, ?, 0, ?)", (chat_id, username, ref_id))
        if ref_id != 0 and ref_id != chat_id:
            try: bot.send_message(ref_id, f"🎉 <b>CÓ THÀNH VIÊN MỚI!</b>\nAi đó vừa đăng ký qua link REF của bạn.")
            except: pass
            
    text, kb = main_menu(chat_id)
    bot.send_message(chat_id, text, reply_markup=kb)

# ================= XỬ LÝ CALLBACK =================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    user_data = get_user(chat_id)
    balance, total_dep, vip, _, last_checkin, is_banned = user_data
    
    if is_banned:
        bot.answer_callback_query(call.id, "🚫 LỖI: TÀI KHOẢN BỊ KHÓA!", show_alert=True)
        return
        
    if call.data == "back_home":
        text, kb = main_menu(chat_id)
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "profile":
        text = (
            "👤 <b>HỒ SƠ CÁ NHÂN CHI TIẾT</b>\n"
            "───────────────────────\n"
            f"🆔 Telegram ID: <code>{chat_id}</code>\n"
            f"💰 Số dư hiện tại: <b>{balance:,} VNĐ</b>\n"
            f"📈 Tổng tiền đã nạp: <b>{total_dep:,} VNĐ</b>\n"
            f"👑 Hạng thành viên: {get_vip_label(vip)}\n"
            "───────────────────────\n"
            "<i>(Tích lũy nạp để lên VIP nhận ưu đãi giảm giá)</i>"
        )
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "top_spenders":
        top_users = db_query("SELECT chat_id, total_deposit FROM users ORDER BY total_deposit DESC LIMIT 5", fetch=True)
        text = "🏆 <b>BẢNG VÀNG: TOP ĐẠI GIA HỆ THỐNG</b> 🏆\n───────────────────────\n"
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        for i, u in enumerate(top_users):
            hidden_id = str(u[0])[:4] + "****" + str(u[0])[-2:]
            text += f"{medals[i]} ID: <code>{hidden_id}</code> - Nạp: <b>{u[1]:,}đ</b>\n\n"
        
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "tx_history":
        history = db_query("SELECT amount, reason, created_at FROM transactions WHERE chat_id=? ORDER BY id DESC LIMIT 5", (chat_id,), True)
        if not history:
            text = "🧾 Chưa có giao dịch nào phát sinh."
        else:
            text = "🧾 <b>5 GIAO DỊCH MỚI NHẤT:</b>\n───────────────────────\n"
            for tx in history:
                amt = f"+{tx[0]:,}" if tx[0] > 0 else f"{tx[0]:,}"
                text += f"🕒 <code>{tx[2][:16]}</code>\n💵 {amt}đ ➜ <i>{tx[1]}</i>\n\n"
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "deposit":
        text = (
            "💳 <b>CỔNG THANH TOÁN TỰ ĐỘNG (24/7)</b>\n"
            "───────────────────────\n"
            "🏦 Ngân hàng: <b>MSB (Ngân hàng Hàng Hải)</b>\n"
            "🔢 Số tài khoản: <code>123456789</code>\n"
            "👤 Tên chủ TK: <b>NGUYEN VAN A</b>\n\n"
            "⚠️ <b>NỘI DUNG CHUYỂN KHOẢN BẮT BUỘC:</b>\n"
            f"👉 <code>NAP {chat_id}</code> 👈\n\n"
            "<i>(Click vào nội dung để copy. Sai nội dung không được cộng tiền. Hệ thống xử lý trong 5-10 giây.)</i>"
        )
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "buy_proxy":
        if MAINTENANCE_MODE:
            bot.answer_callback_query(call.id, "🛠 Hệ thống đang nâng cấp, thử lại sau!", show_alert=True)
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("🌐 IPv4 Share VN (4k/ngày)", callback_data="order_j2_share"),
            types.InlineKeyboardButton("🚀 IPv4 Private VN (10k/ngày)", callback_data="order_j2_private"),
            types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")
        )
        bot.edit_message_text("🛒 <b>KHO HÀNG J2PROXY</b>\nChọn cấu hình Proxy phù hợp với bạn:", chat_id, call.message.message_id, reply_markup=kb)

    elif call.data.startswith("order_j2_"):
        ptype = call.data.split("_")[2] # 'share' hoặc 'private'
        base_price = 4000 if ptype == "share" else 10000
        api_type = "ipv4_shared" if ptype == "share" else "ipv4_private"
        
        price = base_price
        if vip == 1: price = int(price * 0.95)
        elif vip == 2: price = int(price * 0.9)
        elif vip == 3: price = int(price * 0.8)
        
        if balance < price:
            bot.answer_callback_query(call.id, f"❌ Số dư không đủ! Cần {price:,}đ. Hãy nạp tiền.", show_alert=True)
            return
            
        bot.edit_message_text("⏳ <i>Đang khởi tạo kết nối đến máy chủ J2Proxy...</i>", chat_id, call.message.message_id)
        
        proxy = call_j2proxy_api(api_type)
        if proxy:
            update_balance(chat_id, -price, reason=f"Mua Proxy {ptype.upper()}")
            
            receipt = (
                "✅ <b>GIAO DỊCH THÀNH CÔNG</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 Mã GD: <code>#J2P_{random.randint(10000, 99999)}</code>\n"
                f"Loại: <b>{api_type.replace('_', ' ').upper()}</b>\n"
                f"Giá tiền: <b>{price:,} VNĐ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🔐 <b>THÔNG TIN PROXY:</b>\n"
                f"<code>{proxy}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>💵 Số dư còn lại: {balance - price:,} VNĐ</i>"
            )
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
            bot.edit_message_text(receipt, chat_id, call.message.message_id, reply_markup=kb)
        else:
            bot.edit_message_text("⚠️ <b>HẾT HÀNG HOẶC LỖI KẾT NỐI API</b>\nKho Proxy hiện tại tạm thời hết tài nguyên hoặc Token API sai. Vui lòng thử lại sau.", chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")))

    elif call.data == "lucky_wheel":
        text = (
            "🎰 <b>VÒNG QUAY NHÂN PHẨM</b> 🎰\n\n"
            f"Chi phí: <b>{WHEEL_PRICE}đ / lượt</b>\n\n"
            "🎁 <b>Giải thưởng:</b>\n"
            "▪️ 1,000đ (10%)\n"
            "▪️ 200đ (30%)\n"
            "▪️ Chúc bạn may mắn lần sau (60%)\n\n"
            "<i>Nhấn nút bên dưới để thử vận may!</i>"
        )
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(f"🕹 QUAY NGAY (-{WHEEL_PRICE}đ)", callback_data="spin_wheel"),
            types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "spin_wheel":
        if balance < WHEEL_PRICE:
            bot.answer_callback_query(call.id, f"❌ Bạn không đủ {WHEEL_PRICE}đ để quay!", show_alert=True)
            return
            
        bot.answer_callback_query(call.id, "🎰 Vòng quay đang chạy...")
        update_balance(chat_id, -WHEEL_PRICE, reason="Chơi Vòng Quay")
        
        chance = random.randint(1, 100)
        if chance <= 10:
            prize = 1000
            msg = "🎉 <b>NỔ HŨ!</b> Chúc mừng bạn quay trúng <b>1,000 VNĐ</b>!"
        elif chance <= 40:
            prize = 200
            msg = "👍 <b>HƠI ĐEN XÍU!</b> Bạn quay trúng <b>200 VNĐ</b>."
        else:
            prize = 0
            msg = "😭 <b>XUI QUÁ!</b> Quay vào ô mất lượt. Thử lại nào!"
            
        if prize > 0:
            update_balance(chat_id, prize, reason="Trúng thưởng Vòng Quay")
            
        kb = types.InlineKeyboardMarkup(row_width=1).add(
            types.InlineKeyboardButton("🔄 QUAY TIẾP", callback_data="spin_wheel"),
            types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")
        )
        bot.edit_message_text(f"🎰 <b>KẾT QUẢ VÒNG QUAY</b>\n\n{msg}", chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "daily_checkin":
        today = str(date.today())
        if last_checkin == today:
            bot.answer_callback_query(call.id, "❌ Hôm nay bạn đã điểm danh rồi!", show_alert=True)
        else:
            reward = 50 
            update_balance(chat_id, reward, reason="Điểm danh Hàng Ngày")
            db_query("UPDATE users SET last_checkin = ? WHERE chat_id = ?", (today, chat_id))
            bot.answer_callback_query(call.id, f"🎉 Tuyệt vời! Bạn nhận được {reward}đ", show_alert=True)
            bot.send_message(chat_id, f"📅 <b>ĐIỂM DANH THÀNH CÔNG</b>\nĐã cộng <b>+{reward} VNĐ</b> vào tài khoản.")

    elif call.data == "get_ref":
        ref_link = f"https://t.me/{bot.get_me().username}?start={chat_id}"
        text = (
            "🤝 <b>CHƯƠNG TRÌNH ĐỐI TÁC (AFFILIATE)</b>\n"
            "───────────────────────\n"
            f"🔗 Link giới thiệu của bạn:\n<code>{ref_link}</code>\n\n"
            "🎁 <b>Quyền lợi:</b>\n"
            "Nhận ngay hoa hồng <b>5%</b> mỗi khi người bạn giới thiệu nạp tiền vào hệ thống. Thu nhập thụ động vĩnh viễn!"
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")))

    elif call.data == "enter_giftcode":
        msg = bot.send_message(chat_id, "🎁 <b>KHO BÁU GIFTCODE</b>\nNhập mã Code bạn săn được xuống đây:")
        bot.register_next_step_handler(msg, process_giftcode)

    elif call.data == "create_subbot":
        if balance < MIN_BALANCE_FOR_SUBBOT:
            bot.answer_callback_query(call.id, f"❌ Yêu cầu số dư: {MIN_BALANCE_FOR_SUBBOT:,}đ!", show_alert=True)
            return
        msg = bot.send_message(chat_id, "🤖 <b>XƯỞNG TẠO BOT ĐẠI LÝ</b>\nGửi <b>API Token</b> bot con của bạn (Tạo từ @BotFather):")
        bot.register_next_step_handler(msg, create_subbot_process)

    # ================= ADMIN PANEL QUYỀN LỰC =================
    elif call.data == "admin_panel" and chat_id == ADMIN_ID:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("📢 Gửi Broadcast", callback_data="adm_broadcast"),
            types.InlineKeyboardButton("🎁 Tạo Giftcode", callback_data="adm_giftcode")
        )
        kb.add(
            types.InlineKeyboardButton("🔧 Bật/Tắt Bảo trì", callback_data="adm_maintenance"),
            types.InlineKeyboardButton("📊 Báo cáo Doanh Thu", callback_data="adm_stats")
        )
        kb.add(
            types.InlineKeyboardButton("🔍 Tra cứu User", callback_data="adm_checkuser"),
            types.InlineKeyboardButton("🚫 Trừng phạt (Ban)", callback_data="adm_ban")
        )
        kb.add(types.InlineKeyboardButton("🔙 Thoát Panel", callback_data="back_home"))
        bot.edit_message_text("🛠 <b>TRUNG TÂM KIỂM SOÁT (ADMIN)</b>", chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "adm_maintenance" and chat_id == ADMIN_ID:
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        bot.answer_callback_query(call.id, f"Trạng thái Bảo trì: {'BẬT 🔴' if MAINTENANCE_MODE else 'TẮT 🟢'}", show_alert=True)

    elif call.data == "adm_stats" and chat_id == ADMIN_ID:
        u_count = db_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
        b_count = db_query("SELECT COUNT(*) FROM sub_bots", fetch=True)[0][0]
        total_dep = db_query("SELECT SUM(total_deposit) FROM users", fetch=True)[0][0] or 0
        text = f"📊 <b>BÁO CÁO HỆ THỐNG</b>\n👥 Tổng User: {u_count}\n🤖 Tổng Sub-Bot: {b_count}\n💵 Tổng dòng tiền đã nạp: <b>{total_dep:,}đ</b>"
        bot.answer_callback_query(call.id, text, show_alert=True)

    elif call.data == "adm_giftcode" and chat_id == ADMIN_ID:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        db_query("INSERT INTO giftcodes (code, value, max_uses) VALUES (?, ?, ?)", (code, 5000, 10))
        bot.send_message(chat_id, f"✅ Đã gen Code: <code>{code}</code>\n(Giá trị: 5,000đ - Lượt: 10)")

    elif call.data == "adm_broadcast" and chat_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "Nhập nội dung thư gửi toàn server:")
        bot.register_next_step_handler(msg, process_broadcast)
        
    elif call.data == "adm_checkuser" and chat_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "Nhập Telegram ID của người dùng:")
        bot.register_next_step_handler(msg, admin_check_user)
        
    elif call.data == "adm_ban" and chat_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "Nhập ID và Lệnh (VD Khóa: 12345 1 | Mở: 12345 0):")
        bot.register_next_step_handler(msg, admin_ban_user)

# ================= HÀM XỬ LÝ NHẬP LIỆU =================
def process_giftcode(message):
    chat_id = message.chat.id
    code = message.text.strip().upper()
    used = db_query("SELECT * FROM history_codes WHERE chat_id=? AND code=?", (chat_id, code), True)
    if used:
        bot.send_message(chat_id, "❌ Mã này bạn xài rồi cha nội!")
        return
    gift = db_query("SELECT value, max_uses, used_count FROM giftcodes WHERE code=?", (code,), True)
    if gift:
        val, max_u, used_c = gift[0]
        if used_c >= max_u: bot.send_message(chat_id, "❌ Code đã đạt giới hạn lượt nhập.")
        else:
            db_query("UPDATE giftcodes SET used_count = used_count + 1 WHERE code=?", (code,))
            db_query("INSERT INTO history_codes (chat_id, code) VALUES (?, ?)", (chat_id, code))
            update_balance(chat_id, val, reason=f"Nạp Giftcode {code}")
            bot.send_message(chat_id, f"🔥 <b>THÀNH CÔNG!</b> Bạn lụm được <b>{val:,} VNĐ</b>")
    else: bot.send_message(chat_id, "❌ Code dỏm, không tồn tại!")

def process_broadcast(message):
    users = db_query("SELECT chat_id FROM users", fetch=True)
    success = 0
    for u in users:
        try: 
            bot.send_message(u[0], f"📣 <b>THÔNG BÁO HỆ THỐNG</b> 📣\n───────────────────────\n{message.text}")
            success += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ Đã bắn tin đến {success} user.")

def admin_check_user(message):
    try:
        uid = int(message.text.strip())
        b, t, v, ref, _, ban = get_user(uid)
        bot.send_message(ADMIN_ID, f"👤 <b>INFO ID:</b> <code>{uid}</code>\n💵 Balance: {b}\n📈 Nạp: {t}\n🎖 VIP: {v}\n🔗 Giới thiệu bởi: {ref}\n🚫 Bị khóa: {'YES' if ban else 'NO'}")
    except: bot.send_message(ADMIN_ID, "❌ ID nhập sai.")

def admin_ban_user(message):
    try:
        uid, status = map(int, message.text.split())
        db_query("UPDATE users SET is_banned = ? WHERE chat_id = ?", (status, uid))
        bot.send_message(ADMIN_ID, f"✅ Execute Order {status} cho ID {uid}")
    except: bot.send_message(ADMIN_ID, "❌ Sai cú pháp.")

# ================= HỆ THỐNG SUB-BOT =================
def create_subbot_process(message):
    token = message.text.strip()
    chat_id = message.chat.id
    try:
        update_balance(chat_id, -MIN_BALANCE_FOR_SUBBOT, reason="Build Bot Affiliate")
        db_query("INSERT INTO sub_bots (owner_id, token) VALUES (?, ?)", (chat_id, token))
        bot.send_message(chat_id, "✅ <b>BOT CỦA BẠN ĐÃ LÊN SÓNG!</b>\nTừ giờ, khách mua hàng qua bot của bạn, bạn bú lãi 200đ/đơn thụ động.")
        threading.Thread(target=run_sub_bot, args=(token, chat_id), daemon=True).start()
    except sqlite3.IntegrityError:
        bot.send_message(chat_id, "❌ Token này đã có thằng khác xài!")
        update_balance(chat_id, MIN_BALANCE_FOR_SUBBOT, reason="Refund lỗi Build Bot")

def run_sub_bot(token, owner_id):
    try:
        sub_bot = telebot.TeleBot(token, parse_mode='HTML')
        @sub_bot.message_handler(commands=['start', 'mua'])
        def sub_handler(m):
            if m.text == '/start':
                sub_bot.reply_to(m, "👋 <b>ĐẠI LÝ J2PROXY ỦY QUYỀN</b>\nGõ /mua để lên đơn siêu tốc.")
            elif m.text == '/mua':
                if MAINTENANCE_MODE:
                    sub_bot.reply_to(m, "Hệ thống tổng đang bảo trì!")
                    return
                buyer_id = m.chat.id
                balance = get_user(buyer_id)[0]
                price = 4000
                if balance < price:
                    sub_bot.reply_to(m, f"❌ Thiếu lúa! Cần {price:,}đ. Nạp bên @{bot.get_me().username}")
                    return
                
                sub_bot.reply_to(m, "⏳ Đang trích xuất dữ liệu...")
                proxy = call_j2proxy_api("ipv4_shared")
                if proxy:
                    update_balance(buyer_id, -price, reason="Mua Proxy qua Đại Lý")
                    update_balance(owner_id, SUBBOT_COMMISSION, reason=f"Lãi đơn hàng từ {buyer_id}")
                    
                    sub_bot.send_message(buyer_id, f"✅ <b>CHỐT ĐƠN!</b>\n🔐 Proxy: <code>{proxy}</code>")
                    try: bot.send_message(owner_id, f"🤑 <b>TING TING!</b> Khách vừa mua hàng, cộng lãi <b>+{SUBBOT_COMMISSION}đ</b>")
                    except: pass
                else:
                    sub_bot.reply_to(m, "⚠️ Cháy hàng rồi người anh em.")
        sub_bot.polling(none_stop=True)
    except Exception as e: print(e)

# ================= LAUNCH SEQUENCE =================
if __name__ == '__main__':
    print("Khởi động Sub-bot engine...")
    bots = db_query("SELECT token, owner_id FROM sub_bots", fetch=True)
    for b in bots:
        threading.Thread(target=run_sub_bot, args=(b[0], b[1]), daemon=True).start()
        
    print("Khởi động Main Bot engine...")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    
    print("🚀 J2PROXY ENTERPRISE READY TO LAUNCH 🚀")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
