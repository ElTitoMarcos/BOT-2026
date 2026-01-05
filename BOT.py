import tkinter as tk
import csv
import os
import math
import threading
import time
import requests
import websocket
import json
import ccxt
import pygame
import pandas as pd
import numpy as np
from time import sleep
from requests.exceptions import RequestException
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException
from concurrent.futures import ThreadPoolExecutor
from socket import gaierror
from tradingview_ta import TA_Handler, Interval, Exchange

class MoneyBotApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Money Bot")
        pygame.mixer.init()
        self.client = None
        self.comision_porcentaje = 0.15
        self.precio_anterior = 0.0
        self.cantidad_operacion_usdt = None
        self.nombre_archivo_csv_compra = "datos_ordenes_compra.csv"
        self.nombre_archivo_csv_venta = "datos_ordenes_venta.csv"
        self.lock = threading.Lock()
        self.estado_ordenes = []
        self.total_ordenes = 0
        self.tiempo_espera = self.definir_tiempo_espera()
        # threading.Thread(target=self.ordenes_totales).start()
        self.saldo_insuficiente = False
        self.error_1003 = False
        self.ultimos_valores = []
        self.symbols_list = []
        self.ordenes = True
        self.cantidad_ordenes = {}
        self.min_qty_usdt = 0
        self.min_notional = 0.00000001  # Valor nominal mínimo constante
        self.porcentaje_positivo_24h = None
        self.porcentaje_positivo_24h_anterior = None
        self.cambio_positivo = None
        self.min_qty_btc = None
        self.pares_btc = []
        self.order_ids_in_monitoring = set()  # Registro de order_id en monitoreo
        self.symbols_price_changes = {}  # Diccionario para almacenar los valores de price_change_percent por símbolo
        self.condiciones_operar = None
        self.cantidad_btc = 0
        self.perdidas = []

        self.api_key = None
        self.api_secret = None

        # Load API credentials if available
        self.load_api_credentials()

        self.create_widgets()

    def create_widgets(self):
        self.create_api_configuration()
        self.create_usdt_amount_entry()
        self.create_find_optimal_coins_button()
        self.create_no_abrir_ordenes_button()

    def definir_tiempo_espera(self):
        self.tiempo_espera = {
            "tiempo_realizar_compra": None,
            "tiempo_monitoreo": None,
            "tiempo_verificar_ordenes_individuales_compra": None,
            "tiempo_verificar_ordenes_individuales_venta": None,
            "tiempo_verificar_ordenes_grupales": None
        }

        if self.total_ordenes <= 8:
            self.tiempo_espera["tiempo_monitoreo"] = 1
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 0
        elif self.total_ordenes > 8 and self.total_ordenes <= 13:
            self.tiempo_espera["tiempo_monitoreo"] = 1.2
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 0
        elif self.total_ordenes > 13 and self.total_ordenes <= 18:
            self.tiempo_espera["tiempo_monitoreo"] = 1.65
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 0
        elif self.total_ordenes > 18 and self.total_ordenes <= 25:
            self.tiempo_espera["tiempo_monitoreo"] = 1.8
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 0 #1
        elif self.total_ordenes > 25 and self.total_ordenes <= 37:
            self.tiempo_espera["tiempo_monitoreo"] = 2.3
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 0 #3
        elif self.total_ordenes > 37 and self.total_ordenes <= 44:
            self.tiempo_espera["tiempo_monitoreo"] = 2.65
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 2 #5.5
        elif self.total_ordenes > 44 and self.total_ordenes <= 50:
            self.tiempo_espera["tiempo_monitoreo"] = 2.8
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 5 # 8

        return self.tiempo_espera

    def ordenes_totales(self):
        while True:
            print(f"Ordenes totales: {self.total_ordenes}")
            time.sleep(1)

    def create_no_abrir_ordenes_button(self):
        self.no_abrir_ordenes_button = tk.Button(self, text="No abrir órdenes", command=self.no_abrir_ordenes)
        self.no_abrir_ordenes_button.pack()

    def no_abrir_ordenes(self):
        self.ordenes = False
        print("No se abrirán ordenes nuevas.")

    def create_api_configuration(self):
        frame_configuracion_api = tk.Frame(self)
        frame_configuracion_api.pack()

        tk.Label(frame_configuracion_api, text="API Key:").grid(row=0, column=0)
        self.entry_api_key = tk.Entry(frame_configuracion_api)
        self.entry_api_key.grid(row=0, column=1)
        if self.api_key:
            self.entry_api_key.insert(tk.END, self.api_key)

        tk.Label(frame_configuracion_api, text="API Secret:").grid(row=1, column=0)
        self.entry_api_secret = tk.Entry(frame_configuracion_api)
        self.entry_api_secret.grid(row=1, column=1)
        if self.api_secret:
            self.entry_api_secret.insert(tk.END, self.api_secret)

        tk.Button(frame_configuracion_api, text="Configurar API", command=self.configurar_api).grid(row=2, columnspan=2)

    def load_api_credentials(self):
        if os.path.exists("api_credentials.txt"):
            with open("api_credentials.txt", "r") as file:
                lines = file.readlines()
                if len(lines) >= 2:
                    self.api_key = lines[0].strip()
                    self.api_secret = lines[1].strip()

    def save_api_credentials(self):
        with open("api_credentials.txt", "w") as file:
            if self.api_key:
                file.write(self.api_key + "\n")
            if self.api_secret:
                file.write(self.api_secret + "\n")

    def create_find_optimal_coins_button(self):
        self.find_optimal_coins_button = tk.Button(self, text="Operar", command=self.revision_ordenes_y_obtener_moneda)
        self.find_optimal_coins_button.pack()

    def create_usdt_amount_entry(self):
        frame_usdt_amount = tk.Frame(self)
        frame_usdt_amount.pack()

        tk.Label(frame_usdt_amount, text="Cantidad por Operación (USDT):").grid(row=0, column=0)
        self.entry_usdt_amount = tk.Entry(frame_usdt_amount)
        self.entry_usdt_amount.grid(row=0, column=1)
        tk.Button(frame_usdt_amount, text="Confirmar", command=self.confirmar_cantidad_usdt).grid(row=0, column=2)

    def confirmar_cantidad_usdt(self):
        cantidad = self.entry_usdt_amount.get().strip()
        min_qty_usdt = self.obtener_minima_cantidad_usdt() 
        self.min_qty_usdt = min_qty_usdt

        url = "https://api.binance.com/api/v3/exchangeInfo"
        response = requests.get(url)
        data = response.json()
        
        # Filtrar los símbolos que contienen 'BTC'
        pares_btc = [symbol['symbol'] for symbol in data['symbols'] if 'BTC' in symbol['symbol']]
        
        self.pares_btc = pares_btc

        try:
            cantidad_float = float(cantidad)
            if cantidad_float < self.obtener_minima_cantidad_usdt() + 0.5:
                cantidad_minima = self.obtener_minima_cantidad_usdt() + 0.5
                print(f"La cantidad ingresada está por debajo del mínimo permitido por Binance + 0.5 USDT. El mínimo requerido es: {cantidad_minima} USDT.")
                self.cantidad_operacion_usdt = cantidad_minima
            else:
                self.cantidad_operacion_usdt = cantidad_float
                print("La cantidad por operación en USDT se ha configurado correctamente.")
            
            # Imprimir la cantidad equivalente en BTC una vez configurada la cantidad en USDT
            self.imprimir_cantidad_equivalente_en_btc()

        except ValueError:
            print("Error: Por favor ingrese un valor numérico válido.")

    def imprimir_cantidad_equivalente_en_btc(self):
        if self.cantidad_operacion_usdt is not None:
            self.cantidad_btc = self.convertir_usdt_a_btc()
            if self.cantidad_btc is not None:
                print(f"La cantidad de USDT ingresada es equivalente a {self.cantidad_btc } BTC.")

    def revision_ordenes_y_obtener_moneda(self):
        # Definir las funciones a ejecutar en hilos separados
        def verificar_estado_orden():
            self.verificar_estado_orden()

        def datos_iniciales():
            self.datos_iniciales()
            
        # Crear los hilos para ejecutar las funciones
        thread_verificar_estado_orden = threading.Thread(target=verificar_estado_orden)
        thread_datos_iniciales = threading.Thread(target=datos_iniciales)

        # Iniciar los hilos
        thread_verificar_estado_orden.start()
        thread_datos_iniciales.start()

        # Esperar a que ambos hilos terminen antes de continuar
        thread_verificar_estado_orden.join()
        thread_datos_iniciales.join()

    def realizar_compra(self, symbol):
        try:
            # Verificar el número de órdenes abiertas para el símbolo
            if self.cantidad_ordenes.get(symbol, 0) >= 3:
                # print(f"Se encontraron {self.cantidad_ordenes[symbol]} órdenes abiertas para {symbol}. No se realizarán más compras.")
                return

            order_book_data = self.actualizar_libro_ordenes(symbol)
            if not order_book_data or 'order_book' not in order_book_data or 'porcentaje_compra' not in order_book_data:
                print(f"Error al obtener los datos del libro de órdenes para {symbol}.")
                return

            order_book = order_book_data['order_book']
            porcentaje_compra = order_book_data['porcentaje_compra']

            # Verificar si hay suficientes órdenes de venta y compra
            if not order_book['asks'] or len(order_book['asks']) < 1 or not order_book['bids'] or len(order_book['bids']) < 1:
                print(f"No se han podido obtener suficientes datos del order book del símbolo {symbol}.")
                return

            nearest_sell_price = float(order_book['asks'][0][0])
            nearest_sell_quantity = float(order_book['asks'][0][1])

            # Verificar si ha habido alguna venta en nearest_sell_price en las últimas 24 horas
            try:
                trades = self.client.get_recent_trades(symbol=symbol)
                now = int(time.time() * 1000)
                twenty_four_hours_ago = now - 24 * 60 * 60 * 1000

                recent_sell_trades = [
                    trade for trade in trades
                    if float(trade['price']) == nearest_sell_price and trade['time'] >= twenty_four_hours_ago and not trade['isBuyerMaker']
                ]
            
            except BinanceAPIException as api_error:
                print(f"Error al obtener transacciones recientes para {symbol}: {api_error.message} (código de error: {api_error.code})")
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()
                error_msg = f"Error al obtener transacciones recientes para {symbol}: {api_error.message} (código de error: {api_error.code})\n"
                self.guardar_error(error_msg)
                return
            except Exception as general_error:
                print(f"Error inesperado al obtener transacciones recientes para {symbol}: {general_error}")
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()
                error_msg = f"Error inesperado al obtener transacciones recientes para {symbol}: {general_error}\n"
                self.guardar_error(error_msg)
                return

            summary_5m = self.analizar_grafico_5m(symbol)
            tendencia_5m = self.identificar_tendencia(summary_5m, symbol)

            if not recent_sell_trades and tendencia_5m != 'ALCISTA':
                print(f"No hubo ventas en {nearest_sell_price} para {symbol} en las últimas 24 horas y la tendencia de 5min no es alcista, no se abrirá la orden de compra.")
                return

            # Obtener la cantidad de monedas acumuladas únicamente en el nivel 1
            buy_quantity = sum(float(item[1]) for item in order_book['bids'][:1])
            sell_quantity = sum(float(item[1]) for item in order_book['asks'][:1])

            # Obtener la cantidad de monedas acumuladas únicamente en el nivel 2
            buy_quantity_level_2 = sum(float(item[1]) for item in order_book['bids'][:2]) - buy_quantity
            sell_quantity_level_2 = sum(float(item[1]) for item in order_book['asks'][:2]) - sell_quantity

            # Obtener la cantidad de monedas acumuladas únicamente en el nivel 3
            buy_quantity_level_3 = sum(float(item[1]) for item in order_book['bids'][:3]) - sum(float(item[1]) for item in order_book['bids'][:2])
            sell_quantity_level_3 = sum(float(item[1]) for item in order_book['asks'][:3]) - sum(float(item[1]) for item in order_book['asks'][:2])

            # Obtener el precio con la orden de compra más cercana
            compra_price = float(order_book['bids'][0][0])

            # Convertir la cantidad de USDT a BTC
            cantidad_btc = self.cantidad_btc

            # Dividir la cantidad de BTC entre el precio de compra para obtener la cantidad exacta de monedas a comprar
            cantidad_exacta = cantidad_btc / compra_price

            # Obtener información de intercambio para el símbolo
            exchange_info = self.client.get_symbol_info(symbol)
            lot_size_filter = next(f for f in exchange_info['filters'] if f['filterType'] == 'LOT_SIZE')

            min_qty = float(lot_size_filter['minQty'])
            max_qty = float(lot_size_filter['maxQty'])
            step_size = float(lot_size_filter['stepSize'])

            # Ajustar la cantidad a comprar para cumplir con LOT_SIZE
            cantidad_exacta = max(min_qty, min(cantidad_exacta, max_qty))

            # Ajustar la cantidad exacta al step_size permitido
            cantidad_exacta = math.floor(cantidad_exacta / step_size) * step_size

            if cantidad_exacta < min_qty or cantidad_exacta > max_qty:
                print(f"La cantidad ajustada {cantidad_exacta} está fuera de los límites permitidos para {symbol}.")
                return

            nearest_buy_order = next((item for item in order_book['bids'] if float(item[0]) >= compra_price), None)
            nearest_sell_order = next((item for item in order_book['asks'] if float(item[0]) >= compra_price), None)

            if nearest_buy_order is None or nearest_sell_order is None:
                print(f"No se encontraron órdenes de compra/venta cercanas para {symbol}.")
                return

            nearest_sell_price = min(float(order[0]) for order in order_book['asks'])
            nearest_buy_price = float(nearest_buy_order[0])

            # Si la cantidad de venta es mayor que la de compra, no proceder
            if buy_quantity < 0.90 * sell_quantity:
                return  # Pasa al siguiente símbolo sin ejecutar más código para este símbolo

            # Redondear la cantidad al número de decimales permitido
            cantidad_exacta_rounded = round(cantidad_exacta, 8)

            # Almacenar la cantidad exacta de monedas compradas en "self.quantity"
            self.quantity = cantidad_exacta_rounded

            vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

            if avg_buy_price != 0.00000000 and compra_price >= avg_buy_price + 0.00000005:
                print(f"El precio de compra de {symbol} a {compra_price} está a 5 puntos por encima del precio de compra medio: {avg_buy_price}, no se abrirá una orden de compra.")
                return

            if not self.error_1003 and not self.saldo_insuficiente:
                # Verifica si la cantidad acumulada es menor o igual al 10% de buy_quantity
                if not self.resistencias_mercado(symbol, nearest_sell_price, order_book):
                    # Aquí realizamos la compra real
                    order_price_formatted = "{:.8f}".format(compra_price)  # Formatear el precio con hasta 8 decimales
                    order = self.client.create_order(
                        symbol=symbol,
                        side='BUY',
                        type='LIMIT',
                        timeInForce='GTC',
                        quantity=cantidad_exacta_rounded,
                        price=order_price_formatted  # Utilizar el precio de compra formateado como cadena
                    )

                    print(f"Orden de compra de {symbol} realizada exitosamente al precio de {order_price_formatted}.")

        except (TypeError, BinanceAPIException, Exception) as e:
            if isinstance(e, TypeError) and "cannot unpack non-iterable NoneType object" in str(e):
                print(f"Error al realizar la orden de compra con {symbol}: {e}. Saltando este par")
                return
            elif isinstance(e, BinanceAPIException) and e.code == -1003:
                print("Error -1003: Demasiado peso utilizado para llamar a la API. Deteniendo el programa para evitar un posible baneo de la API.")
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()
                self.error_1003 = True  # Detener el programa
            elif isinstance(e, Exception) and "insufficient balance" in str(e).lower():
                self.saldo_insuficiente = True
                print("Saldo insuficiente. Esperando a tener saldo.")
            else:
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()
                print(f"Error al realizar la orden de compra con {symbol}: {e}")
                error_msg = f"Error al realizar la orden de compra con {symbol}: {e}\n"
                self.guardar_error(error_msg)

    def monitorear_compra(self, symbol, order_price, order_book, order_id=None, order_quantity=None):
        try:
            print(f"Iniciando monitoreo de la orden de compra de {symbol} a {order_price} BTC")

            vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

            while not self.error_1003:
                # Actualizar los tiempos de espera según la cantidad total de órdenes
                self.definir_tiempo_espera()
                tiempo_espera = self.tiempo_espera['tiempo_monitoreo']
                time.sleep(tiempo_espera)

                order_book_data = self.actualizar_libro_ordenes(symbol)
                if order_book_data is None:
                    print("Order book vacío, reintentando obtenerlo.")
                    continue

                order_book = order_book_data['order_book']
                porcentaje_compra = order_book_data['porcentaje_compra']

                # Filtrar las órdenes abiertas por el símbolo dado
                order_active = False
                for order in self.estado_ordenes:
                    if order['orderId'] == order_id:
                        order_active = True
                        break

                if not order_active:
                    print(f"Orden de compra de {symbol} finalizada.")
                    pygame.mixer.music.load('compra_finalizada.mp3')
                    pygame.mixer.music.play()

                    vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

                    # Calcula el volumen de compra (bids)
                    bids = order_book['bids']
                    buy_volume = sum([float(bid[1]) for bid in bids])
                    # Calcula el volumen de venta (asks)
                    asks = order_book['asks']
                    sell_volume = sum([float(ask[1]) for ask in asks])

                    # Añadir el volumen de compra en la sección guardar_datos_compra
                    datos_compra = {
                        "Par": symbol,
                        "Order ID": order_id,
                        "VWAP Compra": vwap,
                        "Precio Compra": order_price,
                        "Volumen Compra": buy_volume,
                        "Volumen Venta": sell_volume,
                        "Precio Medio Compra Ultimas 24h": avg_buy_price,
                        "Precio Medio Venta Ultimas 24h": avg_sell_price,
                        "Order Book Compra": order_book
                    }

                    self.guardar_datos_compra(datos_compra)  # Almacenar los datos de compra

                    self.realizar_venta(symbol, order_price, order_book, order_id)
                    break

                order_status = None
                for order in self.estado_ordenes:
                    if order['orderId'] == order_id:
                        order_status = order['status']
                        break

                # Obtener el análisis del gráfico
                summary_1D = self.analizar_grafico_1D(symbol)
                tendencia_1D = self.identificar_tendencia(summary_1D, symbol)
                summary_4H = self.analizar_grafico_4H(symbol)
                tendencia_4H = self.identificar_tendencia(summary_4H, symbol)
                summary_5m = self.analizar_grafico_5m(symbol)
                tendencia_5m = self.identificar_tendencia(summary_5m, symbol)

                if tendencia_1D == 'BAJISTA' and tendencia_4H == 'BAJISTA': # se verifica si la tendencia de 1h es bajista, entonces no se opera
                    print(f"Se ha detectado una tendencia diaria y horaria bajista, eliminando la orden de compra de {symbol}")
                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                    self.saldo_insuficiente = False
                    break

                if tendencia_5m == 'BAJISTA': # se verifica si la tendencia de 5m es bajista, entonces no se opera
                    print(f"Se ha detectado una tendencia de 5 minutos bajista, eliminando la orden de compra de {symbol}")
                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                    self.saldo_insuficiente = False
                    break
                
                if porcentaje_compra < 25:
                    print(f"Eliminando la orden de compra de {symbol} ya que la cantidad de monedas puestas en ordenes de compra es inferior al 25% en comparacion a la cantidad de monedas en ordenes de venta.")
                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                    self.saldo_insuficiente = False
                    break
                
                if self.porcentaje_positivo_24h < 40 and self.condiciones_operar == False:
                    print(f"Se ha un cambio bajista de tendencia y un porcentaje de monedas con porcentaje positivo inferior al 40% y no hay indicios de una posible subida. Cancelando orden de compra de {symbol}")
                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                    self.saldo_insuficiente = False
                    break
                
                # Obtener las órdenes de compra y venta más cercanas al precio de la orden actual
                nearest_buy_order = next((item for item in order_book['bids'] if float(item[0]) >= order_price), None)
                nearest_sell_order = next((item for item in order_book['asks'] if float(item[0]) >= order_price), None)

                # Verificar si las órdenes más cercanas no son None antes de acceder a sus elementos
                if nearest_buy_order is not None and nearest_sell_order is not None:
                    # Calcular las cantidades de monedas en las órdenes más cercanas
                    buy_quantity = float(nearest_buy_order[1])
                    sell_quantity = float(nearest_sell_order[1])

                    nearest_sell_price = min(float(order[0]) for order in order_book['asks'])
                    nearest_buy_price = float(nearest_buy_order[0])
                    # Obtener la cantidad de monedas acumuladas únicamente en el nivel 2
                    buy_quantity_level_2 = sum(float(item[1]) for item in order_book['bids'][:2]) - buy_quantity

                    # Calculamos los límites inferior y superior
                    lower_limit = 0.20 * sell_quantity
                    upper_limit = 0.50 * sell_quantity # En veradd esto da igual

                    # Verificar cantidad de monedas
                    if order_price == nearest_buy_price and buy_quantity <= 0.05 * sell_quantity and tendencia_5m == 'BAJISTA' or tendencia_4H == 'BAJISTA':
                        if self.detectar_soporte_mercado(symbol, order_price - 0.00000001, order_book) or buy_quantity_level_2 > 2 * sell_quantity: 
                            print(f"Se prevé una bajada para la orden de compra de {symbol} a {order_price}, pero se detectó soporte de mercado en {order_price - 0.00000001}. Continuando sin cambios.")
                        else:
                            print(f"Ajustando orden de compra de {symbol} en el precio de {order_price} a {order_price - 0.00000001} ya que la cantidad de monedas acumuladas en la orden de compra más cercana es muy baja.")
                            self.client.cancel_order(symbol=symbol, orderId=order_id)
                            order_price_formatted = "{:.8f}".format(order_price - 0.00000001)
                            self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                            pygame.mixer.music.load('ajustando_compra.mp3')
                            pygame.mixer.music.play()
                            break

                    if order_price == round(nearest_buy_price - 0.00000001, 8) and buy_quantity >= buy_quantity_level_2 and buy_quantity >= lower_limit:
                        print(f"Se ha determinado que la orden de compra de {symbol} a {order_price} no va a completarse, ajustando orden de compra a {nearest_buy_price}.")
                        self.client.cancel_order(symbol=symbol, orderId=order_id)
                        order_price_formatted = "{:.8f}".format(nearest_buy_price)
                        self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                        pygame.mixer.music.load('ajustando_compra.mp3')
                        pygame.mixer.music.play()
                        break

                    if order_price < round(nearest_buy_price - 0.00000001, 8):
                        if buy_quantity >= buy_quantity_level_2:
                            print(f"El precio de {symbol} ha bajado más de dos puntos, reajustando orden de compra a {nearest_buy_price}.")
                            self.client.cancel_order(symbol=symbol, orderId=order_id)
                            order_price_formatted = "{:.8f}".format(nearest_buy_price)
                            self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                            pygame.mixer.music.load('ajustando_compra.mp3')
                            pygame.mixer.music.play()
                            break
                        else:
                            if self.detectar_soporte_mercado(symbol, order_price - 0.00000001, order_book):
                                print(f"El precio de {symbol} ha bajado más de dos puntos y se ha detectado un soporte de mercado a {order_price - 0.00000001}, reajustando orden de compra a {nearest_buy_price}.")
                                self.client.cancel_order(symbol=symbol, orderId=order_id)
                                order_price_formatted = "{:.8f}".format(nearest_buy_price)
                                self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                                pygame.mixer.music.load('ajustando_compra.mp3')
                                pygame.mixer.music.play()
                                break
                            else:
                                print(f"El precio de {symbol} ha bajado más de dos puntos, reajustando orden de compra a {nearest_buy_price - 0.00000001}.")
                                self.client.cancel_order(symbol=symbol, orderId=order_id)
                                order_price_formatted = "{:.8f}".format(nearest_buy_price - 0.00000001)
                                self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                                pygame.mixer.music.load('ajustando_compra.mp3')
                                pygame.mixer.music.play()
                                break

                    if nearest_sell_price != (nearest_buy_price + 0.00000001) and (self.detectar_soporte_mercado(symbol, nearest_buy_price, order_book) or buy_quantity > 2 * sell_quantity):
                        if order_price < avg_buy_price + 0.00000005:
                            # Verificar si ha habido alguna venta en nearest_sell_price en las últimas 24 horas
                            try:
                                trades = self.client.get_recent_trades(symbol=symbol)
                                now = int(time.time() * 1000)
                                twenty_four_hours_ago = now - 24 * 60 * 60 * 1000

                                recent_sell_trades = [
                                    trade for trade in trades
                                    if float(trade['price']) == nearest_sell_price and trade['time'] >= twenty_four_hours_ago and not trade['isBuyerMaker']
                                ]
                            
                            except BinanceAPIException as api_error:
                                print(f"Error al obtener transacciones recientes para {symbol}: {api_error.message} (código de error: {api_error.code})")
                                pygame.mixer.music.load('error.mp3')
                                pygame.mixer.music.play()
                                error_msg = f"Error al obtener transacciones recientes para {symbol}: {api_error.message} (código de error: {api_error.code})\n"
                                self.guardar_error(error_msg)
                                return
                            except Exception as general_error:
                                print(f"Error inesperado al obtener transacciones recientes para {symbol}: {general_error}")
                                pygame.mixer.music.load('error.mp3')
                                pygame.mixer.music.play()
                                error_msg = f"Error inesperado al obtener transacciones recientes para {symbol}: {general_error}\n"
                                self.guardar_error(error_msg)
                                return

                            if not recent_sell_trades and tendencia_5m == 'ALCISTA' or recent_sell_trades:
                                if self.cantidad_ordenes.get(symbol, 0) >= 3:
                                    print(f"Se encontraron {self.cantidad_ordenes[symbol]} órdenes abiertas para {symbol}. Reajustando orden de compra al precio de {nearest_buy_price}.")
                                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                                else:
                                    print(f"Abriendo orden de compra de {symbol} a {order_price + 0.00000001} BTC.")

                                order_price_formatted = "{:.8f}".format(order_price + 0.00000001)
                                try:
                                    new_order = self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                                    pygame.mixer.music.load('ajustando_compra.mp3')
                                    pygame.mixer.music.play()
                                    time.sleep(2)

                                    new_order_id = new_order['orderId']
                                    new_order_status = self.client.get_order(symbol=symbol, orderId=new_order_id)['status']

                                    if new_order_status == 'FILLED':
                                        print(f"Orden de compra de {symbol} finalizada.")
                                        pygame.mixer.music.load('compra_finalizada.mp3')
                                        pygame.mixer.music.play()

                                        vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

                                        # Calcula el volumen de compra (bids) y venta (asks)
                                        buy_volume = sum([float(bid[1]) for bid in order_book['bids']])
                                        sell_volume = sum([float(ask[1]) for ask in order_book['asks']])

                                        datos_compra = {
                                            "Par": symbol,
                                            "Order ID": order_id,
                                            "VWAP Compra": vwap,
                                            "Precio Compra": order_price,
                                            "Volumen Compra": buy_volume,
                                            "Volumen Venta": sell_volume,
                                            "Precio Medio Compra Ultimas 24h": avg_buy_price,
                                            "Precio Medio Venta Ultimas 24h": avg_sell_price,
                                            "Order Book Compra": order_book
                                        }

                                        self.guardar_datos_compra(datos_compra)  # Almacenar los datos de compra
                                        self.realizar_venta(symbol, order_price + 0.00000001, order_book, order_id)
                                        break
                                    else:
                                        break

                                except BinanceAPIException as e:
                                    if e.code == -2010:
                                        order_price_formatted = "{:.8f}".format(order_price + 0.00000001)
                                        print(f"Fondos insuficientes para realizar la orden de compra a {order_price_formatted} con {symbol}. Cancelando la orden actual y reintentando.")
                                        self.client.cancel_order(symbol=symbol, orderId=order_id)
                                        new_order = self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                                        pygame.mixer.music.load('ajustando_compra.mp3')
                                        pygame.mixer.music.play()
                                        time.sleep(2)

                                        new_order_id = new_order['orderId']
                                        new_order_status = self.client.get_order(symbol=symbol, orderId=new_order_id)['status']

                                        if new_order_status == 'FILLED':
                                            print(f"Orden de compra de {symbol} finalizada.")
                                            pygame.mixer.music.load('compra_finalizada.mp3')
                                            pygame.mixer.music.play()

                                            vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

                                            # Calcula el volumen de compra (bids) y venta (asks)
                                            buy_volume = sum([float(bid[1]) for bid in order_book['bids']])
                                            sell_volume = sum([float(ask[1]) for ask in order_book['asks']])

                                            datos_compra = {
                                                "Par": symbol,
                                                "Order ID": order_id,
                                                "VWAP Compra": vwap,
                                                "Precio Compra": order_price,
                                                "Volumen Compra": buy_volume,
                                                "Volumen Venta": sell_volume,
                                                "Precio Medio Compra Ultimas 24h": avg_buy_price,
                                                "Precio Medio Venta Ultimas 24h": avg_sell_price,
                                                "Order Book Compra": order_book
                                            }

                                            self.guardar_datos_compra(datos_compra)  # Almacenar los datos de compra
                                            self.realizar_venta(symbol, order_price + 0.00000001, order_book, order_id)
                                            break
                                        else:
                                            break
                                    else:
                                        raise e

                    if order_price == round(nearest_buy_price - 0.00000001, 8) and buy_quantity >= lower_limit:
                        if not self.resistencias_mercado(symbol, nearest_sell_price, order_book):
                            if self.cantidad_ordenes.get(symbol, 0) >= 3:
                                print(f"Se encontraron {self.cantidad_ordenes[symbol]} órdenes abiertas para {symbol}. Reajustando orden de compra al precio de {nearest_buy_price}.")
                                self.client.cancel_order(symbol=symbol, orderId=order_id)
                                order_price_formatted = "{:.8f}".format(order_price + 0.00000001)
                                self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                                pygame.mixer.music.load('ajustando_compra.mp3')
                                pygame.mixer.music.play()
                                break
                            else:
                                try:
                                    print(f"Abriendo orden de compra de {symbol} a {order_price + 0.00000001} BTC.")
                                    order_price_formatted = "{:.8f}".format(order_price + 0.00000001)
                                    self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                                    pygame.mixer.music.load('ajustando_compra.mp3')
                                    pygame.mixer.music.play()
                                    break
                                except BinanceAPIException as e:
                                    if e.code == -2010:
                                        print(f"Error -2010: Fondos insuficientes para realizar la orden de compra a {order_price_formatted} con {symbol}. Cancelando la orden actual y reintentando.")
                                        self.client.cancel_order(symbol=symbol, orderId=order_id)
                                        time.sleep(1)
                                        order_price_formatted = "{:.8f}".format(order_price + 0.00000001)
                                        self.client.create_order(symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=order_quantity, price=order_price_formatted)
                                        pygame.mixer.music.load('ajustando_compra.mp3')
                                        pygame.mixer.music.play()
                                        break
                                    else:
                                        raise e

        except BinanceAPIException as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            if e.code == -1003:
                print("Error -1003: Demasiado peso utilizado para llamar a la API. Deteniendo el programa para evitar un posible baneo de la API.")
                self.error_1003 = True  # Detener el programa
            else:
                print(f"Error al monitorear la orden de compra de {symbol}: {e}")
                error_msg = f"Error al monitorear la orden de compra de {symbol}: {e}\n"
                self.guardar_error(error_msg)

    def realizar_venta(self, symbol, order_price, order_book, order_id=None):
        if not self.error_1003:
            try:
                # Obtener el balance de la moneda subyacente (primer símbolo del par)
                base_asset = symbol.replace('BTC', '')
                balance_info = self.client.get_asset_balance(asset=base_asset)
                available_balance = float(balance_info['free'])

                # Redondear hacia abajo el saldo disponible y convertirlo a entero
                order_quantity = int(math.floor(available_balance))

                if order_quantity <= 0:
                    print(f"No hay suficiente saldo disponible para vender en {symbol}.")
                    self.saldo_insuficiente = False
                    return

                tick_size = self.client.get_symbol_info(symbol)['filters'][0]['tickSize']
                tick_size = float(tick_size)

                precio_venta = round(order_price + tick_size, 8)

                # Redondear al valor más cercano
                precio_venta_rounded = round(precio_venta / tick_size) * tick_size
                # Ajustar el precio de venta si es igual al precio de compra
                if precio_venta_rounded == order_price:
                    precio_venta = round(precio_venta_rounded + tick_size, 8)

                precio_venta_str = "{:.8f}".format(precio_venta)  # Formatear el precio de venta como una cadena

                print(f"Vendiendo al precio de {str(precio_venta)}.")

                # Se realiza la orden de venta con la cantidad redondeada
                order = self.client.create_order(
                    symbol=symbol,
                    side='SELL',
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=order_quantity,
                    price=precio_venta_str  # Utilizar el precio de venta formateado como cadena
                )
                print(f"Orden de venta de {symbol} realizada exitosamente.")
                return

            except Exception as e:
                if isinstance(e, BinanceAPIException):
                    if e.code == -2010:
                        # Ignorar el error si es "Account has insufficient balance for requested action"
                        print(f"Balance insuficiente de {symbol}, orden finalizada.")
                        self.saldo_insuficiente = False
                        return
                    elif e.code == -1013:
                        # Manejar el error de "Filter failure: NOTIONAL"
                        print(f"Error de filtro: NOTIONAL para {symbol}, orden finalizada.")
                        return
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()    
                print(f"Error al realizar la orden de venta de {symbol}: {e}")
                error_msg = f"Error al realizar la orden de venta de {symbol}: {e}\n"
                self.guardar_error(error_msg)

    def monitorear_venta(self, symbol, venta_price, sell_quantity, order_id=None, order_book=None):
        try:
            venta_ajustada = False
            Perdidas = False  # Inicializar la variable Perdidas como False por defecto
            print(f"Iniciando monitoreo de la orden de venta de {symbol} a {venta_price} BTC")

            vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

            while not self.error_1003:
                self.definir_tiempo_espera()
                tiempo_espera = self.tiempo_espera['tiempo_monitoreo']
                time.sleep(tiempo_espera)

                order_book_data = self.actualizar_libro_ordenes(symbol)
                if order_book_data is None:
                    print("Order book vacío, reintentando obtenerlo.")
                    continue

                order_book = order_book_data['order_book']
                porcentaje_compra = order_book_data['porcentaje_compra']

                # Obtener el análisis del gráfico
                summary_5m = self.analizar_grafico_5m(symbol)
                tendencia_5m = self.identificar_tendencia(summary_5m, symbol)
                summary_4H = self.analizar_grafico_4H(symbol)
                tendencia_4H = self.identificar_tendencia(summary_4H, symbol)

                #print(f"self.porcentaje_positivo_24h: {self.porcentaje_positivo_24h} self.cambio_positivo: {self.cambio_positivo} symbol: {symbol} tendencia_4H: {tendencia_4H} tendencia_5m: {tendencia_5m}")

                # Filtrar las órdenes abiertas por el símbolo dado
                order_active = False
                for order in self.estado_ordenes:
                    if order['orderId'] == order_id:
                        order_active = True
                        break

                if not order_active:
                    if venta_ajustada:
                        break
                    else:
                        print(f"Orden de {symbol} finalizada.")

                        vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

                        # Calcula el volumen de compra (bids)
                        bids = order_book['bids']
                        buy_volume = sum([float(bid[1]) for bid in bids])
                        # Calcula el volumen de venta (asks)
                        asks = order_book['asks']
                        sell_volume = sum([float(ask[1]) for ask in asks])

                        # Verificar si el order_id está en self.perdidas
                        if order_id in self.perdidas:
                            Perdidas = True
                            self.perdidas.remove(order_id)
                        else:
                            Perdidas = False

                        # Añadir el volumen de compra en la sección guardar_datos_compra
                        datos_venta = {
                            "Par": symbol,
                            "Orden con perdidas": Perdidas,
                            "Order ID": order_id,
                            "VWAP Compra": vwap,
                            "Precio Compra": venta_price,
                            "Volumen Compra": buy_volume,
                            "Volumen Venta": sell_volume,
                            "Precio Medio Compra Ultimas 24h": avg_buy_price,
                            "Precio Medio Venta Ultimas 24h": avg_sell_price,
                            "Order Book Compra": order_book
                        }

                        self.guardar_datos_venta(datos_venta)  # Almacenar los datos de venta
                        self.quantity = None
                        self.saldo_insuficiente = False
                        pygame.mixer.music.load('venta_finalizada.mp3')
                        pygame.mixer.music.play()
                        break

                order_status = None
                for order in self.estado_ordenes:
                    if order['orderId'] == order_id:
                        order_status = order['status']
                        break

                # Obtener el precio de venta actual
                current_sell_price = float(order_book['asks'][0][0])

                # Encontrar el precio con órdenes de compra más cercano al precio de venta actual
                nearest_buy_price = None
                for order in order_book['bids']:
                    if float(order[0]) >= current_sell_price:
                        nearest_buy_price = float(order[0])
                        break

                if nearest_buy_price is None:
                    # Si no se encuentra ningún precio con órdenes de compra mayor o igual al precio de venta actual, se toma el precio más alto disponible
                    nearest_buy_price = float(order_book['bids'][0][0])

                # Buscar las órdenes de compra a ese precio
                nearest_buy_orders = [order for order in order_book['bids'] if float(order[0]) == nearest_buy_price]

                # Sumar la cantidad de monedas en las órdenes de compra a ese precio
                total_buy_quantity = sum(float(order[1]) for order in nearest_buy_orders)

                # Obtener el precio con órdenes de venta más cercano al precio actual de venta
                nearest_sell_price = min(float(order[0]) for order in order_book['asks'])
                nearest_sell_orders = [order for order in order_book['asks'] if float(order[0]) == nearest_sell_price]

                # Sumar la cantidad de monedas en las órdenes de venta a ese precio
                total_sell_quantity = sum(float(order[1]) for order in nearest_sell_orders)

                # Ajustar valores de "X" basado en las condiciones actuales
                x_sell_quantity, x_sell_price = self.ajustar_valores_x(self.cambio_positivo, self.porcentaje_positivo_24h, porcentaje_compra, tendencia_4H, tendencia_5m, avg_sell_price, venta_price)

                if (
                    (float(total_sell_quantity) > x_sell_quantity * float(total_buy_quantity) and 
                     float(venta_price) >= round(nearest_sell_price + x_sell_price, 8) and
                     float(venta_price) != nearest_sell_price
                     ) 
                ):                    
                    # Verificar el valor nominal antes de cancelar la orden actual y crear una nueva
                    notional = sell_quantity * nearest_sell_price
                    if notional < self.min_notional:
                        print(f"Error: el valor nominal de la nueva orden ({notional}) es menor que el mínimo requerido ({self.min_notional}). No se ajustará la orden de venta.")
                        continue

                    # Cancelar la orden de venta
                    self.client.cancel_order(symbol=symbol, orderId=order_id)

                    nearest_sell_price_str = "{:.8f}".format(nearest_sell_price)
                    # Abrir una nueva orden de venta al valor con órdenes de compra más cercano al valor con órdenes de venta
                    new_order = self.client.create_order(symbol=symbol, side='SELL', type='LIMIT', quantity=sell_quantity, price=nearest_sell_price_str, timeInForce='GTC')
                    
                    # Obtener el nuevo order_id
                    new_order_id = new_order['orderId']
                    
                    print(f"Ajustando orden de venta de {symbol} a {venta_price}. Vendiendo al precio de venta mas cercano {nearest_sell_price_str} ya que el precio ha bajado. x_sell_quantity: {x_sell_quantity} x_sell_price: {x_sell_price}")
                    pygame.mixer.music.load('ajustando_venta.mp3')
                    pygame.mixer.music.play()
                    venta_ajustada = True
                    
                    # Añadir el nuevo order_id a self.perdidas
                    self.perdidas.append(new_order_id)
                    break

                if (
                    float(total_buy_quantity) < x_sell_quantity * float(total_sell_quantity) and
                    float(venta_price) == round(nearest_sell_price + x_sell_price, 8) and
                    float(venta_price) == nearest_sell_price
                ):                    
                    # Verificar soporte de mercado
                    if self.detectar_soporte_mercado(symbol, (nearest_buy_price - 0.00000001), order_book):
                        print(f"Se prevé una bajada en la orden de venta de {symbol} a {venta_price}, pero se detectó soporte de mercado en {nearest_buy_price - 0.00000001}. Continuando sin cambios.")
                    else:
                        # Verificar el valor nominal antes de cancelar la orden actual y crear una nueva
                        notional = sell_quantity * nearest_buy_price
                        if notional < self.min_notional:
                            print(f"Error: el valor nominal de la nueva orden ({notional}) es menor que el mínimo requerido ({self.min_notional}). No se ajustará la orden de venta.")
                            continue

                        # Cancelar la orden de venta
                        self.client.cancel_order(symbol=symbol, orderId=order_id)

                        nearest_buy_price_str = "{:.8f}".format(nearest_buy_price)
                        # Abrir una nueva orden de venta al valor con órdenes de compra más cercano al valor con órdenes de venta
                        new_order = self.client.create_order(symbol=symbol, side='SELL', type='LIMIT', quantity=sell_quantity, price=nearest_buy_price_str, timeInForce='GTC')
                        print(f"Ajustando orden de venta de {symbol} a {venta_price}. Vendiendo al precio de compra mas cercano {nearest_buy_price_str} ya que se prevé una bajada. x_sell_quantity: {x_sell_quantity} x_sell_price: {x_sell_price}")
                        pygame.mixer.music.load('ajustando_venta.mp3')
                        pygame.mixer.music.play()
                        break

                if float(venta_price) > float(venta_price + 0.00000005):
                    # Cancelar la orden de venta
                    self.client.cancel_order(symbol=symbol, orderId=order_id)

                    nearest_buy_price_str = "{:.8f}".format(nearest_buy_price)
                    # Abrir una nueva orden de venta al valor con órdenes de compra más cercano al valor con órdenes de venta
                    new_order = self.client.create_order(symbol=symbol, side='SELL', type='LIMIT', quantity=sell_quantity, price=nearest_buy_price_str, timeInForce='GTC')
                    print(f"Ajustando orden de venta de {symbol} a {venta_price}. Vendiendo al precio de compra mas cercano {nearest_buy_price_str} ya que el precio de la moneda ha bajado sustancialmente.")
                    pygame.mixer.music.load('ajustando_venta.mp3')
                    pygame.mixer.music.play()
                    break

        except BinanceAPIException as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            if e.code == -1003:
                print("Error -1003: Demasiado peso utilizado para llamar a la API. Deteniendo el programa para evitar un posible baneo de la API.")
                self.error_1003 = True  # Detener el programa
            else:
                print(f"Error al monitorear la orden de venta de {symbol}: {e}")
                error_msg = f"Error al monitorear la orden de venta de {symbol}: {e}\n"
                self.guardar_error(error_msg)

    def ajustar_valores_x(self, cambio_positivo, porcentaje_positivo_24h, porcentaje_compra, tendencia_4H, tendencia_5m, avg_sell_price, venta_price):
        # Inicialización de valores base de "X"
        x_sell_quantity = 0.40
        x_sell_price = 0.000000025
        valores_permitidos = [0.00000000, 0.00000001, 0.00000002, 0.00000003, 0.00000004, 0.00000005]

        def redondeo_personalizado(valor):
            # Buscar el valor más cercano en valores_permitidos
            valor_redondeado = min(valores_permitidos, key=lambda x: abs(x - valor))
            return valor_redondeado

        if avg_sell_price != 0.00000000:
            # Ajuste basado en porcentaje_positivo_24h
            if porcentaje_positivo_24h < 30 and cambio_positivo or cambio_positivo == None:
                x_sell_quantity += 0.04
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000005)
            elif porcentaje_positivo_24h < 30 and not cambio_positivo:
                x_sell_quantity += 0.08
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000010)
            elif 30 <= porcentaje_positivo_24h < 43 and cambio_positivo or cambio_positivo == None:
                x_sell_quantity += 0.03
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000003)
            elif 30 <= porcentaje_positivo_24h < 43 and not cambio_positivo:
                x_sell_quantity += 0.06
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000007)
            elif 43 <= porcentaje_positivo_24h <= 57 and cambio_positivo or cambio_positivo == None:
                x_sell_quantity -= 0.04
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000004)
            elif 43 <= porcentaje_positivo_24h <= 57 and not cambio_positivo:
                x_sell_quantity += 0.04
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000004)
            elif 57 < porcentaje_positivo_24h <= 70 and cambio_positivo or cambio_positivo == None:
                x_sell_quantity -= 0.06
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000007)
            elif 57 < porcentaje_positivo_24h <= 70 and not cambio_positivo:
                x_sell_quantity -= 0.03
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000003)
            elif porcentaje_positivo_24h > 70 and cambio_positivo or cambio_positivo == None:
                x_sell_quantity -= 0.08
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000010)
            elif porcentaje_positivo_24h > 70 and not cambio_positivo:
                x_sell_quantity -= 0.04
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000005)

            # Ajuste basado en tendencia_4H
            if tendencia_4H == 'BAJISTA':
                x_sell_quantity += 0.07
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000007)
            elif tendencia_4H == 'LATERAL':
                x_sell_quantity -= 0.04
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000004)
            elif tendencia_4H == 'ALCISTA':
                x_sell_quantity -= 0.07
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000007)

            if self.condiciones_operar:
                x_sell_quantity -= 0.05
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000005)
            else:
                x_sell_quantity += 0.05
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000005)

            # Ajuste basado en tendencia_5m
            if tendencia_5m == 'BAJISTA':
                x_sell_quantity += 0.03
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000004)
            else:
                x_sell_quantity -= 0.03
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000004)

            # Ajuste basado en porcentaje_compra
            if porcentaje_compra > 66:
                x_sell_quantity -= 0.02
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000003)
            elif 44 <= porcentaje_compra <= 66:
                pass  # Sin cambios
            elif porcentaje_compra < 44:
                x_sell_quantity += 0.02
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000003)

            if venta_price >= avg_sell_price:
                x_sell_quantity -= 0.02
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000003)
            elif venta_price == avg_sell_price - 0.00000001:
                x_sell_quantity += 0.01
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000001)
            elif venta_price == avg_sell_price - 0.00000002:
                x_sell_quantity += 0.02
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000002)
            elif venta_price == avg_sell_price - 0.00000003:
                x_sell_quantity += 0.03
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000003)
            elif venta_price <= avg_sell_price - 0.00000004:
                x_sell_quantity += 0.04
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000004)
        else:
            # Ajuste basado en porcentaje_positivo_24h
            if porcentaje_positivo_24h < 30 and cambio_positivo:
                x_sell_quantity += 0.05
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000010)
            elif porcentaje_positivo_24h < 30 and not cambio_positivo:
                x_sell_quantity += 0.10
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000005)
            elif 30 <= porcentaje_positivo_24h < 43 and cambio_positivo:
                x_sell_quantity += 0.04
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000008)
            elif 30 <= porcentaje_positivo_24h < 43 and not cambio_positivo:
                x_sell_quantity += 0.08
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000004)
            elif 43 <= porcentaje_positivo_24h <= 57 and cambio_positivo:
                x_sell_quantity -= 0.05
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000005)
            elif 43 <= porcentaje_positivo_24h <= 57 and not cambio_positivo:
                x_sell_quantity += 0.05
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000005)
            elif 57 < porcentaje_positivo_24h <= 70 and cambio_positivo:
                x_sell_quantity -= 0.08
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000004)
            elif 57 < porcentaje_positivo_24h <= 70 and not cambio_positivo:
                x_sell_quantity -= 0.04
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000008)
            elif porcentaje_positivo_24h > 70 and cambio_positivo:
                x_sell_quantity -= 0.10
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000005)
            elif porcentaje_positivo_24h > 70 and not cambio_positivo:
                x_sell_quantity -= 0.05
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000010)

            # Ajuste basado en tendencia_4H
            if tendencia_4H == 'BAJISTA':
                x_sell_quantity += 0.08
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000008)
            else:
                x_sell_quantity -= 0.08
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000008)

            if self.condiciones_operar:
                x_sell_quantity -= 0.06
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000006)
            else:
                x_sell_quantity += 0.06
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000006)

            # Ajuste basado en tendencia_5m
            if tendencia_5m == 'BAJISTA':
                x_sell_quantity += 0.05
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000004)
            else:
                x_sell_quantity -= 0.05
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000004)

            # Ajuste basado en porcentaje_compra
            if porcentaje_compra > 66:
                x_sell_quantity -= 0.04
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000003)
            elif 44 <= porcentaje_compra <= 66:
                pass  # Sin cambios
            elif porcentaje_compra < 44:
                x_sell_quantity += 0.04
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000003)

        # Limitar valores de "X" a los rangos especificados y aplicar valores mínimos
        x_sell_quantity = max(0.15, min(x_sell_quantity, 0.65))
        x_sell_price = min(valores_permitidos, key=lambda x: abs(x - x_sell_price))

        return x_sell_quantity, x_sell_price

    def analizar_grafico_1D(self, symbol):
        exchanges = ["BINANCE", "HITBTC", "COINBASE", "KRAKEN", "BITFINEX"]
        summary = None

        for exchange in exchanges:
            while True:
                try:
                    # Saltar pares que no están en la web
                    if symbol == "MDXBTC" or symbol == "QUICKBTC" or symbol == "BETABTC":
                        summary = {'RECOMMENDATION': 'LATERAL'}
                        return summary

                    # Saltar la combinación BINANCE y ALPACABTC
                    if symbol == "ALPACABTC" and exchange == "BINANCE":
                        break

                    handler = TA_Handler(
                        symbol=symbol,
                        screener="crypto",
                        exchange=exchange,
                        interval=Interval.INTERVAL_1_DAY
                    )
                    analysis = handler.get_analysis()
                    if analysis is not None and hasattr(analysis, 'summary'):
                        summary = analysis.summary
                        if summary:
                            return summary
                    break  # Salir del bucle si no hay errores y se obtiene el análisis

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    print(f"Error de conexión al analizar gráfico 1D para {symbol} en {exchange}: {e}. Reintentando en 5 segundos...")
                    sleep(5)  # Esperar 5 segundos antes de reintentar
                except Exception as e:
                    print(f"Error al analizar gráfico 1D para {symbol} en {exchange}: {e}")
                    error_msg = f"Error al analizar gráfico 1D para {symbol} en {exchange}: {e}\n"
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
                    self.guardar_error(error_msg)
                    break  # Salir del bucle para errores no relacionados con la conexión

        if summary is None:
            # Establecer summary a un valor específico que identificar_tendencia pueda manejar
            summary = {'RECOMMENDATION': 'LATERAL'}
            
        return summary

    def analizar_grafico_4H(self, symbol):
        exchanges = ["BINANCE", "HITBTC", "COINBASE", "KRAKEN", "BITFINEX"]
        summary = None

        for exchange in exchanges:
            while True:
                try:
                    # Saltar pares que no están en la web
                    if symbol == "MDXBTC" or symbol == "QUICKBTC" or symbol == "BETABTC":
                        summary = {'RECOMMENDATION': 'LATERAL'}
                        return summary

                    # Saltar la combinación BINANCE y ALPACABTC
                    if symbol == "ALPACABTC" and exchange == "BINANCE":
                        break

                    handler = TA_Handler(
                        symbol=symbol,
                        screener="crypto",
                        exchange=exchange,
                        interval=Interval.INTERVAL_4_HOURS
                    )
                    analysis = handler.get_analysis()
                    if analysis is not None and hasattr(analysis, 'summary'):
                        summary = analysis.summary
                        if summary:
                            return summary
                    break  # Salir del bucle si no hay errores y se obtiene el análisis

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    print(f"Error de conexión al analizar gráfico 4H para {symbol} en {exchange}: {e}. Reintentando en 5 segundos...")
                    sleep(5)  # Esperar 5 segundos antes de reintentar
                except Exception as e:
                    print(f"Error al analizar gráfico 4H para {symbol} en {exchange}: {e}")
                    error_msg = f"Error al analizar gráfico 4H para {symbol} en {exchange}: {e}\n"
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
                    self.guardar_error(error_msg)
                    break  # Salir del bucle para errores no relacionados con la conexión

        if summary is None:
            # Establecer summary a un valor específico que identificar_tendencia pueda manejar
            summary = {'RECOMMENDATION': 'LATERAL'}
            
        return summary

    def analizar_grafico_5m(self, symbol):
        exchanges = ["BINANCE", "HITBTC", "COINBASE", "KRAKEN", "BITFINEX"]
        summary = None

        for exchange in exchanges:
            while True:
                try:
                    # Saltar pares que no están en la web
                    if symbol == "MDXBTC" or symbol == "QUICKBTC" or symbol == "BETABTC":
                        summary = {'RECOMMENDATION': 'LATERAL'}
                        return summary

                    # Saltar la combinación BINANCE y ALPACABTC
                    if symbol == "ALPACABTC" and exchange == "BINANCE":
                        break

                    handler = TA_Handler(
                        symbol=symbol,
                        screener="crypto",
                        exchange=exchange,
                        interval=Interval.INTERVAL_5_MINUTES
                    )
                    analysis = handler.get_analysis()
                    if analysis is not None and hasattr(analysis, 'summary'):
                        summary = analysis.summary
                        if summary:
                            return summary
                    break  # Salir del bucle si no hay errores y se obtiene el análisis

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    print(f"Error de conexión al analizar gráfico 5m para {symbol} en {exchange}: {e}. Reintentando en 5 segundos...")
                    sleep(5)  # Esperar 5 segundos antes de reintentar
                except Exception as e:
                    print(f"Error al analizar gráfico 5m para {symbol} en {exchange}: {e}")
                    error_msg = f"Error al analizar gráfico 5m para {symbol} en {exchange}: {e}\n"
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
                    self.guardar_error(error_msg)
                    break  # Salir del bucle para errores no relacionados con la conexión

        if summary is None:
            # Establecer summary a un valor específico que identificar_tendencia pueda manejar
            summary = {'RECOMMENDATION': 'LATERAL'}
            
        return summary

    def identificar_tendencia(self, summary, symbol):
        recommendation = summary.get('RECOMMENDATION', 'NEUTRAL')
        tendencia = 'LATERAL'
        if recommendation == 'BUY':
            tendencia = 'ALCISTA'
        elif recommendation == 'SELL':
            tendencia = 'BAJISTA'
        
        # print(f"Tendencia identificada para {symbol}: {tendencia}")
        return tendencia

    def datos_iniciales(self):
        porcentaje_requerido = 45  # Puedes ajustar este valor al porcentaje deseado
        porcentaje_para_no_operar = 55  # Nuevo umbral para dejar de operar
        self.porcentaje_positivo_24h_anterior = None  # Inicializar como None
        self.historico_porcentaje_24h = []  # Inicializar la lista para almacenar valores históricos
        dejo_de_operar = False  # Variable para saber si el sistema ha dejado de operar

        while True:
            while not self.error_1003:
                self.symbols_list = []
                positive_symbols = 0
                total_symbols = 0

                # Implementar el mecanismo de reintento para la llamada a la API
                while True:
                    try:
                        response = requests.get("https://api.binance.com/api/v3/ticker/24hr")
                        response.raise_for_status()  # Levantar un HTTPError para respuestas malas (4xx y 5xx)
                        tickers = response.json()
                        break  # Salir del bucle si se obtienen los datos con éxito
                    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                        print(f"Error de conexión: {e}. Reintentando en 5 segundos...")
                        sleep(5)  # Esperar 5 segundos antes de reintentar
                    except requests.exceptions.RequestException as e:
                        print(f"Ocurrió un error al obtener datos iniciales: {e}")
                        error_msg = f"Ocurrió un error al obtener datos iniciales: {e}\n"
                        pygame.mixer.music.load('error.mp3')
                        pygame.mixer.music.play()
                        self.guardar_error(error_msg)
                        return  # Salir del método para errores no recuperables

                for ticker in tickers:
                    symbol = ticker.get('symbol', '')
                    try:
                        price = float(ticker.get('lastPrice', 0))
                        price_change_percent = float(ticker.get('priceChangePercent', 0))
                        quote_volume = float(ticker.get('quoteVolume', 0))
                    except ValueError as e:
                        print(f"Error al convertir los datos del ticker a float: {e}")
                        continue

                    # Primera verificación
                    if symbol.endswith('BTC') and price <= 0.00000333 and quote_volume >= 0.1:
                        total_symbols += 1  # Contamos este símbolo en el total

                        # Almacenar los valores de price_change_percent por símbolo
                        if symbol not in self.symbols_price_changes:
                            self.symbols_price_changes[symbol] = []
                        self.symbols_price_changes[symbol].append(price_change_percent)
                        if len(self.symbols_price_changes[symbol]) > 111:
                            self.symbols_price_changes[symbol].pop(0)

                        # Verificación del cambio de precio positivo en las últimas 24 horas
                        if price_change_percent > 0:
                            positive_symbols += 1

                # Calcular el porcentaje de símbolos con un cambio de precio positivo en las últimas 24 horas
                if total_symbols > 0:
                    self.porcentaje_positivo_24h_anterior = self.porcentaje_positivo_24h  # Guardar el valor anterior
                    self.porcentaje_positivo_24h = round((positive_symbols / total_symbols) * 100, 2)
                else:
                    self.porcentaje_positivo_24h_anterior = self.porcentaje_positivo_24h  # Guardar el valor anterior
                    self.porcentaje_positivo_24h = 0

                # Definir los umbrales para detectar cambios significativos
                thresholds = list(range(0, 101, 4))

                # Verificar si hubo un cambio positivo significativo
                if self.cambio_positivo is None:
                    if self.porcentaje_positivo_24h_anterior is not None:
                        if self.porcentaje_positivo_24h != self.porcentaje_positivo_24h_anterior:
                            self.cambio_positivo = self.porcentaje_positivo_24h > self.porcentaje_positivo_24h_anterior

                # Verificar si hubo un cambio positivo significativo
                if self.porcentaje_positivo_24h_anterior is not None:
                    cambio_positivo = any(
                        self.porcentaje_positivo_24h_anterior < threshold < self.porcentaje_positivo_24h
                        for threshold in thresholds
                    )

                    # Verificar si hubo un cambio negativo significativo
                    cambio_negativo = any(
                        self.porcentaje_positivo_24h_anterior > threshold > self.porcentaje_positivo_24h
                        for threshold in thresholds
                    )

                    # Asignar el valor a self.cambio_positivo
                    if cambio_positivo:
                        self.cambio_positivo = True
                    elif cambio_negativo:
                        self.cambio_positivo = False
                    else:
                        self.cambio_positivo = self.cambio_positivo  # Mantener el valor anterior si no hubo cambios significativos

                aumento_significativo = False  # Inicializar como False en cada iteración
                bajada_significativa = False  # Inicializar la nueva variable como False en cada iteración

                # Verificar si positive_symbols < (total_symbols * self.porcentaje_requerido / 100)
                if positive_symbols < (total_symbols * porcentaje_requerido / 100):
                    # Encontrar el valor mínimo en el historial
                    if self.historico_porcentaje_24h:
                        valor_minimo = min(self.historico_porcentaje_24h)
                        diferencia = self.porcentaje_positivo_24h - valor_minimo
                        aumento_significativo = diferencia >= 12
                        bajada_significativa = diferencia <= -12  # Verificar si la diferencia es igual o menor a -15

                    # Añadir el valor actual al historial después de la verificación
                    self.historico_porcentaje_24h.append(self.porcentaje_positivo_24h)

                    # Mantener la lista con un máximo de 111 valores (equivalente a 2h)
                    if len(self.historico_porcentaje_24h) > 111:
                        self.historico_porcentaje_24h.pop(0)
                else:
                    # Si no se cumple la condición, borrar todos los datos
                    self.historico_porcentaje_24h.clear()

                # Verificar si el porcentaje ha subido a más de porcentaje_para_no_operar y luego ha caído por debajo
                if self.porcentaje_positivo_24h > porcentaje_para_no_operar:
                    dejo_de_operar = True

                if self.porcentaje_positivo_24h < porcentaje_requerido:
                    dejo_de_operar = False

                if dejo_de_operar and self.porcentaje_positivo_24h < porcentaje_para_no_operar:
                    print(f"El porcentaje de monedas positivas ha caído por debajo del {porcentaje_para_no_operar}%, no se abrirán nuevas órdenes.")
                    self.condiciones_operar = False
                    time.sleep(65)  # Esperar 65 segundos antes de volver a iniciar el proceso
                    continue

                # Verificar si positive_symbols < (total_symbols * self.porcentaje_requerido / 100) y si no ha habido un aumento significativo
                if positive_symbols < (total_symbols * porcentaje_requerido / 100) and not aumento_significativo:
                    # Verificar si hay un aumento positivo del 1.5% o más en el 50% o más de las monedas
                    symbols_with_positive_jumps = 0
                    for symbol, changes in self.symbols_price_changes.items():
                        if len(changes) > 1:
                            last_change = changes[-1]
                            positive_jumps = [change for change in changes[:-1] if last_change - change >= 1.5]
                            if len(positive_jumps) >= len(changes[:-1]) / 2:
                                symbols_with_positive_jumps += 1

                if self.ordenes:
                    if self.saldo_insuficiente:
                        print("Saldo insuficiente. Esperando a tener saldo.")
                        time.sleep(65)  # Esperar 65 segundos antes de volver a iniciar el proceso
                        continue  # Saltar todo el código y volver a iniciar el bucle

                    self.condiciones_operar = True
                    porcentaje_minimo_requerido = total_symbols * porcentaje_requerido / 100
                    positive_jump_threshold = len(self.symbols_price_changes) / 2

                    # Verificar si la cantidad de símbolos con porcentaje positivo es menor al porcentaje requerido
                    if positive_symbols < porcentaje_minimo_requerido:
                        if not aumento_significativo and symbols_with_positive_jumps < positive_jump_threshold:
                            print(f"No se ha detectado un aumento del 12% de monedas con porcentaje positivo, la cantidad de monedas con un cambio de precio positivo en las últimas 24 horas es del {self.porcentaje_positivo_24h}% y no llega al porcentaje mínimo del {porcentaje_requerido}%, y no se ha detectado un aumento del 1.5% en la mitad o más de las monedas.")
                            self.condiciones_operar = False
                        elif not aumento_significativo and symbols_with_positive_jumps >= positive_jump_threshold:
                            print(f"Se ha detectado un aumento del 1.5% en el 50% o más de las monedas, procediendo con órdenes de compra.")
                            self.condiciones_operar = True
                        elif aumento_significativo:
                            print(f"Se ha detectado un aumento igual o mayor al 12% en la cantidad de monedas con porcentaje positivo en las últimas 24h.")
                            self.condiciones_operar = True

                    if bajada_significativa:
                        print(f"Se ha detectado una bajada igual o mayor al 12% en la cantidad de monedas con porcentaje positivo en las últimas 24h, No se abrirán nuevas órdenes de compra.")
                        self.condiciones_operar = False

                    if not self.condiciones_operar:
                        time.sleep(65)  # Esperar 65 segundos antes de volver a iniciar el proceso
                        continue  # Saltar todo el código y volver a iniciar el bucle

                    # Verificar si el 50% o más de los valores almacenados ha bajado igual o más de un 1%
                    symbols_with_drops = 0
                    for symbol, changes in self.symbols_price_changes.items():
                        if len(changes) > 1:
                            last_change = changes[-1]
                            drops = [change for change in changes[:-1] if change - last_change >= 1]
                            if len(drops) >= len(changes[:-1]) / 2:
                                symbols_with_drops += 1

                    if symbols_with_drops >= len(self.symbols_price_changes) / 2:
                        print("Se ha detectado una bajada del 1% en más del 50% de los valores históricos, no se abrirán nuevas órdenes de compra.")
                        self.condiciones_operar = False
                        time.sleep(65)  # Esperar 65 segundos antes de volver a iniciar el proceso
                        continue

                    for ticker in tickers:
                        symbol = ticker.get('symbol', '')
                        try:
                            price = float(ticker.get('lastPrice', 0))
                            price_change_percent = float(ticker.get('priceChangePercent', 0))
                            quote_volume = float(ticker.get('quoteVolume', 0))
                        except ValueError as e:
                            continue

                        # Verificar si los datos son válidos y cumplen con las condiciones
                        if symbol.endswith('BTC') and symbol != 'ZKBTC' and 0.00000050 <= price <= 0.00000200 and quote_volume >= 0.1:  # 333
                            # Verificar si el cambio de precio en las últimas 24 horas está dentro del rango especificado (-6% a 10%)
                            if -6 <= price_change_percent <= 10:
                                # Obtener el análisis del gráfico
                                summary_4H = self.analizar_grafico_4H(symbol)
                                tendencia_4H = self.identificar_tendencia(summary_4H, symbol)
                                summary_5m = self.analizar_grafico_5m(symbol)
                                tendencia_5m = self.identificar_tendencia(summary_5m, symbol)
                                if tendencia_4H != 'BAJISTA' and tendencia_5m == 'ALCISTA':
                                    self.symbols_list.append(symbol)

                    # Utilizar ThreadPoolExecutor para controlar los hilos
                    with ThreadPoolExecutor(max_workers=max(1, len(self.symbols_list))) as executor:
                        # Iniciar un hilo para cada símbolo en self.symbols_list
                        futures = [executor.submit(self.realizar_compra, symbol) for symbol in self.symbols_list]
                        # Esperar a que todos los hilos hayan terminado
                        for future in futures:
                            try:
                                future.result()  # Esto asegura que el hilo actual haya terminado antes de continuar
                            except Exception as e:
                                pygame.mixer.music.load('error.mp3')
                                pygame.mixer.music.play()
                                print(f"Error en la ejecución del hilo: {e}")

                time.sleep(65)  # Esperar 65 segundos antes de volver a iniciar el proceso

    def convertir_usdt_a_btc(self):
        try:
            # Define la URL de la API de Binance para el precio de BTCUSDT
            api_url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"

            # Realizar la solicitud GET a la API con un tiempo de espera de 10 segundos
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()  # Esto generará una excepción para códigos de estado HTTP 4xx/5xx
            response_data = response.json()

            # Verificar si la respuesta contiene el precio de BTCUSDT
            if 'price' in response_data:
                # Obtén el precio de BTCUSDT del mensaje
                precio_btcusdt = float(response_data['price'])

                # Calcular la cantidad de BTC equivalente a la cantidad de USDT ingresada
                cantidad_btc = self.cantidad_operacion_usdt / precio_btcusdt

                self.min_qty_btc = (self.cantidad_operacion_usdt - 0.5) / precio_btcusdt

                # Redondear la cantidad de BTC a 8 decimales si no es None
                if cantidad_btc is not None:
                    cantidad_btc = round(cantidad_btc, 8)

                # Devolver la cantidad de BTC calculada
                return cantidad_btc
            else:
                print("Error: No se pudo obtener el precio de BTCUSDT")
                return None

        except requests.exceptions.Timeout:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print("Error: La solicitud a la API de Binance excedió el tiempo de espera")
            return None
        except requests.exceptions.RequestException as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al convertir USDT a BTC: {e}")
            return None

    def actualizar_libro_ordenes(self, symbol):
        if not self.error_1003:
            base_url = 'https://api.binance.com'  # Base URL for Binance API
            for intento in range(5):
                try:
                    # Envoltorio para manejar el timeout
                    response = self.client._request(method='get', uri=f'{base_url}/api/v3/depth', params={'symbol': symbol, 'limit': 10}, signed=False, timeout=10)
                    order_book = response  # Directly use the response as it is already a dictionary
                    
                    buy_orders = order_book['bids']
                    sell_orders = order_book['asks']

                    buy_volume = sum(float(order[1]) for order in buy_orders)
                    sell_volume = sum(float(order[1]) for order in sell_orders)
                    
                    total_volume = buy_volume + sell_volume
                    porcentaje_compra = (buy_volume / total_volume) * 100 if total_volume != 0 else 0

                    return {
                        "order_book": order_book,
                        "porcentaje_compra": porcentaje_compra
                    }
                except BinanceAPIException as e:
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
                    if e.code == -1003:
                        print("Error -1003: Demasiado peso utilizado para llamar a la API. Deteniendo el programa para evitar un posible baneo de la API.")
                        self.error_1003 = True  # Detener el programa
                        return None
                    else:
                        # print(f"Error al actualizar el libro de órdenes para {symbol}: {e}. Reintentando en {2 ** intento} segundos...")
                        time.sleep(2 ** intento)  # Backoff exponencial
                except RequestException as e:
                    # print(f"Error de red al actualizar el libro de órdenes para {symbol}: {e}. Reintentando en {2 ** intento} segundos...")
                    time.sleep(2 ** intento)  # Backoff exponencial

            print(f"Error al actualizar el libro de órdenes para {symbol} después de múltiples intentos.")
            error_msg = f"Error al actualizar el libro de órdenes para {symbol} después de múltiples intentos.\n"
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            self.guardar_error(error_msg)
            return None

    def verificar_estado_orden_individual(self, symbol, order_id):
        if self.orden_compra == True:
            time.sleep(self.tiempo_espera['tiempo_verificar_ordenes_individuales_compra'])
        else:
            time.sleep(self.tiempo_espera['tiempo_verificar_ordenes_individuales_venta'])

        try:
            if symbol is None or order_id is None:
                print("Los argumentos 'symbol' y 'order_id' no pueden ser None.")
                return None

            order_status_completo = self.client.get_order(symbol=symbol, orderId=order_id)
            threading.Thread(target=self.conteo_order_status).start()

            # print(f"order_status de {symbol}: {order_status['status']}")
            order_status =  order_status_completo['status']
            return order_status

        except ccxt.base.errors.InvalidOrder as e:
            print(f"Error al verificar el estado de la orden: {e}")
            return None

    def verificar_estado_orden(self):
        with self.lock:
            while not self.error_1003:
                # Esperar según el tiempo definido
                self.definir_tiempo_espera()
                tiempo_espera = self.tiempo_espera['tiempo_verificar_ordenes_grupales']
                time.sleep(tiempo_espera)
                try:
                    open_orders = self.client.get_open_orders()
                    self.estado_ordenes = open_orders
                    self.total_ordenes = len(open_orders)

                    # Reiniciar el conteo de órdenes abiertas por símbolo
                    self.cantidad_ordenes = {}

                    for order in open_orders:
                        symbol = order['symbol']
                        # Incrementar el conteo de órdenes abiertas para el símbolo
                        if symbol not in self.cantidad_ordenes:
                            self.cantidad_ordenes[symbol] = 0
                        self.cantidad_ordenes[symbol] += 1

                        order_id = order['orderId']
                        # Verificar si el order_id ya está siendo monitoreado
                        hilo_compra_activo = any(
                            thread.name == f"monitorear_compra_{order_id}" for thread in threading.enumerate()
                        )
                        hilo_venta_activo = any(
                            thread.name == f"monitorear_venta_{order_id}" for thread in threading.enumerate()
                        )
                        
                        if not hilo_compra_activo and not hilo_venta_activo:
                            # Agregar el order_id al registro de monitoreo
                            self.order_ids_in_monitoring.add(order_id)

                            # Verificar si es una orden de compra o venta
                            order_price = float(order['price'])
                            order_quantity = float(order['origQty'])

                            if order['side'] == 'BUY':
                                # Orden de compra
                                order_book_data = self.actualizar_libro_ordenes(symbol)
                                order_book = order_book_data['order_book']
                                threading.Thread(target=self.monitorear_compra, args=(symbol, order_price, order_book, order_id, order_quantity), name=f"monitorear_compra_{order_id}").start()
                            elif order['side'] == 'SELL':
                                # Orden de venta
                                order_book_data = self.actualizar_libro_ordenes(symbol)
                                order_book = order_book_data['order_book']
                                threading.Thread(target=self.monitorear_venta, args=(symbol, order_price, order_quantity, order_id, order_book), name=f"monitorear_venta_{order_id}").start()

                    # Obtener balances
                    balances = self.client.get_account()['balances']

                    # Filtrar balances con "free" > 0.0
                    balances_filtrados = [balance for balance in balances if float(balance['free']) > 0.0]

                    for balance in balances_filtrados:
                        asset = balance['asset']
                        free = float(balance['free'])
                        symbol = f"{asset}BTC"  # Par BTC

                        # Verificación final del activo y símbolo
                        if asset not in ['BTC', 'USDT', 'QSP', 'POA', 'WPR', 'DLT'] and symbol in self.pares_btc:
                            try:
                                # Obtener el precio actual en BTC
                                max_retries = 5
                                for attempt in range(max_retries):
                                    try:
                                        avg_price = float(self.client.get_avg_price(symbol=symbol)['price'])
                                        break
                                    except requests.exceptions.ReadTimeout:
                                        if attempt < max_retries - 1:
                                            time.sleep(2)  # Esperar 2 segundos antes de reintentar
                                        else:
                                            print('Se alcanzó el número máximo de reintentos. No se pudo obtener el precio promedio.')
                                            pygame.mixer.music.load('error.mp3')
                                            pygame.mixer.music.play()
                                            raise

                                value_in_btc = free * avg_price

                                if value_in_btc >= self.min_qty_btc:  # Verificar si el valor en BTC es mayor al mínimo
                                    asset_open_orders = [order for order in open_orders if order['symbol'] == symbol and order['side'] == 'SELL']

                                    if asset_open_orders:
                                        order_book_data = self.actualizar_libro_ordenes(symbol)
                                        order_book = order_book_data['order_book']
                                        # Obtener el precio más bajo de las órdenes de venta existentes
                                        min_sell_price = min(float(order['price']) for order in asset_open_orders)
                                        sell_price = min_sell_price - 0.00000001
                                    else:
                                        order_book_data = self.actualizar_libro_ordenes(symbol)
                                        order_book = order_book_data['order_book']
                                        # No hay órdenes de venta disponibles, buscar en el historial de operaciones
                                        historial = self.obtener_historial_operaciones(symbol)
                                        if historial:
                                            # Filtrar por órdenes de compra y obtener la última orden de compra
                                            compras = [trade for trade in historial if trade['isBuyer']]
                                            if compras:
                                                ultima_compra = max(compras, key=lambda x: x['time'])
                                                sell_price = float(ultima_compra['price'])
                                            else:
                                                print(f"No se encontraron órdenes de compra en el historial para {symbol}. No se puede abrir una orden de venta.")
                                                pygame.mixer.music.load('error.mp3')
                                                pygame.mixer.music.play()
                                                continue  # Continuar con el siguiente balance si no hay órdenes de compra en el historial
                                        else:
                                            print(f"No se pudo obtener el historial de operaciones para {symbol}. No se puede abrir una orden de venta.")
                                            pygame.mixer.music.load('error.mp3')
                                            pygame.mixer.music.play()
                                            continue  # Continuar con el siguiente balance si no se pudo obtener el historial de operaciones

                                    # Ejecutar la orden de venta en un nuevo hilo
                                    threading.Thread(target=self.realizar_venta, args=(symbol, sell_price, order_book)).start()
                                    print(f"Intentando abrir una orden de venta para {asset} a {sell_price + 0.00000001}")

                            except BinanceAPIException as e:
                                if e.code == -1121:
                                    pygame.mixer.music.load('error.mp3')
                                    pygame.mixer.music.play()
                                    print(f"Símbolo inválido: {symbol}")

                except (BinanceAPIException, requests.exceptions.ReadTimeout, Exception) as e:
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
                    if isinstance(e, BinanceAPIException) and e.code == -1003:
                        print("Error -1003: Demasiado peso utilizado para llamar a la API. Deteniendo el programa para evitar un posible baneo de la API.")
                        self.error_1003 = True  # Detener el programa
                    else:
                        print(f"Error al verificar el estado de las órdenes: {e}")
                        error_msg = f"Error al verificar el estado de las órdenes: {e}\n"
                        pygame.mixer.music.load('error.mp3')
                        pygame.mixer.music.play()
                        self.guardar_error(error_msg)

    def obtener_historial_operaciones(self, symbol):
        try:
            historial = self.client.get_my_trades(symbol=symbol)
            return historial
        except BinanceAPIException as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al obtener el historial de operaciones para {symbol}: {e}")
            return []

    def get_btc_balance(self):
        try:
            if self.client is None:
                print("Por favor, configure las credenciales de la API antes de usar esta función.")
                return None
            
            # Obtener el saldo de la cuenta para BTC
            account_info = self.client.get_account()
            for balance in account_info['balances']:
                if balance['asset'] == 'BTC':
                    return float(balance['free'])
            
            print("No se pudo encontrar el saldo de BTC en la cuenta.")
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            return None
        
        except Exception as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al obtener el saldo de BTC: {e}")
            return None

    def obtener_minima_cantidad_usdt(self):
        try:
            if self.client is None:
                print("Por favor, configure las credenciales de la API antes de usar esta función.")
                return None

            # Obtener el filtro de cantidad mínima de la exchange
            exchange_info = self.client.get_exchange_info()
            filters = exchange_info['symbols'][0]['filters']

            # Buscar el filtro de cantidad mínima en BTC
            min_qty_filter = next((f for f in filters if f['filterType'] == 'LOT_SIZE'), None)
            if min_qty_filter:
                min_qty_btc = float(min_qty_filter['minQty'])
                # Obtener el precio actual de BTCUSDT
                ticker = self.client.get_symbol_ticker(symbol="BTCUSDT")
                precio_btcusdt = float(ticker['price'])
                # Calcular la cantidad mínima en USDT
                min_qty_usdt = min_qty_btc * precio_btcusdt
                return min_qty_usdt
            else:
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()
                raise ValueError("No se pudo obtener el filtro de cantidad mínima.")

        except Exception as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al obtener la cantidad mínima permitida por Binance: {e}")
            raise ValueError("Error al obtener la cantidad mínima permitida por Binance.")

    def configurar_api(self):
        self.api_key = self.entry_api_key.get().strip()
        self.api_secret = self.entry_api_secret.get().strip()
        if self.api_key and self.api_secret:
            try:
                self.client = Client(self.api_key, self.api_secret)
                account_info = self.client.get_account()
                if 'makerCommission' in account_info:
                    self.find_optimal_coins_button.config(state=tk.NORMAL)
                    print("API configurada correctamente")
                    self.save_api_credentials()  # Guardar las credenciales
                else:
                    print("Error: La API Key o el API Secret no son válidos.")
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
            except Exception as e:
                print("Error: La API Key o el API Secret no son válidos.")
        else:
            print("Por favor, ingrese tanto la clave API como el secreto API.")

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
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al detectar la resistencia de mercado para {symbol}: {e}")
            return False

    def detectar_soporte_mercado(self, symbol, venta_price, order_book):
        try:
            # Obtener los precios y volúmenes de compra del libro de órdenes
            bids = order_book['bids']

            bid_venta = None
            bid_below = None

            # Encontrar el bid más cercano al precio de venta
            min_diff = float('inf')  # Inicializamos con un valor grande
            for bid in bids:
                price = float(bid[0])
                quantity = float(bid[1])
                diff = abs(price - venta_price)

                if diff < min_diff:
                    min_diff = diff
                    bid_venta = (price, quantity)

            if bid_venta:
                bid_below_price = bid_venta[0] - 0.00000001
                # Buscar el bid justo por debajo de bid_venta_price
                for bid in bids:
                    price = float(bid[0])
                    quantity = float(bid[1])

                    if price < bid_venta[0]:
                        if bid_below is None or price > bid_below[0]:
                            bid_below = (price, quantity)

            # Verificar si encontramos un bid_below y si la cantidad de bid_venta es 4 veces mayor que la cantidad de bid_below
            if bid_below and bid_venta[1] > 4 * (bid_below[1] if bid_below else 0):
                return True

            else:
                return False

        except Exception as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al detectar el soporte de mercado para {symbol}: {e}")
            return False

    def calcular_datos(self, symbol):
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
                    error_msg = f"Mensaje de error: {response.json()}\n"
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
                    self.guardar_error(error_msg)
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

    def guardar_datos_compra(self, datos):
        try:
            with open(self.nombre_archivo_csv_compra, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=datos.keys())
                if os.stat(self.nombre_archivo_csv_compra).st_size == 0:
                    writer.writeheader()
                writer.writerow(datos)
        except Exception as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al guardar los datos de compra: {e}")

    def guardar_datos_venta(self, datos):
        try:
            with open(self.nombre_archivo_csv_venta, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=datos.keys())
                if os.stat(self.nombre_archivo_csv_venta).st_size == 0:
                    writer.writeheader()
                writer.writerow(datos)
        except Exception as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al guardar los datos de venta: {e}")

    def guardar_error(self, error_msg):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("errores.txt", "a") as file:
                file.write(f"{now}: {error_msg}")
        except Exception as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al guardar el mensaje de error: {e}")

if __name__ == "__main__":
    app = MoneyBotApp()
    app.mainloop()
