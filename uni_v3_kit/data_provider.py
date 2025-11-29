import requests
import time

class DataProvider:
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.base_url = "https://apiindex.mucho.finance"

    def get_market_iv(self, currency="ETH"):
        """Obtiene IV desde Deribit (DVOL)"""
        try:
            url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
            params = {
                "currency": currency.upper(),
                "resolution": "1D",
                "end_timestamp": int(time.time()*1000)
            }
            data = requests.get(url, params=params).json()
            return data['result']['data'][-1][4] / 100.0
        except Exception as e:
            print(f"Error Deribit: {e}")
            return 0.55 

    def get_all_pools(self):
        """API 1: Listado general"""
        endpoint = f"{self.base_url}/pools"
        try:
            response = requests.get(endpoint, headers=self.headers)
            return response.json().get('pools', [])
        except Exception as e:
            return []

    def get_pool_history(self, pool_address):
        """API 2: Devuelve el OBJETO COMPLETO del pool (info + history)"""
        endpoint = f"{self.base_url}/pool/history"
        params = {"id": pool_address}
        try:
            response = requests.get(endpoint, params=params, headers=self.headers)
            data = response.json()
            # Devolvemos todo el objeto 'pool', no solo 'history', para acceder a poolName
            if "pool" in data and data["pool"]:
                return data["pool"]
            return {}
        except:
            return {}
