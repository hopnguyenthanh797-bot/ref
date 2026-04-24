import asyncio
from supabase import create_client, Client
from config import config
from datetime import datetime

class Database:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    async def get_user(self, user_id: int, full_name: str):
        def _get():
            res = self.client.table('users').select('*').eq('user_id', user_id).execute()
            if not res.data:
                new_user = {
                    'user_id': user_id, 'full_name': full_name,
                    'balance': 0, 'total_spent': 0, 'total_deposit': 0
                }
                self.client.table('users').insert(new_user).execute()
                return new_user
            return res.data[0]
        return await asyncio.to_thread(_get)

    async def update_balance(self, user_id: int, amount: int, is_deposit=False):
        def _update():
            user = self.client.table('users').select('balance, total_deposit').eq('user_id', user_id).execute().data[0]
            new_balance = user['balance'] + amount
            update_data = {'balance': new_balance}
            if is_deposit and amount > 0:
                update_data['total_deposit'] = user['total_deposit'] + amount
            self.client.table('users').update(update_data).eq('user_id', user_id).execute()
            return new_balance
        return await asyncio.to_thread(_update)

    async def add_order(self, user_id: int, product_name: str, price: int, data: str):
        def _add():
            # Lưu lịch sử đơn hàng
            self.client.table('orders').insert({
                'user_id': user_id, 'product_name': product_name,
                'price': price, 'resource_data': data
            }).execute()
            # Cập nhật tổng chi
            user = self.client.table('users').select('total_spent').eq('user_id', user_id).execute().data[0]
            self.client.table('users').update({'total_spent': user['total_spent'] + price}).eq('user_id', user_id).execute()
        return await asyncio.to_thread(_add)

    async def get_history(self, user_id: int, limit=5):
        def _get_hist():
            res = self.client.table('orders').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
            return res.data
        return await asyncio.to_thread(_get_hist)

    async def get_settings(self):
        def _get_set():
            res = self.client.table('settings').select('*').eq('id', 1).execute()
            if not res.data:
                default_set = {'id': 1, 'markup_percent': 20, 'guide_link': 'https://t.me/admin', 'bank_info': 'MSB | 1234 | ADMIN'}
                self.client.table('settings').insert(default_set).execute()
                return default_set
            return res.data[0]
        return await asyncio.to_thread(_get_set)

    async def update_setting(self, key: str, value):
        def _update_set():
            self.client.table('settings').update({key: value}).eq('id', 1).execute()
        return await asyncio.to_thread(_update_set)

db = Database()
