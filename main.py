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

# Cấu hình Ngân hàng cho Auto Bank
BANK_ID = "MSB" # Mã ngân hàng, VD: MB, VCB, MSB, ACB...
BANK_ACCOUNT = "123456789"
BANK_NAME = "NGUYEN VAN A"

MIN_BALANCE_FOR_SUBBOT = 50000 
SUBBOT_COMMISSION = 200 
WHEEL_PRICE = 500 

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
app = Flask(__name__)

SYS_CONFIG = {'maintenance': False}
db_lock = threading.Lock()

# ================= DATABASE LOGIC =================
def db_query(query, params=(), fetch=False):
    with db_lock:
        conn = sqlite3.connect('j2proxy_v5.db', check_same_thread=False, timeout=20)
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
        owner_id INTEGER, token TEXT UNIQUE, status INTEGER DEFAULT 1
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

def get_user(chat_id, username="Unknown"):
    res = db_query("SELECT balance, total_deposit, vip_level, referrer_id, last_checkin, is_banned FROM users WHERE chat_id=?", (chat_id,), True)
    if not res:
        db_query("INSERT INTO users (chat_id, username, balance) VALUES (?, ?, 0)", (chat_id, username))
        return (0, 0, 0, 0, None, 0)
    return res[0]

def update_balance(chat_id, amount, is_deposit=False, reason="Giao dịch"):
    if is_deposit and amount > 0:
        db_query("UPDATE users SET balance = balance + ?, total_deposit = total_deposit + ? WHERE chat_id = ?", (amount, amount, chat_id))
        _, total_dep, _, _, _, _ = get_user(chat_id)
        new_vip = 3 if total_dep >= 5000000 else 2 if total_dep >= 1000000 else 1 if total_dep >= 200000 else 0
        db_query("UPDATE users SET vip_level = ? WHERE chat_id = ?", (new_vip, chat_id))
    else:
        db_query("UPDATE users SET balance = balance + ? WHERE chat_id = ?", (amount, chat_id))
    db_query("INSERT INTO transactions (chat_id, amount, reason) VALUES (?, ?, ?)", (chat_id, amount, reason))

def get_vip_label(level):
    return {0: "🥉 Member", 1: "🥈 VIP 1 (Giảm 5%)", 2: "🥇 VIP 2 (Giảm 10%)", 3: "👑 DIAMOND (Giảm 20%)"}.get(level, "🥉 Member")

# ================= API J2PROXY =================
def call_j2proxy_api(proxy_type="ipv4_shared"):
    url = "https://j2proxy.vn/api/proxy/buy" 
    headers = {"Authorization": f"Bearer {J2PROXY_API_TOKEN}", "x-merchant-id": J2PROXY_MERCHANT_ID, "Content-Type": "application/json"}
    payload = {"type": proxy_type, "days": 1}
    try:
        # response = requests.post(url, headers=headers, json=payload, timeout=15).json()
        # if response.get('status') == 'success': return response.get('data').get('proxy')
        # return None
        
        # Fake API 
        time.sleep(0.5) 
        return f"{random.randint(100,255)}.{random.randint(1,255)}.1.1:{random.randint(1000,9999)}:user:pass"
    except Exception as e:
        print(f"Lỗi API: {e}")
        return None

# ================= FLASK WEBHOOK (AUTO BANK) =================
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
            update_balance(user_id, amount, is_deposit=True, reason="Nạp Bank Auto")
            
            _, _, _, ref_id, _, _ = get_user(user_id)
            if ref_id != 0:
                ref_bonus = int(amount * 0.05)
                update_balance(ref_id, ref_bonus, reason=f"Hoa hồng REF ID {user_id}")
                try: bot.send_message(ref_id, f"💸 <b>HOA HỒNG AFFILIATE</b>\nCấp dưới nạp {amount:,}đ. Nhận: <b>+{ref_bonus:,}đ</b>")
                except: pass
            try: bot.send_message(user_id, f"✅ <b>NẠP TIỀN THÀNH CÔNG!</b>\nSố tiền: <b>+{amount:,} VNĐ</b>")
            except: pass
    except Exception as e:
        print(f"Lỗi Webhook: {e}")
    return jsonify({"success": True})

