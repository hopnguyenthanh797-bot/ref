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
SUPPORT_LINK = 'https://t.me/username_cua_ban' # Link hỗ trợ

# Thông tin API lấy từ ảnh của bạn
J2PROXY_API_TOKEN = 'j2proxy3643_eb73d0215ab40bbd9a74b7998e86bff3891aa6ec882ae441631b34761971d540'
J2PROXY_MERCHANT_ID = '2e773742-dc78-4755-bd99-a9f38e9f2c0f'

MIN_BALANCE_FOR_SUBBOT = 50000 
SUBBOT_COMMISSION = 200 
WHEEL_PRICE = 500 

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
app = Flask(__name__)

# Khai báo toàn cục ĐÚNG CHUẨN
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
    # Bảng mới: Yêu cầu rút tiền đại lý
    db_query('''CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        amount INTEGER,
        bank_info TEXT,
        status TEXT DEFAULT 'pending',
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
        # response = requests.post(url, headers=headers, json=payload, timeout=10).json()
        # if response.get('status') == 'success' or response.get('code') == 0:
        #     return response.get('data').get('proxy')
        # return None
        
        # MOCK DATA giả lập test khi chưa gọi API thật
        ip = f"{random.randint(100,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
        port = random.randint(10000, 65535)
        return f"{ip}:{port}:j2user:j2pass"
    except Exception as e:
        print(f"Lỗi API J2Proxy: {e}")
        return None

# ================= FLASK & WEBHOOK =================
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
            update_balance(user_id, amount, is_deposit=True, reason="Nạp Auto Bank")
            
            _, _, _, referrer_id, _, _ = get_user(user_id)
            if referrer_id != 0:
                ref_bonus = int(amount * 0.05)
                update_balance(referrer_id, ref_bonus, reason=f"Hoa hồng REF ({user_id})")
                try: bot.send_message(referrer_id, f"💸 <b>TING TING!</b>\nCấp dưới nạp {amount:,}đ.\nHoa hồng: <b>+{ref_bonus:,}đ</b>")
                except: pass
            
            try: bot.send_message(user_id, f"✅ <b>GIAO DỊCH THÀNH CÔNG!</b>\n💰 Đã cộng: <b>+{amount:,} VNĐ</b>")
            except: pass
    except Exception as e:
        print(f"Lỗi Webhook: {e}")
    return jsonify({"success": True})

# ================= GIAO DIỆN CHÍNH =================
def main_menu(chat_id):
    balance, total_dep, vip, _, _, _ = get_user(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    # Mở rộng số lượng nút, quy mô lớn hơn
    kb.add(
        types.InlineKeyboardButton("🛒 MUA J2PROXY", callback_data="buy_proxy"),
        types.InlineKeyboardButton("💳 NẠP TIỀN AUTO", callback_data="deposit")
    )
    kb.add(
        types.InlineKeyboardButton("👤 HỒ SƠ", callback_data="profile"),
        types.InlineKeyboardButton("🏆 ĐUA TOP", callback_data="top_spenders")
    )
    kb.add(
        types.InlineKeyboardButton("🎰 VÒNG QUAY", callback_data="lucky_wheel"),
        types.InlineKeyboardButton("🎁 GIFTCODE", callback_data="enter_giftcode")
    )
    kb.add(
        types.InlineKeyboardButton("🤖 BOT ĐẠI LÝ", callback_data="create_subbot"),
        types.InlineKeyboardButton("🔗 TUYỂN REF", callback_data="get_ref")
    )
    kb.add(
        types.InlineKeyboardButton("📅 ĐIỂM DANH", callback_data="daily_checkin"),
        types.InlineKeyboardButton("🧾 LỊCH SỬ", callback_data="tx_history")
    )
    kb.add(
        types.InlineKeyboardButton("📖 HƯỚNG DẪN", callback_data="guide"),
        types.InlineKeyboardButton("🎧 HỖ TRỢ", url=SUPPORT_LINK)
    )
    
    if chat_id == ADMIN_ID:
        kb.row(types.InlineKeyboardButton("🛠 BẢNG ĐIỀU KHIỂN ADMIN 🛠", callback_data="admin_panel"))
        
    status_icon = "🔴 ĐANG BẢO TRÌ" if MAINTENANCE_MODE else "🟢 HOẠT ĐỘNG TỐT"
    
    text = (
        "┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        "      🚀 <b>J2PROXY PREMIUM BOT</b> 🚀      \n"
        "┗━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"🆔 Mã Khách Hàng: <code>{chat_id}</code>\n"
        f"💰 Số Dư Khả Dụng: <b>{balance:,} VNĐ</b>\n"
        f"🎖 Cấp Bậc: <b>{get_vip_label(vip)}</b>\n"
        f"⚡️ Máy Chủ J2 API: {status_icon}\n"
        "───────────────────────\n"
        "👇 <i>Chọn dịch vụ bên dưới:</i>"
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
    global MAINTENANCE_MODE # CHÚ Ý: ĐÃ SỬA LỖI Ở ĐÂY, DECLARE NGAY DÒNG ĐẦU TIÊN
    
    chat_id = call.message.chat.id
    user_data = get_user(chat_id)
    balance, total_dep, vip, _, last_checkin, is_banned = user_data
    
    if is_banned:
        bot.answer_callback_query(call.id, "🚫 LỖI: TÀI KHOẢN BỊ KHÓA!", show_alert=True)
        return
        
    if call.data == "back_home":
        text, kb = main_menu(chat_id)
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "guide":
        text = (
            "📖 <b>HƯỚNG DẪN SỬ DỤNG</b>\n"
            "───────────────────────\n"
            "1️⃣ <b>Nạp tiền:</b> Chọn 'Nạp Tiền Auto', chuyển đúng nội dung. Tiền vào sau 5s.\n"
            "2️⃣ <b>Mua Proxy:</b> Mua xong sẽ nhận định dạng IP:PORT:USER:PASS.\n"
            "3️⃣ <b>Bot Đại Lý:</b> Cần 50k. Bot tự chạy song song, bạn nhận 200đ mỗi khi có người mua proxy trên bot của bạn.\n"
            "4️⃣ <b>Lên VIP:</b> Nạp đạt mốc 200k, 1M, 5M để giảm giá mua proxy vĩnh viễn.\n"
        )
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "profile":
        text = (
            "👤 <b>HỒ SƠ CÁ NHÂN</b>\n"
            "───────────────────────\n"
            f"🆔 Telegram ID: <code>{chat_id}</code>\n"
            f"💰 Số dư: <b>{balance:,} VNĐ</b>\n"
            f"📈 Tổng nạp: <b>{total_dep:,} VNĐ</b>\n"
            f"👑 Cấp bậc: {get_vip_label(vip)}\n"
        )
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("💸 YÊU CẦU RÚT TIỀN ĐẠI LÝ", callback_data="withdraw_fund"),
            types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "withdraw_fund":
        if balance < 100000:
            bot.answer_callback_query(call.id, "❌ Cần tối thiểu 100,000đ để rút!", show_alert=True)
            return
        msg = bot.send_message(chat_id, "💸 <b>RÚT TIỀN</b>\nNhập Tên Ngân Hàng - STK - Tên Chủ TK (Hoặc gõ 'huy' để hủy):")
        bot.register_next_step_handler(msg, process_withdrawal)

    elif call.data == "top_spenders":
        top_users = db_query("SELECT chat_id, total_deposit FROM users ORDER BY total_deposit DESC LIMIT 5", fetch=True)
        text = "🏆 <b>TOP ĐẠI GIA HỆ THỐNG</b> 🏆\n───────────────────────\n"
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        for i, u in enumerate(top_users):
            hidden_id = str(u[0])[:4] + "****" + str(u[0])[-2:]
            text += f"{medals[i]} ID: <code>{hidden_id}</code> - Nạp: <b>{u[1]:,}đ</b>\n\n"
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "tx_history":
        history = db_query("SELECT amount, reason, created_at FROM transactions WHERE chat_id=? ORDER BY id DESC LIMIT 5", (chat_id,), True)
        if not history:
            text = "🧾 Chưa có giao dịch nào."
        else:
            text = "🧾 <b>5 GIAO DỊCH MỚI NHẤT:</b>\n───────────────────────\n"
            for tx in history:
                amt = f"+{tx[0]:,}" if tx[0] > 0 else f"{tx[0]:,}"
                text += f"🕒 <code>{tx[2][:16]}</code>\n💵 {amt}đ ➜ <i>{tx[1]}</i>\n\n"
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "deposit":
        text = (
            "💳 <b>CỔNG THANH TOÁN TỰ ĐỘNG</b>\n"
            "───────────────────────\n"
            "🏦 Ngân hàng: <b>MSB (Hàng Hải)</b>\n"
            "🔢 Số tài khoản: <code>123456789</code>\n"
            "👤 Tên chủ TK: <b>NGUYEN VAN A</b>\n\n"
            "⚠️ <b>NỘI DUNG CHUYỂN KHOẢN:</b>\n"
            f"👉 <code>NAP {chat_id}</code> 👈\n"
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
        bot.edit_message_text("🛒 <b>KHO HÀNG J2PROXY</b>\nChọn gói Proxy:", chat_id, call.message.message_id, reply_markup=kb)

    elif call.data.startswith("order_j2_"):
        ptype = call.data.split("_")[2]
        base_price = 4000 if ptype == "share" else 10000
        api_type = "ipv4_shared" if ptype == "share" else "ipv4_private"
        
        price = base_price
        if vip == 1: price = int(price * 0.95)
        elif vip == 2: price = int(price * 0.9)
        elif vip == 3: price = int(price * 0.8)
        
        if balance < price:
            bot.answer_callback_query(call.id, f"❌ Cần {price:,}đ. Hãy nạp tiền.", show_alert=True)
            return
            
        bot.edit_message_text("⏳ <i>Đang trích xuất dữ liệu Proxy...</i>", chat_id, call.message.message_id)
        
        proxy = call_j2proxy_api(api_type)
        if proxy:
            update_balance(chat_id, -price, reason=f"Mua Proxy {ptype.upper()}")
            receipt = (
                "✅ <b>GIAO DỊCH THÀNH CÔNG</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 Mã GD: <code>#J2P_{random.randint(10000, 99999)}</code>\n"
                f"Loại: <b>{api_type.upper()}</b>\n"
                f"Giá tiền: <b>{price:,} VNĐ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔐 <b>PROXY:</b>\n<code>{proxy}</code>\n"
                f"<i>💵 Số dư còn lại: {balance - price:,} VNĐ</i>"
            )
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home"))
            bot.edit_message_text(receipt, chat_id, call.message.message_id, reply_markup=kb)
        else:
            bot.edit_message_text("⚠️ <b>LỖI KẾT NỐI API HOẶC HẾT HÀNG</b>", chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")))

    elif call.data == "lucky_wheel":
        text = (f"🎰 <b>VÒNG QUAY NHÂN PHẨM</b>\nChi phí: <b>{WHEEL_PRICE}đ/lượt</b>\nGiải: 1,000đ, 200đ hoặc Mất.")
        kb = types.InlineKeyboardMarkup(row_width=1).add(
            types.InlineKeyboardButton(f"🕹 QUAY NGAY (-{WHEEL_PRICE}đ)", callback_data="spin_wheel"),
            types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "spin_wheel":
        if balance < WHEEL_PRICE:
            bot.answer_callback_query(call.id, f"❌ Cần {WHEEL_PRICE}đ!", show_alert=True)
            return
        update_balance(chat_id, -WHEEL_PRICE, reason="Quay Wheel")
        chance = random.randint(1, 100)
        if chance <= 10: prize, msg = 1000, "🎉 NỔ HŨ! Trúng 1,000đ"
        elif chance <= 40: prize, msg = 200, "👍 Trúng 200đ"
        else: prize, msg = 0, "😭 Mất lượt!"
        
        if prize > 0: update_balance(chat_id, prize, reason="Trúng thưởng")
        kb = types.InlineKeyboardMarkup(row_width=1).add(
            types.InlineKeyboardButton("🔄 QUAY TIẾP", callback_data="spin_wheel"),
            types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")
        )
        bot.edit_message_text(f"🎰 <b>KẾT QUẢ</b>\n\n{msg}", chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "daily_checkin":
        today = str(date.today())
        if last_checkin == today:
            bot.answer_callback_query(call.id, "❌ Đã điểm danh!", show_alert=True)
        else:
            reward = 50 
            update_balance(chat_id, reward, reason="Điểm danh")
            db_query("UPDATE users SET last_checkin = ? WHERE chat_id = ?", (today, chat_id))
            bot.answer_callback_query(call.id, f"🎉 Nhận {reward}đ", show_alert=True)
            bot.send_message(chat_id, f"📅 Đã điểm danh: <b>+{reward} VNĐ</b>")

    elif call.data == "get_ref":
        ref_link = f"https://t.me/{bot.get_me().username}?start={chat_id}"
        text = (f"🔗 <b>LINK GIỚI THIỆU:</b>\n<code>{ref_link}</code>\n🎁 Nhận <b>5%</b> hoa hồng nạp!")
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")))

    elif call.data == "enter_giftcode":
        msg = bot.send_message(chat_id, "🎁 Nhập mã Giftcode (Gõ 'huy' để hủy):")
        bot.register_next_step_handler(msg, process_giftcode)

    elif call.data == "create_subbot":
        if balance < MIN_BALANCE_FOR_SUBBOT:
            bot.answer_callback_query(call.id, f"❌ Cần tối thiểu {MIN_BALANCE_FOR_SUBBOT:,}đ!", show_alert=True)
            return
        msg = bot.send_message(chat_id, "🤖 <b>TẠO BOT ĐẠI LÝ</b>\nGửi API Token bot con của bạn (Hoặc gõ <code>huy</code> để hủy):", parse_mode='HTML')
        bot.register_next_step_handler(msg, create_subbot_process)

    # ================= ADMIN PANEL QUYỀN LỰC =================
    elif call.data == "admin_panel" and chat_id == ADMIN_ID:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
            types.InlineKeyboardButton("🎁 Tạo Giftcode", callback_data="adm_giftcode")
        )
        kb.add(
            types.InlineKeyboardButton("🔧 Bật/Tắt Bảo trì", callback_data="adm_maintenance"),
            types.InlineKeyboardButton("📊 Báo cáo", callback_data="adm_stats")
        )
        kb.add(
            types.InlineKeyboardButton("🔍 User / 🚫 Ban", callback_data="adm_checkuser"),
            types.InlineKeyboardButton("💸 Duyệt Rút Tiền", callback_data="adm_withdrawals")
        )
        kb.add(
            types.InlineKeyboardButton("💾 Backup Data", callback_data="adm_backup"),
            types.InlineKeyboardButton("🔙 Thoát Panel", callback_data="back_home")
        )
        bot.edit_message_text("🛠 <b>TRUNG TÂM KIỂM SOÁT ADMIN</b>", chat_id, call.message.message_id, reply_markup=kb)

    elif call.data == "adm_maintenance" and chat_id == ADMIN_ID:
        MAINTENANCE_MODE = not MAINTENANCE_MODE # Do đã có global ở trên cùng hàm
        bot.answer_callback_query(call.id, f"Bảo trì: {'BẬT 🔴' if MAINTENANCE_MODE else 'TẮT 🟢'}", show_alert=True)

    elif call.data == "adm_stats" and chat_id == ADMIN_ID:
        u_count = db_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
        b_count = db_query("SELECT COUNT(*) FROM sub_bots", fetch=True)[0][0]
        total_dep = db_query("SELECT SUM(total_deposit) FROM users", fetch=True)[0][0] or 0
        text = f"📊 <b>BÁO CÁO</b>\n👥 User: {u_count}\n🤖 Bot con: {b_count}\n💵 Tổng nạp: <b>{total_dep:,}đ</b>"
        bot.answer_callback_query(call.id, text, show_alert=True)

    elif call.data == "adm_giftcode" and chat_id == ADMIN_ID:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        db_query("INSERT INTO giftcodes (code, value, max_uses) VALUES (?, ?, ?)", (code, 5000, 10))
        bot.send_message(chat_id, f"✅ Code: <code>{code}</code> (5k - 10 lượt)")

    elif call.data == "adm_broadcast" and chat_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "Nhập nội dung (gõ 'huy' để hủy):")
        bot.register_next_step_handler(msg, process_broadcast)
        
    elif call.data == "adm_checkuser" and chat_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "Kiểm tra User: Nhập ID\nBan User: Nhập 'ID 1'\nUnban: Nhập 'ID 0'")
        bot.register_next_step_handler(msg, admin_handle_user)
        
    elif call.data == "adm_withdrawals" and chat_id == ADMIN_ID:
        reqs = db_query("SELECT id, chat_id, amount, bank_info FROM withdraw_requests WHERE status='pending'", fetch=True)
        if not reqs:
            bot.answer_callback_query(call.id, "Không có yêu cầu rút tiền nào.", show_alert=True)
        else:
            text = "💸 <b>CÁC LỆNH RÚT ĐANG CHỜ CHUYỂN KHOẢN:</b>\n\n"
            for r in reqs:
                text += f"▪️ Lệnh #{r[0]} | ID: {r[1]} | Tiền: {r[2]}đ\nNH: {r[3]}\n\n"
            text += "<i>(Để duyệt lệnh rút, dùng tính năng trừ tiền thủ công của admin sau khi đã chuyển khoản cho khách)</i>"
            bot.send_message(chat_id, text)

    elif call.data == "adm_backup" and chat_id == ADMIN_ID:
        try:
            with open('j2proxy_system.db', 'rb') as doc:
                bot.send_document(chat_id, doc, caption="💾 Database Backup")
        except: bot.answer_callback_query(call.id, "Lỗi tải file!", show_alert=True)


# ================= HÀM XỬ LÝ NHẬP LIỆU =================
def process_withdrawal(message):
    chat_id = message.chat.id
    if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy thao tác.")
    
    balance = get_user(chat_id)[0]
    if balance < 100000: return bot.send_message(chat_id, "Lỗi: Số dư tụt dưới 100k.")
    
    db_query("INSERT INTO withdraw_requests (chat_id, amount, bank_info) VALUES (?, ?, ?)", (chat_id, balance, message.text))
    # Reset balance sau khi tạo lệnh rút
    update_balance(chat_id, -balance, reason="Tạo lệnh rút tiền")
    bot.send_message(chat_id, "✅ Đã gửi lệnh rút tiền cho Admin xử lý. Vui lòng chờ 24h.")
    try: bot.send_message(ADMIN_ID, f"🔔 <b>CÓ LỆNH RÚT TIỀN MỚI</b>\nTừ ID: {chat_id}\nSố tiền: {balance}đ")
    except: pass

def process_giftcode(message):
    chat_id = message.chat.id
    if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy thao tác.")
    
    code = message.text.strip().upper()
    used = db_query("SELECT * FROM history_codes WHERE chat_id=? AND code=?", (chat_id, code), True)
    if used: return bot.send_message(chat_id, "❌ Mã này đã xài rồi!")
        
    gift = db_query("SELECT value, max_uses, used_count FROM giftcodes WHERE code=?", (code,), True)
    if gift:
        val, max_u, used_c = gift[0]
        if used_c >= max_u: bot.send_message(chat_id, "❌ Code đã hết lượt.")
        else:
            db_query("UPDATE giftcodes SET used_count = used_count + 1 WHERE code=?", (code,))
            db_query("INSERT INTO history_codes (chat_id, code) VALUES (?, ?)", (chat_id, code))
            update_balance(chat_id, val, reason=f"Nạp Code {code}")
            bot.send_message(chat_id, f"🔥 Lụm được <b>{val:,} VNĐ</b>")
    else: bot.send_message(chat_id, "❌ Code sai!")

def process_broadcast(message):
    if message.text.lower() == 'huy': return bot.send_message(ADMIN_ID, "Đã hủy.")
    users = db_query("SELECT chat_id FROM users", fetch=True)
    success = 0
    for u in users:
        try: 
            bot.send_message(u[0], f"📣 <b>THÔNG BÁO HỆ THỐNG</b>\n────────────────\n{message.text}")
            success += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ Đã bắn tin đến {success} user.")

def admin_handle_user(message):
    if message.text.lower() == 'huy': return
    try:
        parts = message.text.split()
        uid = int(parts[0])
        if len(parts) == 1:
            b, t, v, ref, _, ban = get_user(uid)
            bot.send_message(ADMIN_ID, f"👤 <b>ID:</b> <code>{uid}</code>\n💵 Lúa: {b}\n📈 Nạp: {t}\n🎖 VIP: {v}\n🚫 Bị khóa: {'YES' if ban else 'NO'}")
        elif len(parts) == 2:
            status = int(parts[1])
            db_query("UPDATE users SET is_banned = ? WHERE chat_id = ?", (status, uid))
            bot.send_message(ADMIN_ID, f"✅ Cập nhật Ban = {status} cho ID {uid}")
    except: bot.send_message(ADMIN_ID, "❌ Lỗi cú pháp.")

# ================= HỆ THỐNG SUB-BOT =================
def create_subbot_process(message):
    chat_id = message.chat.id
    token = message.text.strip()
    
    if token.lower() == 'huy': 
        bot.send_message(chat_id, "Đã hủy tiến trình tạo bot.")
        return

    # Check lại số dư lần cuối để chắc chắn không bug
    current_balance = get_user(chat_id)[0]
    if current_balance < MIN_BALANCE_FOR_SUBBOT:
        bot.send_message(chat_id, "❌ Lỗi: Bạn vừa tiêu tiền nên không đủ 50k để tạo bot.")
        return

    try:
        # Cập nhật DB
        update_balance(chat_id, -MIN_BALANCE_FOR_SUBBOT, reason="Build Bot Affiliate")
        db_query("INSERT INTO sub_bots (owner_id, token) VALUES (?, ?)", (chat_id, token))
        bot.send_message(chat_id, "✅ <b>BOT LÊN SÓNG!</b>\nTiến trình bot của bạn đang khởi động...")
        
        # Mở luồng chạy độc lập
        threading.Thread(target=run_sub_bot, args=(token, chat_id), daemon=True).start()
    except sqlite3.IntegrityError:
        bot.send_message(chat_id, "❌ Token này đã được sử dụng rồi!")
        update_balance(chat_id, MIN_BALANCE_FOR_SUBBOT, reason="Hoàn tiền do token trùng")

def run_sub_bot(token, owner_id):
    try:
        sub_bot = telebot.TeleBot(token, parse_mode='HTML')
        
        @sub_bot.message_handler(commands=['start', 'mua'])
        def sub_handler(m):
            global MAINTENANCE_MODE # CHÚ Ý: ĐÃ SỬA LỖI Ở ĐÂY CŨNG VẬY
            
            if m.text == '/start':
                sub_bot.reply_to(m, "👋 <b>ĐẠI LÝ J2PROXY</b>\nGõ /mua để lên đơn siêu tốc.")
            elif m.text == '/mua':
                if MAINTENANCE_MODE:
                    sub_bot.reply_to(m, "Hệ thống tổng đang bảo trì!")
                    return
                buyer_id = m.chat.id
                balance = get_user(buyer_id)[0]
                price = 4000
                if balance < price:
                    sub_bot.reply_to(m, f"❌ Cần {price:,}đ. Hãy nạp qua @{bot.get_me().username}")
                    return
                
                sub_bot.reply_to(m, "⏳ Đang kết nối J2Proxy...")
                proxy = call_j2proxy_api("ipv4_shared")
                if proxy:
                    update_balance(buyer_id, -price, reason="Mua Proxy (Đại Lý)")
                    update_balance(owner_id, SUBBOT_COMMISSION, reason=f"Lãi đơn đại lý")
                    
                    sub_bot.send_message(buyer_id, f"✅ <b>CHỐT ĐƠN!</b>\n🔐 Proxy: <code>{proxy}</code>")
                    try: bot.send_message(owner_id, f"🤑 <b>TING TING!</b> Có khách mua hàng, cộng <b>+{SUBBOT_COMMISSION}đ</b>")
                    except: pass
                else:
                    sub_bot.reply_to(m, "⚠️ Lỗi API hoặc cháy hàng.")
                    
        # Dùng Infinity Polling thay cho polling thường để bot con không bị crash
        sub_bot.infinity_polling()
    except Exception as e:
        print(f"Lỗi khởi động Subbot {token[-5:]}: {e}")

# ================= LAUNCH SEQUENCE =================
if __name__ == '__main__':
    print("Khởi động Sub-bot engine...")
    bots = db_query("SELECT token, owner_id FROM sub_bots", fetch=True)
    for b in bots:
        threading.Thread(target=run_sub_bot, args=(b[0], b[1]), daemon=True).start()
        
    print("Khởi động Main Bot engine...")
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    
    print("🚀 J2PROXY ENTERPRISE READY 🚀")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
