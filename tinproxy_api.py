import requests

class TinProxy:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://api.tinproxy.com" # Kiểm tra lại URL trong tài liệu TinProxy

    def get_info(self):
        # Lấy thông tin tài khoản đại lý của bạn
        headers = {"Authorization": f"Bearer {self.token}"}
        res = requests.get(f"{self.base_url}/user/info", headers=headers)
        return res.json()

    def buy_proxy(self, service_id, region="vn", isp="viettel"):
        # Logic mua proxy tùy theo API của TinProxy
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"service_id": service_id, "region": region, "isp": isp}
        res = requests.post(f"{self.base_url}/proxy/order", json=payload, headers=headers)
        return res.json()
      