# ================= GIAO DIỆN CHÍNH (V5) =================
def main_menu(chat_id):
    balance, total_dep, vip, _, _, _ = get_user(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    kb.add(
        types.InlineKeyboardButton("🛒 CỬA HÀNG PROXY", callback_data="buy_proxy"),
        types.InlineKeyboardButton("💳 NẠP TIỀN / QR", callback_data="deposit")
    )
    kb.add(
        types.InlineKeyboardButton("👤 HỒ SƠ", callback_data="profile"),
        types.InlineKeyboardButton("💸 CHUYỂN TIỀN", callback_data="transfer_money")
    )
    kb.add(
        types.InlineKeyboardButton("🤖 TẠO BOT VỆ TINH", callback_data="create_subbot"),
        types.InlineKeyboardButton("🔗 MÃ GIỚI THIỆU", callback_data="get_ref")
    )
    kb.add(
        types.InlineKeyboardButton("🎁 NHẬP GIFTCODE", callback_data="enter_giftcode"),
        types.InlineKeyboardButton("📅 ĐIỂM DANH", callback_data="daily_checkin")
    )
    kb.add(
        types.InlineKeyboardButton("🎰 VÒNG QUAY MAY MẮN", callback_data="lucky_wheel")
    )
    kb.add(
        types.InlineKeyboardButton("🏆 BẢNG XẾP HẠNG", callback_data="top_spenders"),
        types.InlineKeyboardButton("🧾 LỊCH SỬ", callback_data="tx_history")
    )
    kb.add(
        types.InlineKeyboardButton("📖 HƯỚNG DẪN", callback_data="guide"),
        types.InlineKeyboardButton("🎧 CSKH 24/7", url=SUPPORT_LINK)
    )
    
    if chat_id == ADMIN_ID:
        kb.row(types.InlineKeyboardButton("⚡️ TRUNG TÂM KIỂM SOÁT (ADMIN) ⚡️", callback_data="admin_panel"))
        
    status = "🔴 BẢO TRÌ" if SYS_CONFIG['maintenance'] else "🟢 HOẠT ĐỘNG"
    text = (
        "<b>🛡 HỆ THỐNG PROXY TỰ ĐỘNG THÔNG MINH 🛡</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Tài khoản ID:</b> <code>{chat_id}</code>\n"
        f"💵 <b>Số dư hiện tại:</b> <b>{balance:,} VNĐ</b>\n"
        f"🎖 <b>Trạng thái:</b> <b>{get_vip_label(vip)}</b>\n"
        f"🌐 <b>Máy chủ:</b> {status}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Vui lòng chọn dịch vụ từ menu bên dưới:</i>"
    )
    return text, kb

@bot.message_handler(commands=['start'])
def start(message):
    try:
        chat_id = message.chat.id
        username = message.from_user.username
        
        res = db_query("SELECT is_banned FROM users WHERE chat_id=?", (chat_id,), True)
        if res and res[0][0] == 1:
            return bot.send_message(chat_id, "🚫 <b>TÀI KHOẢN BỊ KHÓA</b>\nVui lòng liên hệ Admin.")

        ref_id = 0
        if len(message.text.split()) > 1:
            try: ref_id = int(message.text.split()[1])
            except: pass
            
        if not res:
            db_query("INSERT INTO users (chat_id, username, balance, referrer_id) VALUES (?, ?, 0, ?)", (chat_id, username, ref_id))
            if ref_id != 0 and ref_id != chat_id:
                try: bot.send_message(ref_id, f"🎉 <b>TIN VUI:</b> Bạn có 1 ref mới đăng ký!")
                except: pass
                
        text, kb = main_menu(chat_id)
        bot.send_message(chat_id, text, reply_markup=kb)
    except Exception as e: print(e)

# ================= XỬ LÝ CALLBACK CHỐNG TREO =================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    try:
        chat_id = call.message.chat.id
        balance, total_dep, vip, _, last_checkin, is_banned = get_user(chat_id)
        
        if is_banned: return bot.answer_callback_query(call.id, "🚫 BỊ KHÓA!", show_alert=True)
            
        if call.data == "back_home":
            text, kb = main_menu(chat_id)
            # Dùng try except để tránh lỗi Message is not modified
            try: bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)
            except: pass

        elif call.data == "profile":
            text = (f"👤 <b>HỒ SƠ CÁ NHÂN</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 Mã ID: <code>{chat_id}</code>\n💵 Số dư: <b>{balance:,} VNĐ</b>\n"
                    f"📈 Tổng nạp: <b>{total_dep:,} VNĐ</b>\n👑 Cấp bậc: {get_vip_label(vip)}")
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton("💸 RÚT TIỀN HOA HỒNG", callback_data="withdraw_fund"),
                types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home")
            )
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "deposit":
            # TẠO ẢNH MÃ QR AUTO CHUYỂN KHOẢN (PRO FEATURE)
            qr_url = f"https://img.vietqr.io/image/{BANK_ID}-{BANK_ACCOUNT}-compact2.png?amount=0&addInfo=NAP%20{chat_id}&accountName={BANK_NAME.replace(' ', '%20')}"
            text = (f"💳 <b>NẠP TIỀN TỰ ĐỘNG</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏦 Ngân hàng: <b>{BANK_ID}</b>\n🔢 STK: <code>{BANK_ACCOUNT}</code>\n"
                    f"👤 Chủ TK: <b>{BANK_NAME}</b>\n\n"
                    f"⚠️ <b>NỘI DUNG CHUYỂN KHOẢN:</b>\n👉 <code>NAP {chat_id}</code> 👈\n\n"
                    f"<i>Hoặc quét mã QR bên trên. Hệ thống auto cộng tiền trong 5-10s.</i>")
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home"))
            bot.delete_message(chat_id, call.message.message_id) # Xóa tin nhắn cũ để gửi ảnh
            bot.send_photo(chat_id, photo=qr_url, caption=text, reply_markup=kb, parse_mode='HTML')

        elif call.data == "transfer_money":
            msg = bot.send_message(chat_id, "💸 <b>CHUYỂN TIỀN</b>\nGõ: <code>[ID_Người_Nhận] [Số_Tiền]</code>\nVD: <code>12345 50000</code>\n(Gõ 'huy' để quay lại)")
            bot.register_next_step_handler(msg, lambda m: process_transfer(m, balance))

        elif call.data == "withdraw_fund":
            if balance < 100000:
                return bot.answer_callback_query(call.id, "❌ Cần tối thiểu 100,000đ để rút!", show_alert=True)
            msg = bot.send_message(chat_id, "🏦 <b>RÚT TIỀN</b>\nNhập Ngân Hàng - STK - Chủ TK\n(Gõ 'huy' để hủy)")
            bot.register_next_step_handler(msg, lambda m: process_withdrawal(m, balance))

        elif call.data == "buy_proxy":
            if SYS_CONFIG['maintenance']: return bot.answer_callback_query(call.id, "🛠 Hệ thống đang bảo trì!", show_alert=True)
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton("🌐 IPv4 Share (4,000đ/Ngày)", callback_data="order_j2_share"),
                types.InlineKeyboardButton("🚀 IPv4 Private (10,000đ/Ngày)", callback_data="order_j2_private"),
                types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home")
            )
            # Kiểm tra nếu tin nhắn hiện tại là ảnh (do lúc nạp tiền tạo ra) thì xóa đi gửi text
            if call.message.content_type == 'photo':
                bot.delete_message(chat_id, call.message.message_id)
                bot.send_message(chat_id, "🛒 <b>CHỌN DỊCH VỤ PROXY:</b>", reply_markup=kb)
            else:
                bot.edit_message_text("🛒 <b>CHỌN DỊCH VỤ PROXY:</b>", chat_id, call.message.message_id, reply_markup=kb)

        elif call.data.startswith("order_j2_"):
            ptype = call.data.split("_")[2]
            price = 4000 if ptype == "share" else 10000
            api_type = "ipv4_shared" if ptype == "share" else "ipv4_private"
            
            if vip == 1: price = int(price * 0.95)
            elif vip == 2: price = int(price * 0.9)
            elif vip == 3: price = int(price * 0.8)
            
            if balance < price: return bot.answer_callback_query(call.id, f"❌ Thiếu {price - balance:,}đ nữa. Nạp đi sếp!", show_alert=True)
                
            bot.edit_message_text("⏳ <i>Đang khởi tạo Proxy... Đợi xíu...</i>", chat_id, call.message.message_id)
            proxy = call_j2proxy_api(api_type)
            
            if proxy:
                update_balance(chat_id, -price, reason=f"Mua Proxy {ptype.upper()}")
                receipt = (f"✅ <b>CHỐT ĐƠN THÀNH CÔNG</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                           f"🔖 Mã ĐH: <code>#J2_{random.randint(10000, 99999)}</code>\n"
                           f"📦 Dịch vụ: <b>IPv4 {ptype.upper()}</b>\n💵 Thanh toán: <b>{price:,}đ</b>\n"
                           f"━━━━━━━━━━━━━━━━━━━━━━\n🔐 <b>PROXY INFO:</b>\n<code>{proxy}</code>\n\n<i>💰 Số dư còn lại: {balance - price:,} VNĐ</i>")
                kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home"))
                bot.edit_message_text(receipt, chat_id, call.message.message_id, reply_markup=kb)
            else:
                bot.edit_message_text("⚠️ <b>LỖI KẾT NỐI API NGUỒN</b>", chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home")))

        elif call.data == "lucky_wheel":
            text = (f"🎰 <b>VÒNG QUAY NHÂN PHẨM</b>\nVé quay: <b>{WHEEL_PRICE}đ/Lượt</b>\nTrúng lớn hoặc mất trắng!")
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton(f"🕹 QUAY NGAY (-{WHEEL_PRICE}đ)", callback_data="spin_wheel"),
                types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home")
            )
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "spin_wheel":
            if balance < WHEEL_PRICE: return bot.answer_callback_query(call.id, f"❌ Cần tối thiểu {WHEEL_PRICE}đ!", show_alert=True)
            
            update_balance(chat_id, -WHEEL_PRICE, reason="Quay Wheel")
            chance = random.randint(1, 100)
            if chance <= 10: prize, msg = 1000, "🎉 <b>NỔ HŨ!</b> Trúng 1,000 VNĐ!"
            elif chance <= 40: prize, msg = 200, "👍 Trúng 200 VNĐ."
            else: prize, msg = 0, "😭 Xịt cmnr! Chúc sếp may mắn lần sau."
            
            if prize > 0: update_balance(chat_id, prize, reason="Trúng Wheel")
            kb = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton("🔄 QUAY LẠI LẦN NỮA", callback_data="spin_wheel"),
                types.InlineKeyboardButton("🔙 TRỞ VỀ MENU", callback_data="back_home")
            )
            bot.edit_message_text(f"🎰 <b>KẾT QUẢ VÒNG QUAY</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{msg}\n<i>Mã quay: {random.randint(100,999)}</i>", chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "daily_checkin":
            today = str(date.today())
            if last_checkin == today: bot.answer_callback_query(call.id, "❌ Đã điểm danh hôm nay!", show_alert=True)
            else:
                update_balance(chat_id, 50, reason="Điểm danh")
                db_query("UPDATE users SET last_checkin = ? WHERE chat_id = ?", (today, chat_id))
                bot.answer_callback_query(call.id, f"🎉 Nhận +50đ", show_alert=True)
                bot.send_message(chat_id, f"📅 <b>ĐIỂM DANH:</b> Đã cộng <b>+50 VNĐ</b>")

        elif call.data == "get_ref":
            ref_link = f"https://t.me/{bot.get_me().username}?start={chat_id}"
            text = (f"🔗 <b>CHƯƠNG TRÌNH AFFILIATE</b>\nLink của bạn:\n<code>{ref_link}</code>\n🎁 Nhận ngay <b>5%</b> khi ref nạp tiền!")
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home")))

        elif call.data == "enter_giftcode":
            msg = bot.send_message(chat_id, "🎁 Nhập mã Code của bạn (Gõ 'huy' để hủy):")
            bot.register_next_step_handler(msg, process_giftcode)

        elif call.data == "create_subbot":
            if balance < MIN_BALANCE_FOR_SUBBOT: return bot.answer_callback_query(call.id, f"❌ Cần tối thiểu {MIN_BALANCE_FOR_SUBBOT:,}đ!", show_alert=True)
            msg = bot.send_message(chat_id, "🤖 <b>TẠO BOT ĐẠI LÝ</b>\nNhập API Token lấy từ @BotFather (Gõ 'huy' để hủy):")
            bot.register_next_step_handler(msg, lambda m: create_subbot_process(m, balance))

        elif call.data == "tx_history":
            history = db_query("SELECT amount, reason, created_at FROM transactions WHERE chat_id=? ORDER BY id DESC LIMIT 5", (chat_id,), True)
            text = "🧾 <b>LỊCH SỬ GIAO DỊCH</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for tx in history or []:
                text += f"{'🟢' if tx[0]>0 else '🔴'} <code>{tx[2][:16]}</code>\n💰 {tx[0]:,}đ | <i>{tx[1]}</i>\n\n"
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home"))
            if call.message.content_type == 'photo':
                bot.delete_message(chat_id, call.message.message_id)
                bot.send_message(chat_id, text, reply_markup=kb)
            else:
                bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "top_spenders":
            top_users = db_query("SELECT chat_id, total_deposit FROM users ORDER BY total_deposit DESC LIMIT 5", fetch=True)
            text = "🏆 <b>TOP ĐẠI GIA HỆ THỐNG</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
            for i, u in enumerate(top_users): text += f"{medals[i]} ID: <code>{str(u[0])[:4]}***</code> - Nạp: <b>{u[1]:,}đ</b>\n\n"
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home")))

        elif call.data == "guide":
            text = "📖 <b>HƯỚNG DẪN</b>\n- Nạp tiền theo mã QR (5-10s).\n- Mua proxy nhận định dạng chuẩn.\n- Tạo bot con tự động kiếm 200đ hoa hồng/đơn thụ động."
            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="back_home")))

        # ---------------- ADMIN PANEL ----------------
        elif call.data == "admin_panel" and chat_id == ADMIN_ID:
            kb = types.InlineKeyboardMarkup(row_width=2).add(
                types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
                types.InlineKeyboardButton("🎁 Tạo Giftcode", callback_data="adm_gc"),
                types.InlineKeyboardButton("🔧 Bảo Trì", callback_data="adm_mt"),
                types.InlineKeyboardButton("📊 Báo cáo", callback_data="adm_st"),
                types.InlineKeyboardButton("🔍 Quản lý User", callback_data="adm_us"),
                types.InlineKeyboardButton("💸 Yêu cầu Rút", callback_data="adm_wd"),
                types.InlineKeyboardButton("🔙 Thoát", callback_data="back_home")
            )
            bot.edit_message_text("🛠 <b>ADMIN PANEL</b>", chat_id, call.message.message_id, reply_markup=kb)

        elif call.data == "adm_mt" and chat_id == ADMIN_ID:
            SYS_CONFIG['maintenance'] = not SYS_CONFIG['maintenance']
            bot.answer_callback_query(call.id, f"Bảo trì: {'BẬT 🔴' if SYS_CONFIG['maintenance'] else 'TẮT 🟢'}", show_alert=True)

        elif call.data == "adm_st" and chat_id == ADMIN_ID:
            u = db_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
            b = db_query("SELECT COUNT(*) FROM sub_bots", fetch=True)[0][0]
            t = db_query("SELECT SUM(total_deposit) FROM users", fetch=True)[0][0] or 0
            bot.answer_callback_query(call.id, f"👥 User: {u}\n🤖 Bot con: {b}\n💵 Dòng tiền: {t:,}đ", show_alert=True)

        elif call.data == "adm_gc" and chat_id == ADMIN_ID:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            db_query("INSERT INTO giftcodes (code, value, max_uses) VALUES (?, ?, ?)", (code, 5000, 10))
            bot.send_message(chat_id, f"✅ Code: <code>{code}</code> (5k)")

        elif call.data == "adm_bc" and chat_id == ADMIN_ID:
            msg = bot.send_message(chat_id, "Nhập thông báo:")
            bot.register_next_step_handler(msg, lambda m: process_broadcast(m))
            
        elif call.data == "adm_us" and chat_id == ADMIN_ID:
            msg = bot.send_message(chat_id, "🛠 <b>QUẢN LÝ USER:</b>\nCheck: <code>[ID]</code>\nCộng/trừ: <code>[ID] [Tiền]</code>\nKhóa: <code>[ID] ban</code>\nMở: <code>[ID] unban</code>")
            bot.register_next_step_handler(msg, admin_handle_user)
            
        elif call.data == "adm_wd" and chat_id == ADMIN_ID:
            reqs = db_query("SELECT id, chat_id, amount, bank_info FROM withdraw_requests WHERE status='pending'", fetch=True)
            if not reqs: return bot.answer_callback_query(call.id, "Không có yêu cầu.", show_alert=True)
            text = "💸 <b>CÁC LỆNH ĐANG CHỜ:</b>\n"
            for r in reqs: text += f"ID: {r[1]} | {r[2]:,}đ\nNH: {r[3]}\n\n"
            bot.send_message(chat_id, text)

    except Exception as e: print(f"Lỗi Callback: {traceback.format_exc()}")
    finally:
        try: bot.answer_callback_query(call.id)
        except: pass

