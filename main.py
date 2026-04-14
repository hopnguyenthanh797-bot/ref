import telebot
from telebot import types
import sqlite3
import requests
import threading
import random
import string
import os
import time
import traceback
from datetime import datetime, date
from flask import Flask, request, jsonify

# ================= CẤU HÌNH HỆ THỐNG =================
API_TOKEN = '8774975242:AAGWZdhXiinSQPC-1b12MIBAsMZONEjVvts'
ADMIN_ID = 7816353760
SUPPORT_LINK = 'https://t.me/nth_dev'

J2PROXY_API_TOKEN = 'j2proxy3643_eb73d0215ab40bbd9a74b7998e86bff3891aa6ec882ae441631b34761971d540'
J2PROXY_MERCHANT_ID = '2e773742-dc78-4755-bd99-a9f38e9f2c0f'

MIN_BALANCE_FOR_SUBBOT = 50000 
SUBBOT_COMMISSION = 200 
WHEEL_PRICE = 500 

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
app = Flask(__name__)

# Quản lý trạng thái hệ thống
SYS_CONFIG = {'maintenance': False}

# ================= KẾT NỐI DB AN TOÀN (ANTI-LOCK) =================
db_lock = threading.Lock()

def db_query(query, params=(), fetch=False):
    with db_lock:
        conn = sqlite3.connect('j2proxy_v4.db', check_same_thread=False, timeout=20)
        cursor = conn.cursor()
        cursor.execute(query, params)
        data = cursor.fetchall() if fetch else None
        conn.commit()
        conn.close()
        return data

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, 
        total_deposit INTEGER DEFAULT 0, vip_level INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT 0, last_checkin DATE, is_banned INTEGER DEFAULT 0
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS sub_bots (
        owner_id INTEGER, token TEXT UNIQUE, status INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS giftcodes (
        code TEXT PRIMARY KEY, value INTEGER, max_uses INTEGER, used_count INTEGER DEFAULT 0
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS history_codes (
        chat_id INTEGER, code TEXT
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, amount INTEGER, 
        reason TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, amount INTEGER, 
        bank_info TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

init_db()

# ================= HÀM TIỆN ÍCH CORE =================
def get_user(chat_id, username="Unknown"):
    res = db_query("SELECT balance, total_deposit, vip_level, referrer_id, last_checkin, is_banned FROM users WHERE chat_id=?", (chat_id,), True)
    if not res:
        db_query("INSERT INTO users (chat_id, username, balance) VALUES (?, ?, 0)", (chat_id, username))
        return (0, 0, 0, 0, None, 0)
    return res[0]

def log_tx(chat_id, amount, reason):
    db_query("INSERT INTO transactions (chat_id, amount, reason) VALUES (?, ?, ?)", (chat_id, amount, reason))

def update_balance(chat_id, amount, is_deposit=False, reason="Giao dịch"):
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
    log_tx(chat_id, amount, reason)

def get_vip_label(level):
    return {0: "🥉 Member", 1: "🥈 VIP 1", 2: "🥇 VIP 2", 3: "👑 DIAMOND"}.get(level, "🥉 Member")

# ================= KẾT NỐI API J2PROXY =================
def call_j2proxy_api(proxy_type="ipv4_shared"):
    url = "https://j2proxy.vn/api/proxy/buy" 
    headers = {
        "Authorization": f"Bearer {J2PROXY_API_TOKEN}",
        "x-merchant-id": J2PROXY_MERCHANT_ID,
        "Content-Type": "application/json"
    }
    payload = {"type": proxy_type, "days": 1}
    try:
        # Mở khóa dòng dưới nếu tài khoản J2Proxy đã có tiền để mua thật
        # response = requests.post(url, headers=headers, json=payload, timeout=15).json()
        # if response.get('status') == 'success': return response.get('data').get('proxy')
        # return None
        
        # Fake API để test giao diện
        time.sleep(0.5) # Giả lập độ trễ mạng
        return f"{random.randint(100,255)}.{random.randint(1,255)}.{random.randint(1,255)}.1:{random.randint(1000,9999)}:user:pass"
    except requests.exceptions.RequestException as e:
        print(f"Lỗi API: {e}")
        return None

# ================= FLASK WEBHOOK (TỐI ƯU RENDER) =================
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "running", "timestamp": str(datetime.now())})

@app.route('/sepay-webhook', methods=['POST'])
def sepay_webhook():
    try:
        data = request.json
        content = data.get('content', '').upper()
        amount = int(data.get('transferAmount', 0))
        if "NAP" in content:
            user_id = int(''.join(filter(str.isdigit, content)))
            update_balance(user_id, amount, is_deposit=True, reason="Nạp Auto Bank (SePay)")
            
            _, _, _, ref_id, _, _ = get_user(user_id)
            if ref_id != 0:
                ref_bonus = int(amount * 0.05)
                update_balance(ref_id, ref_bonus, reason=f"Hoa hồng REF từ ID {user_id}")
                try: bot.send_message(ref_id, f"💸 <b>HOA HỒNG AFFILIATE</b>\nCấp dưới nạp {amount:,}đ. Bạn nhận được <b>+{ref_bonus:,}đ</b>")
                except: pass
            try: bot.send_message(user_id, f"✅ <b>NẠP TIỀN THÀNH CÔNG!</b>\nSố tiền: <b>+{amount:,} VNĐ</b>")
            except: pass
    except Exception as e:
        print(f"Lỗi Webhook: {e}")
    return jsonify({"success": True})

# ================= GIAO DIỆN CHÍNH (ENTERPRISE UI) =================
def main_menu(chat_id):
    balance, total_dep, vip, _, _, _ = get_user(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    # Block 1: Dịch vụ chính
    kb.add(
        types.InlineKeyboardButton("🛒 MUA J2PROXY", callback_data="buy_proxy"),
        types.InlineKeyboardButton("💳 NẠP TIỀN AUTO", callback_data="deposit")
    )
    # Block 2: Quản lý & Tiện ích
    kb.add(
        types.InlineKeyboardButton("👤 HỒ SƠ", callback_data="profile"),
        types.InlineKeyboardButton("💸 CHUYỂN TIỀN", callback_data="transfer_money")
    )
    kb.add(
        types.InlineKeyboardButton("🤖 BOT ĐẠI LÝ", callback_data="create_subbot"),
        types.InlineKeyboardButton("🔗 TUYỂN REF", callback_data="get_ref")
    )
    # Block 3: Minigame & Khác
    kb.add(
        types.InlineKeyboardButton("🎰 VÒNG QUAY", callback_data="lucky_wheel"),
        types.InlineKeyboardButton("🎁 GIFTCODE", callback_data="enter_giftcode")
    )
    kb.add(
        types.InlineKeyboardButton("🏆 ĐUA TOP", callback_data="top_spenders"),
        types.InlineKeyboardButton("📅 ĐIỂM DANH", callback_data="daily_checkin")
    )
    kb.add(
        types.InlineKeyboardButton("🧾 LỊCH SỬ GIAO DỊCH", callback_data="tx_history"),
        types.InlineKeyboardButton("🎧 HỖ TRỢ", url=SUPPORT_LINK)
    )
    
    if chat_id == ADMIN_ID:
        kb.row(types.InlineKeyboardButton("⚙️ CONTROL PANEL (ADMIN) ⚙️", callback_data="admin_panel"))
        
    status = "🔴 BẢO TRÌ" if SYS_CONFIG['maintenance'] else "🟢 HOẠT ĐỘNG"
    text = (
        "<b>💎 HỆ THỐNG PHÂN PHỐI PROXY CAO CẤP 💎</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Mã khách hàng:</b> <code>{chat_id}</code>\n"
        f"💵 <b>Số dư khả dụng:</b> <b>{balance:,} VNĐ</b>\n"
        f"🎖 <b>Hạng thành viên:</b> <b>{get_vip_label(vip)}</b>\n"
        f"🌐 <b>Tình trạng API:</b> {status}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Vui lòng chọn dịch vụ bạn cần sử dụng bên dưới:</i>"
    )
    return text, kb

@bot.message_handler(commands=['start'])
def start(message):
    try:
        chat_id = message.chat.id
        username = message.from_user.username
        
        res = db_query("SELECT is_banned FROM users WHERE chat_id=?", (chat_id,), True)
        if res and res[0][0] == 1:
            return bot.send_message(chat_id, "🚫 <b>TÀI KHOẢN BỊ KHÓA</b>\nBạn đã bị cấm khỏi hệ thống.")

        ref_id = 0
        if len(message.text.split()) > 1:
            try: ref_id = int(message.text.split()[1])
            except: pass
            
        if not res:
            db_query("INSERT INTO users (chat_id, username, balance, referrer_id) VALUES (?, ?, 0, ?)", (chat_id, username, ref_id))
            if ref_id != 0 and ref_id != chat_id:
                try: bot.send_message(ref_id, f"🎉 <b>THÔNG BÁO:</b> Có người dùng mới vừa đăng ký qua link của bạn!")
                except: pass
                
        text, kb = main_menu(chat_id)
        bot.send_message(chat_id, text, reply_markup=kb)
    except Exception as e:
        print(f"Lỗi lệnh /start: {e}")

# ================= XỬ LÝ CALLBACK (CHỐNG TREO 100%) =================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    try:
        chat_id = call.message.chat.id
        balance, total_dep, vip, _, last_checkin, is_banned = get_user(chat_id)
        
        if is_banned:
            return bot.answer_callback_query(call.id, "🚫 TÀI KHOẢN ĐÃ BỊ KHÓA!", show_alert=True)
            
        if call.data == "back_home":
            text, kb = main_menu(chat_id)
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        # ---------------- CÁ NHÂN & TIỆN ÍCH ----------------
        elif call.data == "profile":
            text = (f"👤 <b>HỒ SƠ CÁ NHÂN</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 Mã ID: <code>{chat_id}</code>\n"
                    f"💵 Số dư: <b>{balance:,} VNĐ</b>\n"
                    f"📈 Tổng nạp: <b>{total_dep:,} VNĐ</b>\n"
                    f"👑 Cấp bậc: {get_vip_label(vip)}\n"
                    "<i>(Nạp đạt mốc 200k, 1M, 5M để nâng cấp VIP giảm giá)</i>")
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton("💸 YÊU CẦU RÚT TIỀN (ĐẠI LÝ)", callback_data="withdraw_fund"),
                types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home")
            )
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "transfer_money":
            msg = bot.send_message(chat_id, "💸 <b>CHUYỂN TIỀN NỘI BỘ</b>\nCú pháp: <code>[ID_Người_Nhận] [Số_Tiền]</code>\nVí dụ: <code>12345678 50000</code>\n\n<i>(Hoặc gõ 'huy' để hủy)</i>")
            bot.register_next_step_handler(msg, process_transfer)

        elif call.data == "withdraw_fund":
            if balance < 100000:
                bot.answer_callback_query(call.id, "❌ Số dư tối thiểu để rút là 100,000đ!", show_alert=True)
                return
            msg = bot.send_message(chat_id, "🏦 <b>RÚT TIỀN</b>\nNhập: Tên Ngân Hàng - STK - Chủ TK\n<i>(Gõ 'huy' để hủy)</i>")
            bot.register_next_step_handler(msg, process_withdrawal)

        elif call.data == "tx_history":
            history = db_query("SELECT amount, reason, created_at FROM transactions WHERE chat_id=? ORDER BY id DESC LIMIT 6", (chat_id,), True)
            text = "🧾 <b>LỊCH SỬ GIAO DỊCH (6 Gần Nhất)</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            if not history: text += "<i>Chưa có giao dịch nào.</i>"
            for tx in history or []:
                amt_str = f"+{tx[0]:,}" if tx[0] > 0 else f"{tx[0]:,}"
                icon = "🟢" if tx[0] > 0 else "🔴"
                text += f"{icon} <code>{tx[2][:16]}</code>\n💰 {amt_str}đ | <i>{tx[1]}</i>\n\n"
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home"))
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        # ---------------- NẠP & MUA PROXY ----------------
        elif call.data == "deposit":
            text = (f"💳 <b>CỔNG THANH TOÁN TỰ ĐỘNG</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏦 Ngân hàng: <b>MSB (Hàng Hải)</b>\n"
                    f"🔢 STK: <code>123456789</code>\n"
                    f"👤 Chủ TK: <b>NGUYEN VAN A</b>\n\n"
                    f"⚠️ <b>NỘI DUNG CHUYỂN KHOẢN:</b>\n👉 <code>NAP {chat_id}</code> 👈\n\n"
                    f"<i>Hệ thống tự động cộng tiền trong 5-10 giây. Hãy nạp đúng nội dung.</i>")
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home"))
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "buy_proxy":
            if SYS_CONFIG['maintenance']:
                return bot.answer_callback_query(call.id, "🛠 Hệ thống đang bảo trì, thử lại sau!", show_alert=True)
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton("🌐 IPv4 Share VN (4,000đ/ngày)", callback_data="order_j2_share"),
                types.InlineKeyboardButton("🚀 IPv4 Private VN (10,000đ/ngày)", callback_data="order_j2_private"),
                types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home")
            )
            bot.edit_message_text("🛒 <b>CỬA HÀNG J2PROXY</b>\nLựa chọn dịch vụ phù hợp với nhu cầu:", chat_id, call.message.message_id, reply_markup=kb)

        elif call.data.startswith("order_j2_"):
            ptype = call.data.split("_")[2]
            base_price = 4000 if ptype == "share" else 10000
            api_type = "ipv4_shared" if ptype == "share" else "ipv4_private"
            
            # Tính toán VIP
            price = base_price
            if vip == 1: price = int(price * 0.95)
            elif vip == 2: price = int(price * 0.9)
            elif vip == 3: price = int(price * 0.8)
            
            if balance < price:
                return bot.answer_callback_query(call.id, f"❌ Không đủ số dư! Yêu cầu: {price:,}đ", show_alert=True)
                
            bot.edit_message_text("⏳ <i>Đang khởi tạo Proxy... Vui lòng chờ...</i>", chat_id, call.message.message_id)
            proxy = call_j2proxy_api(api_type)
            
            if proxy:
                update_balance(chat_id, -price, reason=f"Mua Proxy {ptype.upper()}")
                receipt = (
                    "✅ <b>GIAO DỊCH THÀNH CÔNG</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔖 Đơn hàng: <code>#J2_{random.randint(10000, 99999)}</code>\n"
                    f"📦 Dịch vụ: <b>IPv4 {ptype.capitalize()}</b>\n"
                    f"💵 Thanh toán: <b>{price:,}đ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔐 <b>THÔNG TIN PROXY:</b>\n<code>{proxy}</code>\n\n"
                    f"<i>💰 Số dư còn lại: {balance - price:,} VNĐ</i>"
                )
                kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home"))
                bot.edit_message_text(receipt, chat_id, call.message.message_id, reply_markup=kb)
            else:
                bot.edit_message_text("⚠️ <b>LỖI API / HẾT HÀNG</b>\nHệ thống nguồn tạm thời không phản hồi. Vui lòng thử lại sau ít phút.", chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home")))

        # ---------------- MINIGAME & KHÁC ----------------
        elif call.data == "lucky_wheel":
            text = (f"🎰 <b>VÒNG QUAY NHÂN PHẨM</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💵 Vé quay: <b>{WHEEL_PRICE}đ/lượt</b>\n\n"
                    f"🎁 <b>Giải thưởng:</b>\n"
                    f"▪️ Trúng 1,000 VNĐ (Tỷ lệ 10%)\n▪️ Trúng 200 VNĐ (Tỷ lệ 30%)\n▪️ Xịt (Tỷ lệ 60%)")
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton(f"🕹 QUAY NGAY (-{WHEEL_PRICE}đ)", callback_data="spin_wheel"),
                types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home")
            )
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "spin_wheel":
            if balance < WHEEL_PRICE:
                return bot.answer_callback_query(call.id, f"❌ Bạn không đủ {WHEEL_PRICE}đ để chơi!", show_alert=True)
            
            update_balance(chat_id, -WHEEL_PRICE, reason="Chơi Vòng Quay")
            chance = random.randint(1, 100)
            if chance <= 10: prize, msg = 1000, "🎉 <b>BÙM! NỔ HŨ!</b>\nBạn vừa quay trúng <b>1,000 VNĐ</b>!"
            elif chance <= 40: prize, msg = 200, "👍 <b>HAY ĐÓ!</b>\nBạn quay trúng <b>200 VNĐ</b>."
            else: prize, msg = 0, "😭 <b>ĐEN THÔI ĐỎ QUÊN ĐI!</b>\nBạn quay vào ô mất lượt."
            
            if prize > 0: update_balance(chat_id, prize, reason="Trúng thưởng Vòng Quay")
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton("🔄 QUAY TIẾP LẦN NỮA", callback_data="spin_wheel"),
                types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home")
            )
            code_quay = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            bot.edit_message_text(f"🎰 <b>KẾT QUẢ VÒNG QUAY</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{msg}\n\n<i>Mã quay: #{code_quay}</i>", chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "daily_checkin":
            today = str(date.today())
            if last_checkin == today:
                bot.answer_callback_query(call.id, "❌ Bạn đã điểm danh hôm nay rồi!", show_alert=True)
            else:
                update_balance(chat_id, 50, reason="Điểm danh hàng ngày")
                db_query("UPDATE users SET last_checkin = ? WHERE chat_id = ?", (today, chat_id))
                bot.answer_callback_query(call.id, f"🎉 Nhận thành công +50đ", show_alert=True)
                bot.send_message(chat_id, f"📅 <b>ĐIỂM DANH</b>\nBạn nhận được <b>+50 VNĐ</b> vào tài khoản.")

        elif call.data == "get_ref":
            ref_link = f"https://t.me/{bot.get_me().username}?start={chat_id}"
            text = (f"🔗 <b>CHƯƠNG TRÌNH ĐỐI TÁC</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Gửi link này cho bạn bè:\n<code>{ref_link}</code>\n\n"
                    f"🎁 <b>Phần thưởng:</b>\nNhận ngay <b>5%</b> tiền hoa hồng mỗi khi bạn bè của bạn nạp tiền. Nạp càng nhiều, nhận càng sướng!")
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 TRỞ VỀ", callback_data="back_home")))

        elif call.data == "enter_giftcode":
            msg = bot.send_message(chat_id, "🎁 Nhập mã Code của bạn (Gõ 'huy' để hủy):")
            bot.register_next_step_handler(msg, process_giftcode)

        elif call.data == "create_subbot":
            if balance < MIN_BALANCE_FOR_SUBBOT:
                return bot.answer_callback_query(call.id, f"❌ Cần tối thiểu {MIN_BALANCE_FOR_SUBBOT:,}đ để tạo xưởng bot!", show_alert=True)
            text = ("🤖 <b>TẠO BOT ĐẠI LÝ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Khi có người mua proxy qua bot của bạn, bạn sẽ nhận hoa hồng 200đ/đơn.\n"
                    "👉 Gửi <b>API Token</b> bot con lấy từ @BotFather (Gõ 'huy' để hủy):")
            msg = bot.send_message(chat_id, text)
            bot.register_next_step_handler(msg, create_subbot_process)

        # ---------------- ADMIN PANEL (PRO) ----------------
        elif call.data == "admin_panel" and chat_id == ADMIN_ID:
            kb = types.InlineKeyboardMarkup(row_width=2).add(
                types.InlineKeyboardButton("📢 Gửi Broadcast", callback_data="adm_bc"),
                types.InlineKeyboardButton("🎁 Gen Giftcode", callback_data="adm_gc"),
                types.InlineKeyboardButton("🔧 Bật/Tắt Bảo Trì", callback_data="adm_mt"),
                types.InlineKeyboardButton("📊 Báo cáo HT", callback_data="adm_st"),
                types.InlineKeyboardButton("🔍 Quản lý User", callback_data="adm_us"),
                types.InlineKeyboardButton("💸 Duyệt Rút", callback_data="adm_wd"),
                types.InlineKeyboardButton("🔙 Thoát Panel", callback_data="back_home")
            )
            bot.edit_message_text("🛠 <b>TRUNG TÂM KIỂM SOÁT ADMIN</b>\nBạn đang nắm quyền cao nhất.", chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "adm_mt" and chat_id == ADMIN_ID:
            SYS_CONFIG['maintenance'] = not SYS_CONFIG['maintenance']
            bot.answer_callback_query(call.id, f"Trạng thái Bảo trì: {'BẬT 🔴' if SYS_CONFIG['maintenance'] else 'TẮT 🟢'}", show_alert=True)

        elif call.data == "adm_st" and chat_id == ADMIN_ID:
            u = db_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
            b = db_query("SELECT COUNT(*) FROM sub_bots", fetch=True)[0][0]
            t = db_query("SELECT SUM(total_deposit) FROM users", fetch=True)[0][0] or 0
            bot.answer_callback_query(call.id, f"👥 Tổng User: {u}\n🤖 Bot vệ tinh: {b}\n💵 Dòng tiền nạp: {t:,}đ", show_alert=True)

        elif call.data == "adm_gc" and chat_id == ADMIN_ID:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            db_query("INSERT INTO giftcodes (code, value, max_uses) VALUES (?, ?, ?)", (code, 5000, 10))
            bot.send_message(chat_id, f"✅ Đã tạo Code mới:\n<code>{code}</code>\nGiá trị: 5k - Lượt: 10")

        elif call.data == "adm_bc" and chat_id == ADMIN_ID:
            msg = bot.send_message(chat_id, "Nhập nội dung Broadcast (Gõ 'huy' để hủy):")
            bot.register_next_step_handler(msg, process_broadcast)
            
        elif call.data == "adm_us" and chat_id == ADMIN_ID:
            msg = bot.send_message(chat_id, "🛠 <b>CÚ PHÁP QUẢN LÝ USER:</b>\n"
                                           "- Check thông tin: <code>[ID]</code> (VD: 12345)\n"
                                           "- Cộng/Trừ tiền: <code>[ID] [Số_Tiền]</code> (VD: 123 50000 hoặc 123 -50000)\n"
                                           "- Ban User: <code>[ID] ban</code>\n"
                                           "- Unban User: <code>[ID] unban</code>\n"
                                           "<i>Gõ 'huy' để hủy lệnh.</i>")
            bot.register_next_step_handler(msg, admin_handle_user)
            
        elif call.data == "adm_wd" and chat_id == ADMIN_ID:
            reqs = db_query("SELECT id, chat_id, amount, bank_info FROM withdraw_requests WHERE status='pending'", fetch=True)
            if not reqs:
                bot.answer_callback_query(call.id, "Không có yêu cầu rút tiền.", show_alert=True)
            else:
                text = "💸 <b>CÁC LỆNH ĐANG CHỜ CHUYỂN KHOẢN:</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                for r in reqs: text += f"▪️ ID người nhận: <code>{r[1]}</code>\n💰 Số tiền: <b>{r[2]:,}đ</b>\n🏦 Thông tin: <code>{r[3]}</code>\n\n"
                bot.send_message(chat_id, text)

    except Exception as e:
        print(f"Lỗi Callback: {traceback.format_exc()}")
        bot.answer_callback_query(call.id, "❌ Hệ thống bận, vui lòng thử lại!", show_alert=True)
    finally:
        try: bot.answer_callback_query(call.id) # BẮT BUỘC PHẢI CÓ ĐỂ CHỐNG TREO NÚT
        except: pass

# ================= CÁC HÀM XỬ LÝ NHẬP =================
def process_transfer(message):
    try:
        chat_id = message.chat.id
        if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy chuyển tiền.")
        
        parts = message.text.split()
        if len(parts) != 2: return bot.send_message(chat_id, "❌ Cú pháp sai. Hãy làm lại.")
        
        target_id, amount = int(parts[0]), int(parts[1])
        if amount <= 0: return bot.send_message(chat_id, "❌ Số tiền phải lớn hơn 0.")
        
        balance = get_user(chat_id)[0]
        if balance < amount: return bot.send_message(chat_id, "❌ Số dư của bạn không đủ.")
        
        target_user = db_query("SELECT chat_id FROM users WHERE chat_id=?", (target_id,), True)
        if not target_user: return bot.send_message(chat_id, "❌ ID người nhận không tồn tại trong hệ thống.")
        
        # Trừ người gửi, Cộng người nhận
        update_balance(chat_id, -amount, reason=f"Chuyển tiền cho {target_id}")
        update_balance(target_id, amount, reason=f"Nhận tiền từ {chat_id}")
        
        bot.send_message(chat_id, f"✅ Đã chuyển thành công <b>{amount:,}đ</b> tới ID <code>{target_id}</code>")
        try: bot.send_message(target_id, f"💸 <b>TING TING!</b>\nBạn vừa nhận được <b>{amount:,}đ</b> từ ID <code>{chat_id}</code>")
        except: pass
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Lỗi: Cú pháp không hợp lệ.")

def process_withdrawal(message):
    try:
        chat_id = message.chat.id
        if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy thao tác.")
        
        balance = get_user(chat_id)[0]
        if balance < 100000: return bot.send_message(chat_id, "❌ Lỗi: Số dư của bạn đã tụt xuống dưới 100k.")
        
        db_query("INSERT INTO withdraw_requests (chat_id, amount, bank_info) VALUES (?, ?, ?)", (chat_id, balance, message.text))
        update_balance(chat_id, -balance, reason="Tạo lệnh rút tiền")
        bot.send_message(chat_id, "✅ Đã gửi lệnh rút tiền cho Admin. Vui lòng chờ giải quyết.")
        try: bot.send_message(ADMIN_ID, f"🔔 <b>CÓ LỆNH RÚT TIỀN</b>\nID: {chat_id}\nTiền: {balance:,}đ\nTT: {message.text}")
        except: pass
    except Exception as e: print(e)

def process_giftcode(message):
    try:
        chat_id = message.chat.id
        if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy thao tác.")
        
        code = message.text.strip().upper()
        used = db_query("SELECT * FROM history_codes WHERE chat_id=? AND code=?", (chat_id, code), True)
        if used: return bot.send_message(chat_id, "❌ Mã này bạn đã sử dụng rồi!")
            
        gift = db_query("SELECT value, max_uses, used_count FROM giftcodes WHERE code=?", (code,), True)
        if gift and gift[0][2] < gift[0][1]:
            db_query("UPDATE giftcodes SET used_count = used_count + 1 WHERE code=?", (code,))
            db_query("INSERT INTO history_codes (chat_id, code) VALUES (?, ?)", (chat_id, code))
            update_balance(chat_id, gift[0][0], reason=f"Nạp Code {code}")
            bot.send_message(chat_id, f"🔥 Lụm thành công <b>{gift[0][0]:,} VNĐ</b>")
        else: bot.send_message(chat_id, "❌ Mã Code không tồn tại hoặc đã hết lượt!")
    except Exception as e: print(e)

def process_broadcast(message):
    try:
        if message.text.lower() == 'huy': return bot.send_message(ADMIN_ID, "Đã hủy Broadcast.")
        users = db_query("SELECT chat_id FROM users", fetch=True)
        count = 0
        for u in users:
            try: 
                bot.send_message(u[0], f"📣 <b>THÔNG BÁO TỪ HỆ THỐNG</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{message.text}")
                count += 1
            except: pass
        bot.send_message(ADMIN_ID, f"✅ Đã gửi thành công đến {count} người dùng.")
    except Exception as e: print(e)

def admin_handle_user(message):
    try:
        if message.text.lower() == 'huy': return bot.send_message(ADMIN_ID, "Đã hủy thao tác admin.")
        parts = message.text.split()
        uid = int(parts[0])
        
        if len(parts) == 1: # Check info
            b, t, v, _, _, ban = get_user(uid)
            bot.send_message(ADMIN_ID, f"👤 <b>INFO ID:</b> <code>{uid}</code>\n💵 Lúa: {b:,}đ\n📈 Tổng nạp: {t:,}đ\n🚫 Bị khóa: {'CÓ' if ban else 'KHÔNG'}")
        elif len(parts) == 2: 
            if parts[1].lower() == 'ban':
                db_query("UPDATE users SET is_banned = 1 WHERE chat_id = ?", (uid,))
                bot.send_message(ADMIN_ID, f"✅ Đã KHÓA ID {uid}")
            elif parts[1].lower() == 'unban':
                db_query("UPDATE users SET is_banned = 0 WHERE chat_id = ?", (uid,))
                bot.send_message(ADMIN_ID, f"✅ Đã MỞ KHÓA ID {uid}")
            else: # Cộng trừ tiền thủ công
                amt = int(parts[1])
                update_balance(uid, amt, reason="Admin thay đổi số dư")
                bot.send_message(ADMIN_ID, f"✅ Đã {'cộng' if amt>0 else 'trừ'} {abs(amt):,}đ cho ID {uid}")
                try: bot.send_message(uid, f"🔔 Admin vừa biến động số dư của bạn: <b>{'+' if amt>0 else ''}{amt:,}đ</b>")
                except: pass
    except Exception as e: bot.send_message(ADMIN_ID, "❌ Sai cú pháp.")

# ================= HỆ THỐNG BOT VỆ TINH (SUB-BOT) =================
def create_subbot_process(message):
    try:
        chat_id = message.chat.id
        token = message.text.strip()
        if token.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy quá trình tạo bot.")

        if get_user(chat_id)[0] < MIN_BALANCE_FOR_SUBBOT:
            return bot.send_message(chat_id, "❌ Tài khoản của bạn không đủ tiền.")

        update_balance(chat_id, -MIN_BALANCE_FOR_SUBBOT, reason="Phí tạo Bot Đại Lý")
        db_query("INSERT INTO sub_bots (owner_id, token) VALUES (?, ?)", (chat_id, token))
        bot.send_message(chat_id, "✅ <b>BOT CỦA BẠN ĐÃ KHỞI CHẠY THÀNH CÔNG!</b>\nHãy thử vào bot của bạn ấn /start nhé.")
        
        threading.Thread(target=run_sub_bot, args=(token, chat_id), daemon=True).start()
    except sqlite3.IntegrityError:
        bot.send_message(chat_id, "❌ Token này đã được đăng ký trên hệ thống!")
        update_balance(chat_id, MIN_BALANCE_FOR_SUBBOT, reason="Hoàn tiền do lỗi tạo Bot")
    except Exception as e: print(e)

def run_sub_bot(token, owner_id):
    try:
        sub_bot = telebot.TeleBot(token, parse_mode='HTML', threaded=False)
        
        @sub_bot.message_handler(commands=['start', 'mua'])
        def sub_handler(m):
            try:
                if m.text == '/start':
                    sub_bot.reply_to(m, "👋 <b>ĐẠI LÝ J2PROXY ỦY QUYỀN</b>\nGõ /mua để đặt hàng ngay lập tức.")
                elif m.text == '/mua':
                    if SYS_CONFIG['maintenance']:
                        return sub_bot.reply_to(m, "Hệ thống tổng đang bảo trì. Vui lòng quay lại sau!")
                        
                    buyer_id = m.chat.id
                    if get_user(buyer_id)[0] < 4000:
                        return sub_bot.reply_to(m, f"❌ Số dư không đủ 4,000đ. Vui lòng nạp tiền qua @{bot.get_me().username}")
                    
                    sub_bot.reply_to(m, "⏳ Đang kết xuất API lấy Proxy...")
                    proxy = call_j2proxy_api("ipv4_shared")
                    
                    if proxy:
                        update_balance(buyer_id, -4000, reason="Mua Proxy (SubBot)")
                        update_balance(owner_id, SUBBOT_COMMISSION, reason="Lãi đại lý")
                        sub_bot.send_message(buyer_id, f"✅ <b>GIAO DỊCH THÀNH CÔNG</b>\n🔐 Proxy: <code>{proxy}</code>")
                        try: bot.send_message(owner_id, f"🤑 <b>TING TING!</b> Bạn vừa có hoa hồng bán thẻ: <b>+{SUBBOT_COMMISSION}đ</b>")
                        except: pass
                    else:
                        sub_bot.reply_to(m, "⚠️ Hệ thống nguồn đang nghẽn hoặc hết tài nguyên.")
            except Exception as e: print(f"Lỗi Subbot Logic: {e}")
                    
        print(f"[*] Subbot {token[-5:]} đang lắng nghe...")
        # Sử dụng polling tối ưu để không chiếm dụng quá nhiều RAM
        sub_bot.polling(none_stop=True, timeout=15, long_polling_timeout=5)
    except Exception as e:
        print(f"[!] Lỗi Crash Subbot {token[-5:]}: {e}")

# ================= QUÁ TRÌNH KHỞI ĐỘNG CHUẨN RENDER =================
if __name__ == '__main__':
    print("1. Đang kích hoạt mạng lưới Sub-bots...")
    bots = db_query("SELECT token, owner_id FROM sub_bots", fetch=True)
    for b in bots or []:
        threading.Thread(target=run_sub_bot, args=(b[0], b[1]), daemon=True).start()
        
    print("2. Đang khởi động BOT MAIN...")
    threading.Thread(target=bot.infinity_polling, kwargs={'timeout': 15, 'long_polling_timeout': 5}, daemon=True).start()
    
    print("🚀 TẤT CẢ ĐÃ SẴN SÀNG! ĐANG LẮNG NGHE PORT 🚀")
    # Để App.run ở luồng chính (Main Thread), Render sẽ lấy được PORT và không báo lỗi Deploy Failed
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
