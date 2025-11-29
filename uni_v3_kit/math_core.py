import math
import numpy as np

class V3Math:
    @staticmethod
    def calculate_realized_volatility(price_history):
        """Calcula volatilidad anualizada basada en precios pasados"""
        if len(price_history) < 5: return 0.80 
        try:
            prices = np.array(price_history, dtype=float)
            prices = prices[prices > 0]
            if len(prices) < 2: return 0.80
            returns = np.diff(np.log(prices))
            std_dev = np.std(returns)
            return std_dev * math.sqrt(365)
        except:
            return 0.80

    @staticmethod
    def calculate_il_risk_cost(volatility_annual):
        return (volatility_annual ** 2) / 2

    # --- CÁLCULO EXACTO DE IL EN V3 (SIMULACIÓN) ---
    @staticmethod
    def calculate_v3_il_at_limit(range_width_pct):
        """
        Calcula el Impermanent Loss exacto de Uniswap V3 al tocar el límite del rango.
        Simula una posición de 1000 USD y compara el valor final en el pool vs HODL.
        """
        try:
            width = max(range_width_pct, 0.001)
            
            # 1. Definimos escenario normalizado
            P_entry = 1.0
            
            # Rango simétrico porcentual: P * (1 +/- width)
            P_min = P_entry * (1 - width)
            P_max = P_entry * (1 + width)
            
            # 2. Inversión teórica de 1000 USD para simular
            investment = 1000.0
            
            # 3. Calcular Liquidez (L) y Tokens Iniciales (HODL Stack) al entrar
            # Usamos las fórmulas de V3 para obtener x0 (Base) e y0 (Quote)
            L = V3Math.get_liquidity_for_amount(investment, P_entry, P_min, P_max)
            
            if L == 0: return 0.0
            
            # Tokens iniciales que compramos (x0=Base, y0=Quote)
            x0, y0 = V3Math.calculate_amounts(L, math.sqrt(P_entry), math.sqrt(P_min), math.sqrt(P_max))
            
            # --- ESCENARIO A: El precio baja hasta P_min (Límite Inferior) ---
            # En P_min, el pool se llena de Token Base (x). y = 0.
            
            # Valor HODL en P_min (nuestros tokens originales valorados a precio bajo)
            val_hodl_min = (x0 * P_min) + y0
            
            # Valor POOL en P_min
            # Calculamos qué tokens tenemos realmente en el pool a precio P_min
            # (Todo X, nada Y)
            x_min, y_min = V3Math.calculate_amounts(L, math.sqrt(P_min), math.sqrt(P_min), math.sqrt(P_max))
            val_pool_min = (x_min * P_min) + y_min
            
            il_min = (val_pool_min - val_hodl_min) / val_hodl_min if val_hodl_min > 0 else 0
            
            # --- ESCENARIO B: El precio sube hasta P_max (Límite Superior) ---
            # En P_max, el pool se llena de Token Quote (y). x = 0.
            
            # Valor HODL en P_max
            val_hodl_max = (x0 * P_max) + y0
            
            # Valor POOL en P_max
            # (Nada X, todo Y)
            x_max, y_max = V3Math.calculate_amounts(L, math.sqrt(P_max), math.sqrt(P_min), math.sqrt(P_max))
            val_pool_max = (x_max * P_max) + y_max
            
            il_max = (val_pool_max - val_hodl_max) / val_hodl_max if val_hodl_max > 0 else 0
            
            # Devolvemos la peor pérdida (máximo IL posible en el rango) en valor absoluto positivo
            # Nota: IL siempre es negativo, devolvemos el % de pérdida como positivo (ej 0.05 para 5%)
            return max(abs(il_min), abs(il_max))
            
        except Exception as e:
            print(f"Error calculando IL: {e}")
            return 0.0

    # --- Fórmulas Oficiales Uniswap V3 ---
    @staticmethod
    def get_liquidity_for_amount(amount_usd, price_current, price_min, price_max):
        """Calcula L dado un valor en USD y el rango (Asumiendo P_quote = 1 USD)"""
        if price_current <= price_min or price_current >= price_max: return 0 
        
        sqrt_p = math.sqrt(price_current)
        sqrt_a = math.sqrt(price_min)
        sqrt_b = math.sqrt(price_max)
        
        # Cantidad de tokens necesarios para 1 unidad de Liquidez (L=1)
        # Amount X (Base) = (1/sqrtP - 1/sqrtB)
        amount_x_unit = (1/sqrt_p) - (1/sqrt_b)
        
        # Amount Y (Quote) = (sqrtP - sqrtA)
        amount_y_unit = sqrt_p - sqrt_a
        
        # Valor en USD de esa unidad de liquidez
        # Asumimos price_current es el precio del activo base en USD
        cost_unit_usd = (amount_x_unit * price_current) + amount_y_unit
        
        if cost_unit_usd == 0: return 0
        
        return amount_usd / cost_unit_usd

    @staticmethod
    def calculate_amounts(liquidity, sqrt_p, sqrt_a, sqrt_b):
        """Calcula cantidad real de tokens x e y dado L y precios (Raíces)"""
        # Caso 1: Precio debajo del rango (P <= Pa) -> Todo es Token X (Base)
        if sqrt_p <= sqrt_a:
            amount_x = liquidity * (sqrt_b - sqrt_a) / (sqrt_a * sqrt_b)
            amount_y = 0
            
        # Caso 2: Precio encima del rango (P >= Pb) -> Todo es Token Y (Quote)
        elif sqrt_p >= sqrt_b:
            amount_x = 0
            amount_y = liquidity * (sqrt_b - sqrt_a)
            
        # Caso 3: En rango -> Mezcla
        else:
            amount_x = liquidity * (sqrt_b - sqrt_p) / (sqrt_p * sqrt_b)
            amount_y = liquidity * (sqrt_p - sqrt_a)
            
        return amount_x, amount_y

    @staticmethod
    def calculate_concentration_multiplier(range_width_pct):
        # Mantenemos esta función por compatibilidad, aunque no se use en el cálculo de IL
        try:
            w = max(range_width_pct, 0.001) 
            ratio = (1 - w) / (1 + w)
            multiplier = 1 / (1 - math.sqrt(ratio))
            return min(multiplier, 100.0)
        except:
            return 1.0