# ================= CÁC HÀM XỬ LÝ NHẬP =================
def process_transfer(message, balance):
    try:
        chat_id = message.chat.id
        if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy.")
        parts = message.text.split()
        if len(parts) != 2: return bot.send_message(chat_id, "❌ Cú pháp sai.")
        tid, amount = int(parts[0]), int(parts[1])
        if amount <= 0 or balance < amount: return bot.send_message(chat_id, "❌ Không đủ tiền hoặc số tiền sai.")
        
        target = db_query("SELECT chat_id FROM users WHERE chat_id=?", (tid,), True)
        if not target: return bot.send_message(chat_id, "❌ ID không tồn tại.")
        
        update_balance(chat_id, -amount, reason=f"Chuyển ID {tid}")
        update_balance(tid, amount, reason=f"Nhận từ ID {chat_id}")
        bot.send_message(chat_id, f"✅ Đã chuyển <b>{amount:,}đ</b> cho <code>{tid}</code>")
        try: bot.send_message(tid, f"💸 Nhận <b>{amount:,}đ</b> từ <code>{chat_id}</code>")
        except: pass
    except Exception as e: bot.send_message(message.chat.id, "❌ Lỗi cú pháp.")

def process_withdrawal(message, balance):
    try:
        chat_id = message.chat.id
        if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy.")
        db_query("INSERT INTO withdraw_requests (chat_id, amount, bank_info) VALUES (?, ?, ?)", (chat_id, balance, message.text))
        update_balance(chat_id, -balance, reason="Lệnh rút")
        bot.send_message(chat_id, "✅ Đã gửi lệnh.")
        try: bot.send_message(ADMIN_ID, f"🔔 <b>RÚT TIỀN</b>\nID: {chat_id} | {balance:,}đ\nTT: {message.text}")
        except: pass
    except Exception as e: print(e)

