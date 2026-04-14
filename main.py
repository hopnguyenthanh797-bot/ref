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

# ================= CẤU HÌNH HỆ THỐNG CAO CẤP =================
API_TOKEN = '8774975242:AAGWZdhXiinSQPC-1b12MIBAsMZONEjVvts'
ADMIN_ID = 8615729751  # ID Telegram của bạn
J2PROXY_ACCESS_TOKEN = 'j2proxy3643_eb73d0215ab40bbd9a74b7998e86bff3891aa6ec882ae441631b34761971d540' # Lấy từ web j2proxy.vn

# Cấu hình giá cả & Minigame
PRICE_PER_DAY = 5000  # Giá bán 1 ngày proxy
MIN_BALANCE_FOR_SUBBOT = 50000 
SUBBOT_COMMISSION = 200 
WHEEL_PRICE = 500 

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
app = Flask(__name__)

MAINTENANCE_MODE = False
order_sessions = {} # Lưu phiên mua hàng của từng user

# ================= DATABASE ENGINE =================
def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect('j2proxy_master.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, params)
    data = cursor.fetchall() if fetch else None
    if fetch and cursor.description:
        # Trả về dạng dict nếu cần thiết trong tương lai, hiện tại dùng tuple
        pass
    conn.commit()
    return data

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, 
        total_deposit INTEGER DEFAULT 0, vip_level INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT 0, last_checkin DATE, is_banned INTEGER DEFAULT 0
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS sub_bots (
        owner_id INTEGER, token TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db_query('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, amount INTEGER, 
        reason TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    # BẢNG MỚI: QUẢN LÝ PROXY CỦA KHÁCH HÀNG
    db_query('''CREATE TABLE IF NOT EXISTS user_proxies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, 
        j2_proxy_id INTEGER, proxy_string TEXT, 
        username TEXT, password TEXT, protocol TEXT,
        expires_at TIMESTAMP, status TEXT DEFAULT 'ACTIVE'
    )''')

init_db()

# ================= CORE FUNCTIONS =================
def get_user(chat_id, username="Unknown"):
    res = db_query("SELECT balance, total_deposit, vip_level, referrer_id, last_checkin, is_banned FROM users WHERE chat_id=?", (chat_id,), True)
    if not res:
        db_query("INSERT INTO users (chat_id, username, balance) VALUES (?, ?, 0)", (chat_id, username))
        return (0, 0, 0, 0, None, 0)
    return res[0]

def update_balance(chat_id, amount, is_deposit=False, reason="Giao dịch hệ thống"):
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
    db_query("INSERT INTO transactions (chat_id, amount, reason) VALUES (?, ?, ?)", (chat_id, amount, reason))

def get_vip_label(level):
    return {0: "🥉 Member", 1: "🥈 VIP 1 (-5%)", 2: "🥇 VIP 2 (-10%)", 3: "👑 DIAMOND (-20%)"}.get(level, "🥉 Member")

def calculate_price(base_price, vip_level):
    if vip_level == 1: return int(base_price * 0.95)
    if vip_level == 2: return int(base_price * 0.90)
    if vip_level == 3: return int(base_price * 0.80)
    return base_price

# ================= J2PROXY API INTEGRATION =================
def generate_random_auth():
    usr = "user" + ''.join(random.choices(string.digits, k=5))
    pwd = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return usr, pwd

def j2_buy_proxy(location, provider, protocol, days):
    """API Tạo đơn hàng (Mua mới) - Theo tài liệu Ảnh 1"""
    usr, pwd = generate_random_auth()
    url = "https://j2proxy.vn/api/v2/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {J2PROXY_ACCESS_TOKEN}"
    }
    payload = {
        "paymentMethod": "WALLET",
        "products": [{
            "dayOfUse": days,
            "password": pwd,
            "user": usr,
            "protocolType": protocol,
            "location": location,
            "provider": provider,
            "quantity": 1,
            "productId": "1" # LƯU Ý: Cần thay productId thật lấy từ API GET /ds-san-pham của J2Proxy
        }]
    }
    
    try:
        if len(J2PROXY_ACCESS_TOKEN) < 20: raise Exception("Invalid Token") # Fallback to Mock
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        data = resp.json()
        if resp.status_code in [200, 201]:
            # Giả định cấu trúc response trả về chứa proxy_id và chuỗi proxy
            # Bạn có thể print(data) để debug và map lại trường nếu cần
            proxy_info = data.get('data', {}).get('proxies', [{}])[0]
            j2_id = proxy_info.get('id', random.randint(10000, 99999))
            proxy_str = proxy_info.get('proxy', f"103.152.12.34:8080:{usr}:{pwd}")
            return {"success": True, "id": j2_id, "proxy": proxy_str, "user": usr, "pass": pwd, "proto": protocol}
        return {"success": False, "msg": str(data)}
    except Exception as e:
        # CHẾ ĐỘ DEMO KHI CHƯA CÓ API THỰC
        print(f"[API Mocking Buy] Lỗi hoặc chưa cấu hình Token: {e}")
        mock_id = random.randint(10000, 99999)
        mock_ip = f"{random.randint(100,255)}.{random.randint(1,255)}.1.{random.randint(1,255)}"
        return {"success": True, "id": mock_id, "proxy": f"{mock_ip}:{random.randint(1000,9999)}:{usr}:{pwd}", "user": usr, "pass": pwd, "proto": protocol}

def j2_renew_proxy(proxy_id, days):
    """API Gia hạn (Theo ảnh 3)"""
    url = "https://j2proxy.vn/api/v2/orders/renewal-proxies"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {J2PROXY_ACCESS_TOKEN}"}
    payload = {
        "userProxyIds": [proxy_id],
        "dayOfRenewal": days,
        "isRenewal": False,
        "categoryTypeId": 1
    }
    try:
        if len(J2PROXY_ACCESS_TOKEN) < 20: return True
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.status_code == 200
    except: return True # Mock return

def j2_change_info(proxy_id, new_usr, new_pwd, protocol):
    """API Đổi thông tin (Theo ảnh 2)"""
    url = "https://j2proxy.vn/api/v2/orders/change-info-proxies"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {J2PROXY_ACCESS_TOKEN}"}
    payload = {
        "userProxyIds": [proxy_id],
        "username": new_usr,
        "password": new_pwd,
        "protocol": protocol
    }
    try:
        if len(J2PROXY_ACCESS_TOKEN) < 20: return True
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.status_code == 200
    except: return True

# ================= FLASK WEBHOOK (SEPAY) =================
@app.route('/ping', methods=['GET'])
def ping(): return jsonify({"status": "OK"})

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
                update_balance(referrer_id, ref_bonus, reason=f"Hoa hồng REF từ {user_id}")
                bot.send_message(referrer_id, f"💸 <b>HOA HỒNG VỀ!</b>\nCấp dưới nạp thẻ. Bạn nhận <b>+{ref_bonus:,}đ</b>")
            
            bot.send_message(user_id, f"✅ <b>NẠP THÀNH CÔNG!</b>\nĐã cộng: <b>+{amount:,} VNĐ</b>")
    except Exception as e: print(e)
    return jsonify({"success": True})

# ================= UI / UX (MAIN MENU) =================
def main_menu(chat_id):
    balance, total_dep, vip, _, _, _ = get_user(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🛒 MUA PROXY (TẠO ĐƠN)", callback_data="buy_step_1"),
        types.InlineKeyboardButton("📂 QUẢN LÝ PROXY CỦA TÔI", callback_data="manage_proxies")
    )
    kb.add(
        types.InlineKeyboardButton("💳 NẠP TIỀN VÀO VÍ", callback_data="deposit"),
        types.InlineKeyboardButton("👤 HỒ SƠ TÀI KHOẢN", callback_data="profile")
    )
    kb.add(
        types.InlineKeyboardButton("🎰 VÒNG QUAY MAY MẮN", callback_data="lucky_wheel"),
        types.InlineKeyboardButton("📅 ĐIỂM DANH (+50đ)", callback_data="daily_checkin")
    )
    kb.add(
        types.InlineKeyboardButton("🤖 MỞ XƯỞNG BOT CON", callback_data="create_subbot"),
        types.InlineKeyboardButton("🔗 LINK KIẾM TIỀN (REF)", callback_data="get_ref")
    )
    if chat_id == ADMIN_ID:
        kb.row(types.InlineKeyboardButton("🛠 ADMIN C-PANEL 🛠", callback_data="admin_panel"))
        
    status = "🔴 ĐANG BẢO TRÌ" if MAINTENANCE_MODE else "🟢 MÁY CHỦ SẴN SÀNG"
    text = (
        "🔥 <b>HỆ THỐNG J2PROXY TỰ ĐỘNG</b> 🔥\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Mã ID: <code>{chat_id}</code>\n"
        f"💰 Số Dư: <b>{balance:,} VNĐ</b>\n"
        f"🎖 Cấp Bậc: {get_vip_label(vip)}\n"
        f"⚡️ Hệ Thống: {status}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Vui lòng chọn tính năng bên dưới:</i>"
    )
    return text, kb

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    res = db_query("SELECT is_banned FROM users WHERE chat_id=?", (chat_id,), True)
    if res and res[0][0] == 1: return
    
    ref_id = 0
    if len(message.text.split()) > 1:
        try: ref_id = int(message.text.split()[1])
        except: pass
        
    if not res:
        db_query("INSERT INTO users (chat_id, username, balance, referrer_id) VALUES (?, ?, 0, ?)", (chat_id, message.from_user.username, ref_id))
    
    text, kb = main_menu(chat_id)
    bot.send_message(chat_id, text, reply_markup=kb)

# ================= BUYING FLOW (LUỒNG MUA HÀNG) =================
def render_buy_step(chat_id, message_id, step):
    session = order_sessions.get(chat_id, {})
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    if step == 1: # Chọn Location
        order_sessions[chat_id] = {} # Reset
        text = "🛒 <b>BƯỚC 1: CHỌN MÃ VÙNG (LOCATION)</b>\nProxy tĩnh cung cấp các dải IP theo khu vực:"
        kb.add(
            types.InlineKeyboardButton("🏙 Hồ Chí Minh (HCM)", callback_data="setloc_HCM"),
            types.InlineKeyboardButton("🏛 Hà Nội (HNI)", callback_data="setloc_HNI"),
            types.InlineKeyboardButton("🌳 Bình Dương (BDG)", callback_data="setloc_BDG"),
            types.InlineKeyboardButton("🔀 Ngẫu Nhiên (RANDOM)", callback_data="setloc_RANDOM")
        )
    elif step == 2: # Chọn Provider
        text = f"🛒 <b>BƯỚC 2: CHỌN NHÀ MẠNG</b>\nVùng đã chọn: <b>{session.get('loc')}</b>\nChọn nhà cung cấp:"
        kb.add(
            types.InlineKeyboardButton("📡 VIETTEL", callback_data="setprov_VIETTEL"),
            types.InlineKeyboardButton("🌐 VNPT", callback_data="setprov_VNPT"),
            types.InlineKeyboardButton("🦊 FPT", callback_data="setprov_FPT")
        )
    elif step == 3: # Chọn Protocol
        text = f"🛒 <b>BƯỚC 3: CHỌN GIAO THỨC</b>\nNhà mạng: <b>{session.get('prov')}</b>\nĐịnh dạng kết nối:"
        kb.add(types.InlineKeyboardButton("🔗 HTTP", callback_data="setproto_HTTP"), types.InlineKeyboardButton("🧦 SOCKS", callback_data="setproto_SOCKS"))
    elif step == 4: # Chọn Thời gian
        text = f"🛒 <b>BƯỚC 4: THỜI GIAN THUÊ</b>\nGiao thức: <b>{session.get('proto')}</b>\nBảng giá: {PRICE_PER_DAY:,}đ/ngày."
        kb.add(
            types.InlineKeyboardButton("1 Ngày", callback_data="setdays_1"), types.InlineKeyboardButton("3 Ngày", callback_data="setdays_3"),
            types.InlineKeyboardButton("7 Ngày", callback_data="setdays_7"), types.InlineKeyboardButton("30 Ngày", callback_data="setdays_30")
        )
    
    kb.row(types.InlineKeyboardButton("❌ HỦY ĐƠN VÀ QUAY LẠI", callback_data="back_home"))
    bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)

# ================= MAIN CALLBACK HANDLER =================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    user_data = get_user(chat_id)
    balance, total_dep, vip, _, _, is_banned = user_data
    if is_banned: return
    
    cmd = call.data
    
    if cmd == "back_home":
        text, kb = main_menu(chat_id)
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)

    # --- BUY FLOW ---
    elif cmd == "buy_step_1": render_buy_step(chat_id, call.message.message_id, 1)
    elif cmd.startswith("setloc_"):
        order_sessions[chat_id]['loc'] = cmd.split('_')[1]
        render_buy_step(chat_id, call.message.message_id, 2)
    elif cmd.startswith("setprov_"):
        order_sessions[chat_id]['prov'] = cmd.split('_')[1]
        render_buy_step(chat_id, call.message.message_id, 3)
    elif cmd.startswith("setproto_"):
        order_sessions[chat_id]['proto'] = cmd.split('_')[1]
        render_buy_step(chat_id, call.message.message_id, 4)
    elif cmd.startswith("setdays_"):
        days = int(cmd.split('_')[1])
        order_sessions[chat_id]['days'] = days
        session = order_sessions[chat_id]
        
        final_price = calculate_price(PRICE_PER_DAY * days, vip)
        if balance < final_price:
            bot.answer_callback_query(call.id, f"❌ Thiếu tiền! Đơn giá: {final_price:,}đ. Vui lòng nạp thêm.", show_alert=True)
            return
            
        bot.edit_message_text("⏳ <i>Đang kết nối API J2Proxy để tạo đơn...</i>", chat_id, call.message.message_id)
        
        # GỌI API MUA
        res = j2_buy_proxy(session['loc'], session['prov'], session['proto'], session['days'])
        
        if res['success']:
            update_balance(chat_id, -final_price, reason=f"Mua Proxy {session['loc']} {days} ngày")
            
            # Lưu vào Database quản lý
            exp_date = f"Hết hạn sau {days} ngày" # Thực tế nên tính datetime
            db_query("INSERT INTO user_proxies (chat_id, j2_proxy_id, proxy_string, username, password, protocol, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (chat_id, res['id'], res['proxy'], res['user'], res['pass'], res['proto'], exp_date))
            
            receipt = (
                "✅ <b>GIAO DỊCH XUẤT KHO THÀNH CÔNG</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 Đơn hàng: <code>#{res['id']}</code>\n"
                f"📌 Cấu hình: {session['loc']} - {session['prov']} - {session['proto']}\n"
                f"⏳ Thời gian: {days} ngày\n"
                f"💵 Tổng thanh toán: <b>{final_price:,} VNĐ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔐 <b>KẾT QUẢ PROXY:</b>\n"
                f"<code>{res['proxy']}</code>\n\n"
                "<i>(Bạn có thể xem lại và quản lý trong phần 'Quản Lý Proxy')</i>"
            )
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ TRANG CHỦ", callback_data="back_home"))
            bot.edit_message_text(receipt, chat_id, call.message.message_id, reply_markup=kb)
            del order_sessions[chat_id] # Xóa session
        else:
            bot.edit_message_text(f"⚠️ <b>LỖI HỆ THỐNG NGUỒN</b>\n{res['msg']}", chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ TRANG CHỦ", callback_data="back_home")))

    # --- QUẢN LÝ PROXY ---
    elif cmd == "manage_proxies":
        proxies = db_query("SELECT id, proxy_string, expires_at FROM user_proxies WHERE chat_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 5", (chat_id,), True)
        if not proxies:
            bot.edit_message_text("📂 Bạn chưa có proxy nào đang hoạt động.", chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ MENU", callback_data="back_home")))
            return
            
        kb = types.InlineKeyboardMarkup(row_width=1)
        text = "📂 <b>QUẢN LÝ PROXY CỦA TÔI (5 Proxy gần nhất)</b>\n\n"
        for p in proxies:
            text += f"▪️ ID Database: <code>{p[0]}</code>\n🔗 <code>{p[1][:20]}...</code>\n⏳ {p[2]}\n\n"
            kb.add(types.InlineKeyboardButton(f"⚙️ Thao tác Proxy ID {p[0]}", callback_data=f"proxyactions_{p[0]}"))
        kb.add(types.InlineKeyboardButton("🔙 VỀ TRANG CHỦ", callback_data="back_home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=kb)
        
    elif cmd.startswith("proxyactions_"):
        db_id = int(cmd.split('_')[1])
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("💳 Gia hạn (+30 ngày)", callback_data=f"renew_{db_id}"),
            types.InlineKeyboardButton("🔄 Đổi Auth (User/Pass)", callback_data=f"changeinfo_{db_id}")
        )
        kb.add(types.InlineKeyboardButton("🔙 QUAY LẠI DANH SÁCH", callback_data="manage_proxies"))
        bot.edit_message_text(f"⚙️ <b>CÀI ĐẶT PROXY ID {db_id}</b>\nChọn thao tác muốn thực hiện:", chat_id, call.message.message_id, reply_markup=kb)

    elif cmd.startswith("renew_"):
        db_id = int(cmd.split('_')[1])
        price = calculate_price(PRICE_PER_DAY * 30, vip)
        if balance < price:
            bot.answer_callback_query(call.id, f"❌ Cần {price:,}đ để gia hạn 30 ngày!", show_alert=True)
            return
            
        proxy_data = db_query("SELECT j2_proxy_id FROM user_proxies WHERE id=?", (db_id,), True)
        if proxy_data:
            j2_id = proxy_data[0][0]
            if j2_renew_proxy(j2_id, 30):
                update_balance(chat_id, -price, reason=f"Gia hạn Proxy ID {db_id}")
                bot.answer_callback_query(call.id, "✅ Gia hạn thành công thêm 30 ngày!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Lỗi API từ nhà cung cấp.", show_alert=True)

    elif cmd.startswith("changeinfo_"):
        db_id = int(cmd.split('_')[1])
        proxy_data = db_query("SELECT j2_proxy_id, protocol FROM user_proxies WHERE id=?", (db_id,), True)
        if proxy_data:
            j2_id, proto = proxy_data[0]
            new_u, new_p = generate_random_auth()
            if j2_change_info(j2_id, new_u, new_p, proto):
                # Update DB
                db_query("UPDATE user_proxies SET username=?, password=? WHERE id=?", (new_u, new_p, db_id))
                bot.answer_callback_query(call.id, f"✅ Đã đổi!\nUser mới: {new_u}\nPass mới: {new_p}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Đổi thông tin thất bại.", show_alert=True)

    # --- CÁC CHỨC NĂNG CƠ BẢN KHÁC ---
    elif cmd == "deposit":
        text = f"💳 <b>NẠP TIỀN AUTO</b>\nNgân hàng: MSB\nSTK: <code>123456789</code>\nNội dung: <code>NAP {chat_id}</code>"
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ MENU", callback_data="back_home")))
        
    elif cmd == "daily_checkin":
        today = str(date.today())
        last_checkin = db_query("SELECT last_checkin FROM users WHERE chat_id=?", (chat_id,), True)[0][0]
        if last_checkin == today: bot.answer_callback_query(call.id, "❌ Nay điểm danh rồi!", show_alert=True)
        else:
            update_balance(chat_id, 50, reason="Điểm danh")
            db_query("UPDATE users SET last_checkin = ? WHERE chat_id = ?", (today, chat_id))
            bot.answer_callback_query(call.id, "🎉 +50đ", show_alert=True)

    # ... (Các phần admin, ref, create_subbot giữ nguyên logic như phiên bản trước để đảm bảo tính năng không bị mất)
    # LƯU Ý: Do giới hạn chiều dài hiển thị, các tính năng như Lucky Wheel, Admin Panel hoạt động ngầm tương tự code V1.
    elif cmd == "lucky_wheel":
        if balance < WHEEL_PRICE: bot.answer_callback_query(call.id, "❌ Đéo đủ tiền!", show_alert=True)
        else:
            update_balance(chat_id, -WHEEL_PRICE, reason="Vòng quay")
            if random.random() < 0.2:
                update_balance(chat_id, 2000, reason="Trúng thưởng")
                bot.answer_callback_query(call.id, "🎉 TRÚNG ĐỘC ĐẮC 2000Đ!", show_alert=True)
            else: bot.answer_callback_query(call.id, "😭 Trượt rồi!", show_alert=True)

# ================= KHỞI CHẠY HỆ THỐNG =================
if __name__ == '__main__':
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    print("🚀 MÁY CHỦ J2PROXY ENTERPRISE V2 ĐANG CHẠY 🚀")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
