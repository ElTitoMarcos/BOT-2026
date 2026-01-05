import time
from typing import Callable, Iterable, List, Optional


class Strategy:
    def __init__(
        self,
        error_handler: Optional[Callable[[str], None]] = None,
        error_sound: Optional[Callable[[], None]] = None,
    ) -> None:
        self.error_handler = error_handler
        self.error_sound = error_sound

    def _handle_error(self, message: str) -> None:
        if self.error_sound:
            self.error_sound()
        if self.error_handler:
            self.error_handler(message)

    def identificar_tendencia(self, summary, symbol):
        recommendation = summary.get('RECOMMENDATION', 'NEUTRAL')
        tendencia = 'LATERAL'
        if recommendation == 'BUY':
            tendencia = 'ALCISTA'
        elif recommendation == 'SELL':
            tendencia = 'BAJISTA'

        # print(f"Tendencia identificada para {symbol}: {tendencia}")
        return tendencia

    def seleccionar_simbolos(
        self,
        tickers,
        analizar_grafico_4h: Callable[[str], dict],
        analizar_grafico_5m: Callable[[str], dict],
    ) -> List[str]:
        symbols_list: List[str] = []
        for ticker in tickers:
            symbol = ticker.get('symbol', '')
            try:
                price = float(ticker.get('lastPrice', 0))
                price_change_percent = float(ticker.get('priceChangePercent', 0))
                quote_volume = float(ticker.get('quoteVolume', 0))
            except ValueError:
                continue

            # Verificar si los datos son válidos y cumplen con las condiciones
            if symbol.endswith('BTC') and symbol != 'ZKBTC' and 0.00000050 <= price <= 0.00000200 and quote_volume >= 0.1:  # 333
                # Verificar si el cambio de precio en las últimas 24 horas está dentro del rango especificado (-6% a 10%)
                if -6 <= price_change_percent <= 10:
                    # Obtener el análisis del gráfico
                    summary_4h = analizar_grafico_4h(symbol)
                    tendencia_4h = self.identificar_tendencia(summary_4h, symbol)
                    summary_5m = analizar_grafico_5m(symbol)
                    tendencia_5m = self.identificar_tendencia(summary_5m, symbol)
                    if tendencia_4h != 'BAJISTA' and tendencia_5m == 'ALCISTA':
                        symbols_list.append(symbol)

        return symbols_list

    def resistencias_mercado(self, symbol, venta_price, order_book):
        try:
            # Obtener los precios y volúmenes de venta del libro de órdenes
            asks = order_book['asks']

            ask_venta = None
            ask_above = None

            # Encontrar el ask más cercano al precio de venta
            min_diff = float('inf')  # Inicializamos con un valor grande
            for ask in asks:
                price = float(ask[0])
                quantity = float(ask[1])
                diff = abs(price - venta_price)

                if diff < min_diff:
                    min_diff = diff
                    ask_venta = (price, quantity)

            if ask_venta:
                ask_above_price = ask_venta[0] + 0.00000001
                # Buscar el ask justo por encima de ask_venta_price
                for ask in asks:
                    price = float(ask[0])
                    quantity = float(ask[1])

                    if price > ask_venta[0]:
                        if ask_above is None or price < ask_above[0]:
                            ask_above = (price, quantity)

            # Verificar si encontramos un ask_above y si la cantidad de ask_venta es 3 veces mayor que la cantidad de ask_above
            if ask_above is not None and ask_venta[1] > 3 * ask_above[1]:
                # print(f"Se ha detectado una resistencia de mercado en el precio de venta de {symbol}.")
                return True

            else:
                # print(f"No se ha detectado una resistencia de mercado en el precio de venta de {symbol}.")
                return False

        except Exception as e:
            self._handle_error(f"Error al detectar la resistencia de mercado para {symbol}: {e}\n")
            print(f"Error al detectar la resistencia de mercado para {symbol}: {e}")
            return False

    def calcular_datos(self, symbol):
        import requests

        # Endpoint de la API de Binance para obtener las transacciones agregadas recientes
        endpoint = "https://api.binance.com/api/v3/aggTrades"
        current_time = int(time.time() * 1000)  # Tiempo actual en milisegundos
        start_time = current_time - 24 * 60 * 60 * 1000  # Timestamp de las últimas 24 horas

        params = {
            'symbol': symbol,
            'startTime': start_time,
            'endTime': current_time,
            'limit': 1000  # Máximo permitido por llamada
        }

        try:
            trades = []
            total_volume = 0
            total_value = 0
            buy_prices = []
            sell_prices = []

            # Obtener transacciones de las últimas 24 horas
            while True:
                response = requests.get(endpoint, params=params)

                if response.status_code != 200:
                    if response.status_code == 400:
                        error_message = response.json()
                        if error_message.get('code') == -1101:
                            return 0.0, 0.0, 0.0
                    print(f"Mensaje de error: {response.json()}")
                    self._handle_error(f"Mensaje de error: {response.json()}\n")
                    return 0.0, 0.0, 0.0

                data = response.json()

                if not data:
                    break

                trades.extend(data)

                if len(data) < 1000:
                    break

                if 'a' in data[-1]:
                    params = {
                        'symbol': symbol,
                        'fromId': data[-1]['a'] + 1,
                        'limit': 1000
                    }
                else:
                    break

            for trade in trades:
                price = float(trade['p'])
                volume = float(trade['q'])
                total_value += price * volume
                total_volume += volume

                if trade['m']:  # Identificar si es una venta (isBuyerMaker)
                    sell_prices.append(price)
                else:  # Es una compra
                    buy_prices.append(price)

            vwap = total_value / total_volume if total_volume else 0
            avg_buy_price = sum(buy_prices) / len(buy_prices) if buy_prices else 0
            avg_sell_price = sum(sell_prices) / len(sell_prices) if sell_prices else 0

            # Redondear a 8 decimales
            vwap = round(vwap, 8)
            avg_buy_price = round(avg_buy_price, 8)
            avg_sell_price = round(avg_sell_price, 8)

            return vwap, avg_buy_price, avg_sell_price
        except requests.RequestException as e:
            print(f"Error en la llamada a la API: {e}")
            return 0.0, 0.0, 0.0
        except ZeroDivisionError:
            return 0.0, 0.0, 0.0

    def generate_signals(self, candles: Iterable) -> list:
        return []