def process_giftcode(message):
    try:
        chat_id = message.chat.id
        if message.text.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy.")
        code = message.text.strip().upper()
        if db_query("SELECT * FROM history_codes WHERE chat_id=? AND code=?", (chat_id, code), True): return bot.send_message(chat_id, "❌ Đã dùng mã này!")
        gift = db_query("SELECT value, max_uses, used_count FROM giftcodes WHERE code=?", (code,), True)
        if gift and gift[0][2] < gift[0][1]:
            db_query("UPDATE giftcodes SET used_count = used_count + 1 WHERE code=?", (code,))
            db_query("INSERT INTO history_codes (chat_id, code) VALUES (?, ?)", (chat_id, code))
            update_balance(chat_id, gift[0][0], reason=f"Nạp Code {code}")
            bot.send_message(chat_id, f"🔥 Lụm <b>{gift[0][0]:,} VNĐ</b>")
        else: bot.send_message(chat_id, "❌ Code dỏm!")
    except Exception as e: print(e)

def process_broadcast(message):
    try:
        if message.text.lower() == 'huy': return
        users = db_query("SELECT chat_id FROM users", fetch=True)
        count = 0
        for u in users:
            try: bot.send_message(u[0], f"📣 <b>THÔNG BÁO TỪ HỆ THỐNG</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{message.text}"); count += 1
            except: pass
        bot.send_message(ADMIN_ID, f"✅ Đã gửi {count} user.")
    except Exception as e: print(e)

def admin_handle_user(message):
    try:
        if message.text.lower() == 'huy': return
        parts = message.text.split()
        uid = int(parts[0])
        if len(parts) == 1:
            b, t, v, _, _, ban = get_user(uid)
            bot.send_message(ADMIN_ID, f"👤 <b>INFO:</b> <code>{uid}</code>\n💵 Lúa: {b:,}đ\n🚫 Ban: {'CÓ' if ban else 'KHÔNG'}")
        elif len(parts) == 2: 
            if parts[1].lower() == 'ban': db_query("UPDATE users SET is_banned=1 WHERE chat_id=?", (uid,)); bot.send_message(ADMIN_ID, f"✅ KHÓA ID {uid}")
            elif parts[1].lower() == 'unban': db_query("UPDATE users SET is_banned=0 WHERE chat_id=?", (uid,)); bot.send_message(ADMIN_ID, f"✅ MỞ ID {uid}")
            else: 
                amt = int(parts[1])
                update_balance(uid, amt, reason="Admin buff tiền")
                bot.send_message(ADMIN_ID, f"✅ Đã {'cộng' if amt>0 else 'trừ'} {abs(amt):,}đ cho {uid}")
    except Exception as e: bot.send_message(ADMIN_ID, "❌ Lỗi cú pháp.")

# ================= HỆ THỐNG SUB-BOT BẤT TỬ =================
def create_subbot_process(message, balance):
    try:
        chat_id = message.chat.id
        token = message.text.strip()
        if token.lower() == 'huy': return bot.send_message(chat_id, "Đã hủy.")
        
        # Check số dư thật lần 2 cho chắc chắn
        if get_user(chat_id)[0] < MIN_BALANCE_FOR_SUBBOT: return bot.send_message(chat_id, "❌ Lỗi số dư.")

        update_balance(chat_id, -MIN_BALANCE_FOR_SUBBOT, reason="Tạo Bot Đại Lý")
        db_query("INSERT INTO sub_bots (owner_id, token) VALUES (?, ?)", (chat_id, token))
        bot.send_message(chat_id, "✅ <b>BOT LÊN SÓNG!</b>")
        threading.Thread(target=run_sub_bot, args=(token, chat_id), daemon=True).start()
    except sqlite3.IntegrityError:
        bot.send_message(chat_id, "❌ Token trùng!")
        update_balance(chat_id, MIN_BALANCE_FOR_SUBBOT, reason="Hoàn tiền Bot")
    except Exception as e: print(e)

def run_sub_bot(token, owner_id):
    while True: # Vòng lặp bất tử chống rớt mạng của Render
        try:
            sub_bot = telebot.TeleBot(token, parse_mode='HTML', threaded=False)
            @sub_bot.message_handler(commands=['start', 'mua'])
            def sub_handler(m):
                try:
                    if m.text == '/start': sub_bot.reply_to(m, "👋 <b>ĐẠI LÝ J2PROXY</b>\nGõ /mua để lên đơn.")
                    elif m.text == '/mua':
                        if SYS_CONFIG['maintenance']: return sub_bot.reply_to(m, "Đang bảo trì!")
                        buyer_id = m.chat.id
                        if get_user(buyer_id)[0] < 4000: return sub_bot.reply_to(m, f"❌ Cần 4,000đ. Nạp bên @{bot.get_me().username}")
                        
                        sub_bot.reply_to(m, "⏳ Đang lấy IP...")
                        proxy = call_j2proxy_api("ipv4_shared")
                        if proxy:
                            update_balance(buyer_id, -4000, reason="Mua Proxy (Đại Lý)")
                            update_balance(owner_id, SUBBOT_COMMISSION, reason="Lãi đại lý")
                            sub_bot.send_message(buyer_id, f"✅ <b>CHỐT ĐƠN!</b>\n🔐 <code>{proxy}</code>")
                            try: bot.send_message(owner_id, f"🤑 Có đơn! Nhận: <b>+{SUBBOT_COMMISSION}đ</b>")
                            except: pass
                        else: sub_bot.reply_to(m, "⚠️ Lỗi API / Hết hàng.")
                except Exception as e: print(f"Lỗi Subbot Logic: {e}")
            
            print(f"[*] Khởi chạy Subbot {token[-5:]} thành công.")
            sub_bot.polling(none_stop=True, timeout=15, long_polling_timeout=5)
            
        except Exception as e:
            print(f"[!] Subbot Crash: {e}. Thử lại sau 5s...")
            time.sleep(5)

# ================= BOOTSTRAP HỆ THỐNG =================
def run_main_bot():
    while True: # Vòng lặp bất tử cho Bot chính
        try:
            print("Đang khởi động Bot Telegram...")
            bot.polling(none_stop=True, timeout=15, long_polling_timeout=5)
        except Exception as e:
            print(f"[!] Mất kết nối Bot. Khởi động lại sau 5s... Lỗi: {e}")
            time.sleep(5)

if __name__ == '__main__':
    print("1. Kích hoạt mạng lưới Sub-bots...")
    bots = db_query("SELECT token, owner_id FROM sub_bots", fetch=True)
    for b in bots or []: threading.Thread(target=run_sub_bot, args=(b[0], b[1]), daemon=True).start()
        
    print("2. Chạy Polling Main Bot chống Crash...")
    threading.Thread(target=run_main_bot, daemon=True).start()
    
    print("🚀 TẤT CẢ ĐÃ SẴN SÀNG! 🚀")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
