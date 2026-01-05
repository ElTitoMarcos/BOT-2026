import os
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.common.exceptions import NoSuchElementException, WebDriverException
import tkinter as tk
from tkinter import scrolledtext, ttk
import webbrowser
import queue
import csv
import os
import math
import threading
import time
import requests
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
        self.saldo_insuficiente = False
        self.error_1003 = False
        self.ultimos_valores = []
        self.symbols_list = []
        self.cantidad_ordenes = {}
        self.min_qty_usdt = 0
        self.min_notional = 0.00000001  # Valor nominal mínimo constante
        self.porcentaje_positivo_24h = None
        self.porcentaje_positivo_24h_anterior = None
        self.cambio_positivo = None
        self.min_qty_btc = 0.0001
        self.pares_btc = []
        self.order_ids_in_monitoring = set()  # Registro de order_id en monitoreo
        self.symbols_price_changes = {}  # Diccionario para almacenar los valores de price_change_percent por símbolo
        self.condiciones_operar = None
        self.cantidad_btc = 0
        self.perdidas = []
        self.simbolos_win = {}
        self.window = None
        self.frame = None
        self.symbols_frame = None
        self.text_area = None
        self.mensaje_operar = "Esperando a obtener información..."
        self.queue = queue.Queue()
        self.entries = {}  # Para mantener referencia a las entradas
        self.usdt_amount_var = 0
        self.free_usdt = 0.00
        self.free_btc = 0.00000000
        self.btc = 0.00000000
        self.estado_ordenes_filtrado = []
        self.previous_estado_ordenes_filtrado = []
        self.usdt_values_cache = {}
        self.simbolos_win_previo = None
        self.open_orders_frame = None  # Inicializa open_orders_frame
        self.morado_orders = {}
        self.modificar = {}
        self.disable_buttons_and_entries = False
        self.driver = {}
        self.symbols_to_skip = set()

        self.api_key = None
        self.api_secret = None

        # Start WhatsApp automation
        self.iniciar_automatizacion_whatsapp()
        # Load API credentials and start the main function
        self.load_api_credentials()
        self.initialize_client()
        self.revision_ordenes_y_obtener_moneda()
        

    def load_api_credentials(self):
        if os.path.exists("api_credentials.txt"):
            with open("api_credentials.txt", "r") as file:
                lines = file.readlines()
                if len(lines) >= 2:
                    self.api_key = lines[0].strip()
                    self.api_secret = lines[1].strip()

    def initialize_client(self):
        if self.api_key and self.api_secret:
            self.client = Client(self.api_key, self.api_secret)
        else:
            print("API Key y/o API Secret no están configurados correctamente.")

    def save_api_credentials(self):
        with open("api_credentials.txt", "w") as file:
            if self.api_key:
                file.write(self.api_key + "\n")
            if self.api_secret:
                file.write(self.api_secret + "\n")

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

    def definir_tiempo_espera(self):
        self.tiempo_espera = {
            "tiempo_realizar_compra": None,
            "tiempo_monitoreo": None,
            "tiempo_verificar_ordenes_individuales_compra": None,
            "tiempo_verificar_ordenes_individuales_venta": None,
            "tiempo_verificar_ordenes_grupales": None
        }

        if self.total_ordenes <= 2:
            self.tiempo_espera["tiempo_monitoreo"] = 1
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 1
        elif self.total_ordenes > 2 and self.total_ordenes <= 8:
            self.tiempo_espera["tiempo_monitoreo"] = 1
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 1
        elif self.total_ordenes > 8 and self.total_ordenes <= 13:
            self.tiempo_espera["tiempo_monitoreo"] = 1.2
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 1
        elif self.total_ordenes > 13 and self.total_ordenes <= 18:
            self.tiempo_espera["tiempo_monitoreo"] = 1.65
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 1
        elif self.total_ordenes > 18 and self.total_ordenes <= 25:
            self.tiempo_espera["tiempo_monitoreo"] = 1.8
            self.tiempo_espera["tiempo_verificar_ordenes_grupales"] = 1
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

    def iniciar_automatizacion_whatsapp(self):
        threading.Thread(target=self.automatizacion_whatsapp).start()

    def iniciar_driver(self):
        options = webdriver.EdgeOptions()
        options.add_argument("user-data-dir=C:/Users/marco/AppData/Local/Microsoft/Edge/User Data")
        options.add_argument("profile-directory=Default")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")

        self.driver = webdriver.Edge(options=options)
        return self.driver

    def abrir_whatsapp_web(self, driver):
        driver.get('https://web.whatsapp.com')
        time.sleep(15)

    def encontrar_chat(self, driver, nombre_chat):
        try:
            chat = driver.find_element(By.XPATH, f'//span[@title="{nombre_chat}"]')
            chat.click()
            return True
        except NoSuchElementException:
            return False

    def obtener_ultimo_mensaje(self, driver):
        try:
            mensajes = driver.find_elements(By.CSS_SELECTOR, 'span.selectable-text.copyable-text span')
            if mensajes:
                return mensajes[-1].text
            else:
                return None
        except NoSuchElementException:
            return None

    def automatizacion_whatsapp(self):
        os.system("taskkill /im msedge.exe /f")

        nombre_del_chat = "Bot-Trading"

        while True:
            try:
                driver = self.iniciar_driver()
                self.abrir_whatsapp_web(driver)

                if not self.encontrar_chat(driver, nombre_del_chat):
                    print(f'No se pudo encontrar el chat con el nombre "{nombre_del_chat}".')
                    driver.quit()
                    continue

                ultimo_mensaje = self.obtener_ultimo_mensaje(driver)

                self.enviar_respuesta(driver, "*Listo*")

                # Start the thread to refresh the page every hour
                threading.Thread(target=self.refrescar_pagina_periodicamente, args=(driver, nombre_del_chat)).start()

                while True:
                    time.sleep(5)
                    nuevo_mensaje = self.obtener_ultimo_mensaje(driver)
                    if nuevo_mensaje and nuevo_mensaje != ultimo_mensaje:
                        print(f'Nuevo mensaje detectado: {nuevo_mensaje}')

                        if re.fullmatch(r'\bMonedas\b', nuevo_mensaje):
                            respuesta = self.generar_respuesta_monedas()
                            self.enviar_respuesta(driver, respuesta)
                            print(f'Respuesta enviada por la palabra "Monedas".')
                        elif re.fullmatch(r'\bInfo\b', nuevo_mensaje):
                            respuesta = self.generar_respuesta_info()
                            self.enviar_respuesta(driver, respuesta)
                            print(f'Respuesta enviada por la palabra "Info".')
                        elif nuevo_mensaje.startswith("Abrir"):
                            self.procesar_y_abrir_ordenes(driver, nuevo_mensaje)
                        elif re.fullmatch(r'\bOrdenes\b', nuevo_mensaje):
                            respuesta = self.generar_respuesta_ordenes()
                            self.enviar_respuesta(driver, respuesta)
                            print(f'Respuesta enviada por la palabra "Ordenes".')
                        elif nuevo_mensaje.startswith("Modificar"):
                            self.procesar_modificar_ordenes(driver, nuevo_mensaje)
                        elif nuevo_mensaje.startswith("Cancelar"):
                            self.procesar_cancelar_ordenes(driver, nuevo_mensaje)
                        else:
                            self.generar_respuesta_cantidad(driver, nuevo_mensaje)

                        ultimo_mensaje = nuevo_mensaje

            except WebDriverException as e:
                print(f'Error con el navegador: {e}')
                if 'no such window' in str(e) or 'disconnected' in str(e):
                    print('La ventana del navegador se ha cerrado. Reiniciando...')
                    driver.quit()
                    continue
            except Exception as e:
                print(f'Ocurrió un error inesperado: {e}')
                driver.quit()
                break

    def refrescar_pagina_periodicamente(self, driver, nombre_del_chat):
        while True:
            time.sleep(1800)  # Wait for one hour
            try:
                driver.refresh()
                print("Página de WhatsApp Web actualizada.")
                time.sleep(15)  # Wait for the page to load
                if not self.encontrar_chat(driver, nombre_del_chat):
                    print(f'No se pudo encontrar el chat con el nombre "{nombre_del_chat}" después de la actualización.')
            except WebDriverException as e:
                print(f"Error al actualizar la página: {e}")

    def procesar_modificar_ordenes(self, driver, mensaje):
        try:
            # Obtener los símbolos del mensaje
            simbolos = mensaje[10:].split(', ')
            modificaciones_realizadas = False
            for simbolo in simbolos:
                simbolo = simbolo.upper() + "BTC"
                
                # Comprobar si el símbolo está en las órdenes filtradas
                simbolo_encontrado = False
                for order in self.estado_ordenes_filtrado:
                    if order['symbol'] == simbolo:
                        simbolo_encontrado = True
                        # Usar toggle_modify_order para modificar self.modificar
                        self.toggle_modify_order(order)
                        modificaciones_realizadas = True
                    
                if not simbolo_encontrado:
                    self.enviar_respuesta(driver, f"*Par {simbolo} no encontrado en las órdenes abiertas.*")
            
            if modificaciones_realizadas:
                self.update_open_orders_frame()
                self.enviar_respuesta(driver, "*Órden/es modificada/s*")
        except Exception as e:
            print(f"Error al procesar las modificaciones de órdenes: {e}")
            self.enviar_respuesta(driver, "*Error al procesar la modificación de órdenes.*")

    def generar_respuesta_monedas(self):
        if not self.simbolos_win:
            return "*No hay monedas disponibles*"

        base_url = "https://www.binance.com/es/trade/"
        respuesta = "*Lista de monedas:*\n"
        ordenes_abiertas = {order['symbol'] for order in self.estado_ordenes_filtrado}

        for symbol, price in sorted(self.simbolos_win.items(), key=lambda item: item[1]):
            formatted_price = int(price * 10**8)
            symbol_without_btc = symbol.replace('BTC', '')
            url = f"{base_url}{symbol_without_btc}_BTC?type=spot"
            respuesta += f"{symbol}: {formatted_price}"
            
            if symbol in ordenes_abiertas:
                respuesta += " *(Orden Abierta)*"
            
            respuesta += f" {url}\n"
        return respuesta

    def generar_respuesta_cantidad(self, driver, mensaje):
        # Detectar el patrón "Cantidad: <número>"
        cantidad_match = re.search(r'Cantidad\s*(\d+)', mensaje)
        if cantidad_match:
            nueva_cantidad = int(cantidad_match.group(1))
            self.cantidad_operacion_usdt = nueva_cantidad
            self.usdt_amount_var = nueva_cantidad
            self.imprimir_cantidad_equivalente_en_btc()
            print(f'Cantidad actualizada: {nueva_cantidad}')
            # Enviar el mensaje con la nueva cantidad
            self.enviar_respuesta(driver, f'*Cantidad actualizada a {nueva_cantidad} USDT*')

    def generar_respuesta_info(self):
        # Verificar si cantidad_operacion_usdt tiene un valor válido
        if self.cantidad_operacion_usdt is None or self.cantidad_operacion_usdt == 0:
            ordenes_a_abrir = 0
        else:
            ordenes_a_abrir = math.floor(self.free_usdt / self.cantidad_operacion_usdt)

        return (f"*Cantidad por operacion: {self.cantidad_operacion_usdt} USDT*\n"
                f"*Abrir ordenes con {self.cantidad_btc} BTC*\n"
                f"*Cantidad de órdenes a abrir: {ordenes_a_abrir}*\n"
                f"*Balance Total BTC: {self.btc:.8f}*\n"
                f"*Balance Disponible en USDT: {self.free_usdt:.2f}*\n"
                f"*Cantidad de monedas positivas: {self.porcentaje_positivo_24h}%*\n"
                f"*Mensaje informativo: {self.mensaje_operar}*")

    def generar_respuesta_ordenes(self):
        estado_ordenes_filtrado = self.estado_ordenes_filtrado if self.estado_ordenes_filtrado else []
        respuesta = f"*Órdenes actuales ({self.total_ordenes}):*\n"

        for order in estado_ordenes_filtrado:
            symbol = order['symbol']
            price = float(order['price'])
            side = order['side']
            side_text = "Compra" if side == "BUY" else "*Venta*" if side == "SELL" else "Desconocido"
            order_id = order['orderId']
            orig_qty = round(float(order['origQty']), 1)
            formatted_price = round(price * 10**8)  # Redondear al valor más cercano sin decimales
            usdt_value_per_coin = self.get_usdt_value(order_id, symbol)
            usdt_value = orig_qty * usdt_value_per_coin if usdt_value_per_coin else 0
            morado_text = " *(orden a punto de modificarse)*" if order_id in self.morado_orders else ""

            # Obtener el estado de monitorización
            monitorizando = "Sí" if self.modificar.get(order_id, True) else "*No*"

            respuesta += (f"{symbol} ({side_text}): {formatted_price}, Valor: {usdt_value:.2f} USDT, Monitorizando: {monitorizando} {morado_text}\n")

        return respuesta

    def procesar_y_abrir_ordenes(self, driver, mensaje):
        try:
            # Obtener los símbolos y precios del mensaje
            ordenes = mensaje[6:].split(', ')
            for orden in ordenes:
                simbolo, precio = orden.split()
                simbolo = simbolo.upper() + "BTC"
                # Convertir el precio a 8 decimales
                precio = float(precio) / 10**8
                self.realizar_compra(simbolo, precio)
        except Exception as e:
            print(f"Error al procesar y abrir órdenes: {e}")
            self.enviar_respuesta(driver, "*Error al procesar la orden de compra*")

    def procesar_cancelar_ordenes(self, driver, mensaje):
        try:
            # Obtener los símbolos del mensaje
            simbolos = mensaje[9:].split(', ')
            cancelaciones_realizadas = False
            for simbolo in simbolos:
                simbolo = simbolo.upper() + "BTC"
                
                # Comprobar si el símbolo está en las órdenes filtradas
                simbolo_encontrado = False
                for order in self.estado_ordenes_filtrado:
                    if order['symbol'] == simbolo:
                        simbolo_encontrado = True
                        # Cancelar la orden
                        self.cancelar_orden(order)
                        cancelaciones_realizadas = True
                    
                if not simbolo_encontrado:
                    self.enviar_respuesta(driver, f"*Par {simbolo} no encontrado en las órdenes abiertas*")
            
            if cancelaciones_realizadas:
                self.update_open_orders_frame()
        except Exception as e:
            print(f"Error al procesar la cancelación de órdenes: {e}")
            self.enviar_respuesta(driver, "*Error al procesar la cancelación de órdenes*")

    def enviar_respuesta(self, driver, respuesta):
        try:
            cuadro_texto = driver.find_element(By.XPATH, '//footer//div[@contenteditable="true"][@data-tab="10"]')
            cuadro_texto.click()
            cuadro_texto.send_keys(respuesta + Keys.ENTER)
        except NoSuchElementException:
            print("No se pudo encontrar el cuadro de texto para enviar el mensaje.")

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

            # Actualizar la etiqueta de la cantidad de órdenes a abrir
            self.actualizar_ordenes_a_abrir()

        except ValueError:
            print("Error: Por favor ingrese un valor numérico válido.")

    def actualizar_ordenes_a_abrir(self):
        # Obtener la cantidad de órdenes a abrir dividiendo cantidad_btc entre free_usdt y redondeando a la baja
        if self.free_usdt == 0.00 or self.cantidad_operacion_usdt == None:
            ordenes_a_abrir = 0
        else:
            ordenes_a_abrir = math.floor(self.free_usdt / self.cantidad_operacion_usdt)

        self.label_ordenes_a_abrir.config(text=f"Cantidad de órdenes a abrir: {ordenes_a_abrir}")
        # Actualizar el balance de BTC
        self.label_balance_btc.config(text=f"Balance Total BTC: {self.btc:.8f}")
        self.label_free_usdt.config(text=f"Balance Disponible USDT: {self.free_usdt:.2f}")
        self.label_porcentaje_positivo.config(text=f"Cantidad de monedas positivas: {self.porcentaje_positivo_24h}%")

    def create_usdt_amount_entry(self, parent):
        frame_usdt_amount = tk.Frame(parent)
        frame_usdt_amount.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        tk.Label(frame_usdt_amount, text="Cantidad por Operación (USDT):").grid(row=0, column=0, sticky=tk.W)
        self.entry_usdt_amount = tk.Entry(frame_usdt_amount, textvariable=self.usdt_amount_var)
        self.entry_usdt_amount.grid(row=0, column=1, padx=2)
        tk.Button(frame_usdt_amount, text="Confirmar", command=self.confirmar_cantidad_usdt).grid(row=0, column=2, padx=2)

        self.frame_labels = tk.Frame(frame_usdt_amount)
        self.frame_labels.grid(row=0, column=3, padx=10, pady=5, sticky=tk.W)

        self.label_ordenes_a_abrir = tk.Label(self.frame_labels, text="")
        self.label_ordenes_a_abrir.grid(row=0, column=0, padx=5, sticky=tk.W)

        self.label_balance_btc = tk.Label(self.frame_labels, text=f"Balance Total BTC: {self.btc:.8f}")
        self.label_balance_btc.grid(row=1, column=0, padx=5, sticky=tk.W)

        self.label_free_usdt = tk.Label(self.frame_labels, text=f"Balance Disponible USDT: {self.free_usdt:.2f}")
        self.label_free_usdt.grid(row=2, column=0, padx=5, sticky=tk.W)

        self.label_porcentaje_positivo = tk.Label(self.frame_labels, text=f"Cantidad de monedas positivas: {self.porcentaje_positivo_24h}%")
        self.label_porcentaje_positivo.grid(row=3, column=0, padx=5, sticky=tk.W)

        # Llamar a actualizar_ordenes_a_abrir para obtener el valor correcto desde el principio
        self.actualizar_ordenes_a_abrir()

    def create_small_buttons(self, parent, row, index):
        btn_up = ttk.Button(parent, text="▲", width=2, command=lambda: self.move_order_up(index))
        btn_up.grid(row=row, column=2, padx=2, pady=2, sticky=tk.W)
        btn_down = ttk.Button(parent, text="▼", width=2, command=lambda: self.move_order_down(index))
        btn_down.grid(row=row, column=3, padx=2, pady=2, sticky=tk.W)

    def move_order_up(self, index):
        if index < 0 or index >= len(self.estado_ordenes_filtrado):
            print("Error: Índice fuera de rango al mover orden hacia arriba.")
            return

        order = self.estado_ordenes_filtrado[index]

        if order['side'] == 'BUY' and not self.entry_usdt_amount.get():
            print("Introduce la cantidad de dólares para las órdenes")
            pygame.mixer.music.load('dolares_operacion.mp3')
            pygame.mixer.music.play()
            return

        self.client.cancel_order(symbol=order['symbol'], orderId=order['orderId'])

        price = float(order['price'])

        if order['side'] == 'BUY':
            new_price = price + 0.00000001
            compra_thread = threading.Thread(target=self.realizar_compra, args=(order['symbol'], float(new_price)))
            compra_thread.start()
        elif order['side'] == 'SELL':
            new_price = price - 0.00000001
            venta_thread = threading.Thread(target=self.realizar_venta, args=(order['symbol'], float(new_price)))
            venta_thread.start()

        self.estado_ordenes_filtrado.pop(index)
        self.update_open_orders_frame(self.estado_ordenes_filtrado)

    def move_order_down(self, index):
        if index < 0 or index >= len(self.estado_ordenes_filtrado):
            print("Error: Índice fuera de rango al mover orden hacia abajo.")
            return

        order = self.estado_ordenes_filtrado[index]

        if order['side'] == 'BUY' and not self.entry_usdt_amount.get():
            print("Introduce la cantidad de dólares para las órdenes")
            pygame.mixer.music.load('dolares_operacion.mp3')
            pygame.mixer.music.play()
            return

        self.client.cancel_order(symbol=order['symbol'], orderId=order['orderId'])

        price = float(order['price'])

        if order['side'] == 'BUY':
            new_price = price - 0.00000001
            compra_thread = threading.Thread(target=self.realizar_compra, args=(order['symbol'], float(new_price)))
            compra_thread.start()
        elif order['side'] == 'SELL':
            new_price = price - 0.00000002
            venta_thread = threading.Thread(target=self.realizar_venta, args=(order['symbol'], float(new_price)))
            venta_thread.start()

        self.estado_ordenes_filtrado.pop(index)
        self.update_open_orders_frame(self.estado_ordenes_filtrado)

    def create_symbol_entry(self, row, symbol, formatted_price, symbol_color, label_color):
        label = ttk.Label(self.symbols_frame, text=f"{symbol}: {formatted_price}", foreground=symbol_color, cursor="hand2")
        label.grid(row=row, column=0, sticky=tk.W, pady=2)
        label.bind("<Button-1>", lambda e, symbol=symbol: self.open_link(symbol))

        label_orden = ttk.Label(self.symbols_frame, text="Abrir orden de compra a:", foreground=label_color)
        label_orden.grid(row=row, column=1, padx=5, sticky=tk.W)

        entry_valor = ttk.Entry(self.symbols_frame)
        entry_valor.grid(row=row, column=2, padx=2, sticky=tk.W)

        btn_abrir_orden = ttk.Button(self.symbols_frame, text="Abrir Orden", command=lambda s=symbol, e=entry_valor: self.abrir_orden(s, e.get(), 'BUY'))
        btn_abrir_orden.grid(row=row, column=3, padx=2, pady=2, sticky=tk.W)

        if self.disable_buttons_and_entries:
            entry_valor.config(state='disabled')
            btn_abrir_orden.config(state='disabled')

        self.entries[symbol] = (label, entry_valor, label_orden, btn_abrir_orden)

    def get_usdt_value(self, order_id, symbol):
        try:
            if symbol.endswith('BTC'):
                base_symbol = symbol.replace('BTC', '')
            else:
                base_symbol = base_symbol

            # Verificar si el valor ya está en caché
            if order_id in self.usdt_values_cache:
                return self.usdt_values_cache[order_id]

            response = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={base_symbol}USDT')
            response.raise_for_status()
            data = response.json()
            price = float(data['price'])

            # Guardar el valor en caché usando order_id como clave
            self.usdt_values_cache[order_id] = price

            return price
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"Error fetching USDT value for {symbol}: {e}")
            return None

    def mostrar_monedas(self):
        if self.window is None or not tk.Toplevel.winfo_exists(self.window):
            self.window = tk.Tk()
            self.window.title("Simbolos Win")

            self.frame = ttk.Frame(self.window, padding="10")
            self.frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

            self.label_mensaje_operar = ttk.Label(self.frame, text=self.mensaje_operar, wraplength=500)
            self.label_mensaje_operar.grid(row=0, column=0, pady=10, sticky=tk.W)

            self.create_usdt_amount_entry(self.frame)

        self.update_labels_loop()

        self.window.mainloop()

    def update_labels_loop(self):
        self.update_labels()
        self.window.after(5000, self.update_labels_loop)

    def update_labels(self):
        if self.label_mensaje_operar and self.label_mensaje_operar.winfo_exists():
            self.label_mensaje_operar.config(text=self.mensaje_operar)

        if not hasattr(self, 'simbolos_win_previo') or self.simbolos_win != self.simbolos_win_previo:
            self.simbolos_win_previo = self.simbolos_win.copy()

            if self.frame and self.frame.winfo_exists():
                for widget in self.frame.winfo_children():
                    if widget.winfo_exists():
                        widget.destroy()

            self.label_mensaje_operar = ttk.Label(self.frame, text=self.mensaje_operar, wraplength=500)
            self.label_mensaje_operar.grid(row=0, column=0, pady=5, sticky=tk.W)

            self.create_usdt_amount_entry(self.frame)

            # Verificación de porcentaje_positivo_24h
            if self.porcentaje_positivo_24h is None or self.porcentaje_positivo_24h >= 30:
                self.disable_buttons_and_entries = False
            elif self.porcentaje_positivo_24h < 30 and not self.condiciones_operar:
                self.label_advertencia = ttk.Label(self.frame, text="La cantidad de monedas positivas en las últimas 24h es igual o inferior al 30%", foreground="red")
                self.label_advertencia.grid(row=1, column=0, pady=10, sticky=tk.W)
                self.disable_buttons_and_entries = True

            self.symbols_frame = ttk.Labelframe(self.frame, text="Operaciones", padding=(10, 5))
            self.symbols_frame.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky=(tk.W, tk.E))

            row = 0
            open_order_symbols = {order['symbol'] for order in self.estado_ordenes_filtrado}

            for symbol, price in sorted(self.simbolos_win.items(), key=lambda item: item[1]):
                formatted_price = int(price * 10**8)

                if symbol in open_order_symbols:
                    symbol_color = "grey"
                    label_color = "grey"
                else:
                    symbol_color = "blue"
                    label_color = "black"

                self.create_symbol_entry(row, symbol, formatted_price, symbol_color, label_color)
                row += 1

            if len(self.simbolos_win) >= 2:
                self.btn_graficos = ttk.Button(self.symbols_frame, text="Ver Gráficos", command=self.abrir_todos_los_links)
                self.btn_graficos.grid(row=row, column=0, pady=5, padx=5, sticky=tk.W)

            self.open_orders_frame = ttk.Labelframe(self.frame, text=f"Órdenes Abiertas ({self.total_ordenes})", padding=(10, 5))
            self.open_orders_frame.grid(row=2, column=5, columnspan=2, padx=5, pady=5, sticky=(tk.N, tk.S, tk.E, tk.W))

            self.frame.columnconfigure(0, weight=1)
            self.frame.columnconfigure(5, weight=1)

            if not self.simbolos_win:
                self.no_symbols_label = ttk.Label(self.frame, text="Sin monedas disponibles para operar", foreground="red")
                self.no_symbols_label.grid(row=3, column=0, pady=10)
            else:
                if hasattr(self, 'no_symbols_label'):
                    self.no_symbols_label.destroy()
                    del self.no_symbols_label

        else:
            open_order_symbols = {order['symbol'] for order in self.estado_ordenes_filtrado}
            row = 0

            for symbol, price in sorted(self.simbolos_win.items(), key=lambda item: item[1]):
                formatted_price = int(price * 10**8)

                if symbol in open_order_symbols:
                    symbol_color = "grey"
                    label_color = "grey"
                else:
                    symbol_color = "blue"
                    label_color = "black"

                if symbol in self.entries:
                    try:
                        label, entry_valor, label_orden, btn_abrir_orden = self.entries[symbol]
                        label.config(text=f"{symbol}: {formatted_price}", foreground=symbol_color)
                        label_orden.config(foreground=label_color)

                        if self.disable_buttons_and_entries:
                            entry_valor.config(state='disabled')
                            btn_abrir_orden.config(state='disabled')
                        else:
                            entry_valor.config(state='normal')
                            btn_abrir_orden.config(state='normal')

                    except tk.TclError:
                        self.create_symbol_entry(row, symbol, formatted_price, symbol_color, label_color)
                else:
                    self.create_symbol_entry(row, symbol, formatted_price, symbol_color, label_color)
                row += 1

            symbols_to_remove = set(self.entries.keys()) - set(self.simbolos_win.keys())
            for symbol in symbols_to_remove:
                label, entry_valor, label_orden, btn_abrir_orden = self.entries.pop(symbol)
                if label.winfo_exists():
                    label.destroy()
                if entry_valor.winfo_exists():
                    entry_valor.destroy()
                if label_orden.winfo_exists():
                    label_orden.destroy()
                if btn_abrir_orden.winfo_exists():
                    btn_abrir_orden.destroy()

            if not self.simbolos_win:
                if not hasattr(self, 'no_symbols_label'):
                    self.no_symbols_label = ttk.Label(self.frame, text="Sin monedas disponibles para operar", foreground="red")
                    self.no_symbols_label.grid(row=3, column=0, pady=10)
            else:
                if hasattr(self, 'no_symbols_label'):
                    self.no_symbols_label.destroy()
                    del self.no_symbols_label

            if len(self.simbolos_win) >= 2:
                if not hasattr(self, 'btn_graficos'):
                    self.btn_graficos = ttk.Button(self.symbols_frame, text="Ver Gráficos", command=self.abrir_todos_los_links)
                    self.btn_graficos.grid(row=row, column=0, pady=5, padx=5, sticky=tk.W)
            else:
                if hasattr(self, 'btn_graficos'):
                    self.btn_graficos.destroy()
                    del self.btn_graficos

        self.simbolos_win_previo = self.simbolos_win

        self.check_estado_ordenes()
        self.update_open_orders_frame()
        self.actualizar_ordenes_a_abrir()

    def update_open_orders_frame(self, orders=None):
        if self.open_orders_frame and self.open_orders_frame.winfo_exists():
            for widget in self.open_orders_frame.winfo_children():
                if widget.winfo_exists():
                    widget.destroy()

            row = 0
            estado_ordenes_filtrado = orders if orders is not None else self.estado_ordenes_filtrado
            if estado_ordenes_filtrado:
                current_order_ids = {order['orderId'] for order in estado_ordenes_filtrado}

                for index, order in enumerate(estado_ordenes_filtrado):
                    symbol = order['symbol']
                    price = float(order['price'])
                    side = order['side']
                    order_id = order['orderId']
                    orig_qty = round(float(order['origQty']), 1)  # Redondeamos la cantidad de monedas a un decimal máximo
                    formatted_price = price * 10**8  # Convertimos el precio al nuevo formato

                    usdt_value_per_coin = self.get_usdt_value(order_id, symbol)
                    usdt_value = orig_qty * usdt_value_per_coin if usdt_value_per_coin else 0

                    color = "green" if side == "BUY" else "red"
                    if order_id in self.morado_orders:
                        color = "purple"

                    label_order = ttk.Label(
                        self.open_orders_frame,
                        text=f"{symbol}: {formatted_price:.0f} - {usdt_value:.2f} USDT",
                        foreground=color,
                        cursor="hand2"
                    )
                    label_order.grid(row=row, column=0, sticky=tk.W, pady=2)
                    label_order.bind("<Button-1>", lambda e, symbol=symbol: self.open_link(symbol))
                    self.create_small_buttons(self.open_orders_frame, row, index)
                    btn_cancelar_orden = ttk.Button(self.open_orders_frame, text="Cancelar", command=lambda o=order: self.cancelar_orden(o))
                    btn_cancelar_orden.grid(row=row, column=4, padx=2, pady=2, sticky=tk.W)

                    toggle_text = "✓" if self.modificar.get(order_id, True) else "🚫"
                    bg_color = "green" if self.modificar.get(order_id, True) else "red"
                    btn_toggle = tk.Button(self.open_orders_frame, text=toggle_text, bg=bg_color, command=lambda o=order: self.toggle_modify_order(o))
                    btn_toggle.grid(row=row, column=5, padx=2, pady=2, sticky=tk.W)
                    row += 1
            else:
                label_no_orders = ttk.Label(self.open_orders_frame, text="Sin órdenes abiertas")
                label_no_orders.grid(row=row, column=0, sticky=tk.W, pady=2)

    def toggle_modify_order(self, order):
        order_id = order['orderId']
        current_state = self.modificar.get(order_id, True)
        new_state = not current_state
        self.modificar[order_id] = new_state
        self.update_open_orders_frame()  # Refresh the frame to update the button text and background color

    def check_estado_ordenes(self):
        # Actualizar previous_estado_ordenes_filtrado
        self.previous_estado_ordenes_filtrado = self.estado_ordenes_filtrado.copy()

        # Eliminar valores de caché para order_ids que ya no están en self.estado_ordenes_filtrado
        current_order_ids = {order['orderId'] for order in self.estado_ordenes_filtrado}
        for order_id in list(self.usdt_values_cache.keys()):
            if order_id not in current_order_ids:
                del self.usdt_values_cache[order_id]

    def check_queue(self):
        try:
            while True:
                data = self.queue.get_nowait()
                self.simbolos_win = data['simbolos_win']
                self.mensaje_operar = data['mensaje_operar']
                self.estado_ordenes_filtrado = data.get('estado_ordenes_filtrado', [])

        except queue.Empty:
            pass
        finally:
            self.window.after(1000, self.check_queue)

    def open_link(self, symbol):
        # Formatear el enlace con el símbolo correspondiente, eliminando 'BTC'
        base_url = "https://www.binance.com/es/trade/"
        symbol_without_btc = symbol.replace('BTC', '')
        url = f"{base_url}{symbol_without_btc}_BTC?type=spot"
        webbrowser.open(url)

    def abrir_todos_los_links(self):
        # Ordenar los símbolos por nearest_buy_price de menor a mayor
        sorted_simbolos_win = dict(sorted(self.simbolos_win.items(), key=lambda item: item[1]))

        # Convertir los precios a la forma deseada
        for symbol in sorted_simbolos_win:
            self.open_link(symbol)

    def abrir_orden(self, symbol, valor_compra_str, side):
        if not self.entry_usdt_amount.get():
            print("Introduce la cantidad de dólares para las órdenes")
            pygame.mixer.music.load('dolares_operacion.mp3')
            pygame.mixer.music.play()
            return

        try:
            valor_compra = float(valor_compra_str) * 10**-8
            
            if side == 'BUY':
                self.realizar_compra(symbol, valor_compra)
            elif side == 'SELL':
                self.realizar_venta(symbol, valor_compra)

            # Suponiendo que analizarealizar_compra` y `realizar_venta` añaden la orden a `self.estado_ordenes_filtrado`
            self.update_open_orders_frame(self.estado_ordenes_filtrado)
            self.actualizar_ordenes_a_abrir()

        except ValueError:
            print(f"Valor de entrada no es válido para {symbol}: {valor_compra_str}")
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()

    def cancelar_orden(self, order):
        try:
            self.client.cancel_order(symbol=order['symbol'], orderId=order['orderId'])
            self.estado_ordenes_filtrado = [o for o in self.estado_ordenes_filtrado if o['orderId'] != order['orderId']]
            self.update_open_orders_frame()
            self.saldo_insuficiente = False

        except BinanceAPIException as e:
            print(f"Error al cancelar la orden: {e}")

    def recomendar_compra(self, symbol):
        try:
            order_book_data = self.actualizar_libro_ordenes(symbol)
            if not order_book_data or 'order_book' not in order_book_data or 'porcentaje_compra' not in order_book_data:
                print(f"Error al obtener los datos del libro de órdenes para {symbol}.")
                return

            order_book = order_book_data['order_book']

            # Verificar si hay suficientes órdenes de venta y compra
            if not order_book['asks'] or not order_book['bids']:
                print(f"No se han podido obtener suficientes datos del order book del símbolo {symbol}.")
                return

            nearest_sell_price = float(order_book['asks'][0][0])
            nearest_buy_price = float(order_book['bids'][0][0])

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
            summary_4H = self.analizar_grafico_4H(symbol)
            tendencia_4H = self.identificar_tendencia(summary_4H, symbol)
            summary_1D = self.analizar_grafico_1D(symbol)
            tendencia_1D = self.identificar_tendencia(summary_1D, symbol)

            if not recent_sell_trades and tendencia_5m != 'ALCISTA':
                return

            # Agregar el símbolo y su nearest_buy_price a la lista de símbolos ganadores
            if not hasattr(self, 'simbolos_win'):
                self.simbolos_win = {}
            self.simbolos_win[symbol] = nearest_buy_price

            # Verificar el número de órdenes abiertas para el símbolo
            if self.cantidad_ordenes.get(symbol, 0) <= 2:
                if not self.saldo_insuficiente and tendencia_5m == 'ALCISTA' and tendencia_4H == 'ALCISTA' and tendencia_1D == 'ALCISTA' and self.porcentaje_positivo_24h >= 55:
                    if self.cantidad_operacion_usdt is None:
                        print("Por favor introduce la cantidad de USDT por órden.")
                    else:
                        self.realizar_compra(symbol, nearest_buy_price)

        except BinanceAPIException as e:
            if e.code == -1003:
                print("Error -1003: Demasiado peso utilizado para llamar a la API. Deteniendo el programa para evitar un posible baneo de la API.")
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()
                self.error_1003 = True  # Detener el programa
        except Exception as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al recomendar {symbol}: {e}")
            error_msg = f"Error al recomendar {symbol}: {e}\n"
            self.guardar_error(error_msg)

    def realizar_compra(self, symbol, valor_compra):
        try:
            if not self.error_1003 or not self.saldo_insuficiente:
                order_book_data = self.actualizar_libro_ordenes(symbol)

                if not order_book_data or 'order_book' not in order_book_data or 'porcentaje_compra' not in order_book_data:
                    print(f"Error al obtener los datos del libro de órdenes para {symbol}.")
                    return

                order_book = order_book_data['order_book']
                exchange_info = self.client.get_symbol_info(symbol)
                price_filter = None
                percent_price_by_side_filter = None
                for f in exchange_info['filters']:
                    if f['filterType'] == 'PRICE_FILTER':
                        price_filter = f
                    elif f['filterType'] == 'PERCENT_PRICE_BY_SIDE':
                        percent_price_by_side_filter = f

                if price_filter is None:
                    print(f"No se encontró el filtro de precio para {symbol}.")
                    return

                if percent_price_by_side_filter is None:
                    print(f"No se encontró el filtro de precio por lado para {symbol}.")
                    return

                min_price = float(price_filter['minPrice'])
                max_price = float(price_filter['maxPrice'])
                valor_compra = float(valor_compra)
                valor_compra = max(min(valor_compra, max_price), min_price)
                order_price_formatted = "{:.8f}".format(valor_compra)
                compra_price = float(order_price_formatted)

                last_price = float(self.client.get_symbol_ticker(symbol=symbol)['price'])
                multiplier_up = float(percent_price_by_side_filter['bidMultiplierUp'])
                multiplier_down = float(percent_price_by_side_filter['bidMultiplierDown'])

                if not (last_price * multiplier_down <= compra_price <= last_price * multiplier_up):
                    print(f"Precio de compra {compra_price} no cumple con el filtro PERCENT_PRICE_BY_SIDE para {symbol}.")
                    return

                cantidad_btc = self.cantidad_btc
                cantidad_exacta = cantidad_btc / compra_price

                lot_size_filter = next(f for f in exchange_info['filters'] if f['filterType'] == 'LOT_SIZE')
                min_qty = float(lot_size_filter['minQty'])
                max_qty = float(lot_size_filter['maxQty'])
                step_size = float(lot_size_filter['stepSize'])

                cantidad_exacta = max(min_qty, min(cantidad_exacta, max_qty))
                cantidad_exacta = math.floor(cantidad_exacta / step_size) * step_size
                cantidad_exacta_rounded = round(cantidad_exacta, 8)
                self.quantity = cantidad_exacta_rounded

                order = None
                try:
                    order = self.client.create_order(
                        symbol=symbol,
                        side='BUY',
                        type='LIMIT',
                        timeInForce='GTC',
                        quantity=cantidad_exacta_rounded,
                        price=order_price_formatted
                    )
                    print(f"Orden de compra de {symbol} abierta a {order_price_formatted}.")
                    pygame.mixer.music.load('compra_realizada.mp3')
                    pygame.mixer.music.play()
                    self.enviar_respuesta(self.driver, f"*Orden de compra de {symbol} abierta a {order_price_formatted}.*")

                except Exception as e:
                    error_message = str(e)
                    if 'APIError(code=-2010)' in error_message:
                        min_qty_usdt = self.obtener_minima_cantidad_usdt()
                        if self.free_usdt >= min_qty_usdt:
                            print(f"No hay suficiente balance para abrir la orden de compra con esa cantidad de monedas, se abrirá con el saldo disponible.")
                            pygame.mixer.music.load('saldo_insuficiente.mp3')
                            pygame.mixer.music.play()
                            cantidad_exacta_rounded = self.free_btc / compra_price
                            cantidad_exacta_rounded = max(min_qty, min(cantidad_exacta_rounded, max_qty))
                            cantidad_exacta_rounded = math.floor(cantidad_exacta_rounded / step_size) * step_size
                            cantidad_exacta_rounded = round(cantidad_exacta_rounded, 8)
                            self.quantity = cantidad_exacta_rounded
                            order = self.client.create_order(
                                symbol=symbol,
                                side='BUY',
                                type='LIMIT',
                                timeInForce='GTC',
                                quantity=cantidad_exacta_rounded,
                                price=order_price_formatted
                            )
                            self.enviar_respuesta(self.driver, f"*Orden de compra de {symbol} abierta a {order_price_formatted}.*")
                        else:
                            self.saldo_insuficiente = True
                            pygame.mixer.music.load('sin_saldo.mp3')
                            pygame.mixer.music.play()
                            self.enviar_respuesta(self.driver, f"*Sin saldo*")
                    else:
                        raise e

                if order:
                    vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)
                    order_id = order['orderId']
                    bids = order_book['bids']
                    buy_volume = sum([float(bid[1]) for bid in bids])
                    asks = order_book['asks']
                    sell_volume = sum([float(ask[1]) for ask in asks])

                    datos_compra = {
                        "Par": symbol,
                        "Order ID": order_id,
                        "VWAP Compra": vwap,
                        "Precio Compra": order_price_formatted,
                        "Volumen Compra": buy_volume,
                        "Volumen Venta": sell_volume,
                        "Precio Medio Compra Ultimas 24h": avg_buy_price,
                        "Precio Medio Venta Ultimas 24h": avg_sell_price,
                        "Order Book Compra": order_book
                    }

                    self.guardar_datos_compra(datos_compra)
                    
                    # Añadir la orden a estado_ordenes
                    self.estado_ordenes_filtrado.append(order)
                    self.update_open_orders_frame()

        except Exception as e:
            error_message = str(e)
            print(f"Error al realizar la compra: {error_message}")
            if 'APIError(code=-2010)' in error_message:
                self.saldo_insuficiente = True
                pygame.mixer.music.load('sin_saldo.mp3')
                self.enviar_respuesta(self.driver, f"*Sin saldo*")
            else:
                pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()

    def monitorear_compra(self, symbol, order_price, order_book, order_id=None, order_quantity=None):
        try:
            time.sleep(60)

            print(f"Iniciando monitoreo de la orden de compra de {symbol} a {order_price} BTC")

            while not self.error_1003:
                # Actualizar los tiempos de espera según la cantidad total de órdenes
                self.definir_tiempo_espera()
                tiempo_espera = self.tiempo_espera['tiempo_monitoreo']
                time.sleep(tiempo_espera)

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
                    self.enviar_respuesta(self.driver, f"*Orden de compra de {symbol} finalizada.*")

                    self.realizar_venta(symbol, order_price, order_id)
                    break

                order_status = None
                for order in self.estado_ordenes:
                    if order['orderId'] == order_id:
                        order_status = order['status']
                        break

                if not self.modificar.get(order_id, True):
                    continue

                order_book_data = self.actualizar_libro_ordenes(symbol)
                if order_book_data is None:
                    print("Order book vacío, reintentando obtenerlo.")
                    continue

                order_book = order_book_data['order_book']
                porcentaje_compra = order_book_data['porcentaje_compra']

                # Obtener el análisis del gráfico
                summary_1D = self.analizar_grafico_1D(symbol)
                tendencia_1D = self.identificar_tendencia(summary_1D, symbol)
                summary_4H = self.analizar_grafico_4H(symbol)
                tendencia_4H = self.identificar_tendencia(summary_4H, symbol)
                summary_5m = self.analizar_grafico_5m(symbol)
                tendencia_5m = self.identificar_tendencia(summary_5m, symbol)

                nearest_buy_price = min(float(order[0]) for order in order_book['bids'])

                if self.porcentaje_positivo_24h < 30 and not self.condiciones_operar:
                    print(f"La cantidad de monedas positivas es inferior el 30%, cancelando orden de compra de {symbol}")
                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                    self.saldo_insuficiente = False
                    break

                if order_price == nearest_buy_price and self.porcentaje_positivo_24h < 15 and self.condiciones_operar == False and tendencia_4H == 'BAJISTA' and tendencia_5m == 'BAJISTA':
                    print(f"La tendencia es bajista en 4h y 5min, el porcentaje de monedas positivas es menor al 15% y no se detectan condiciones favorables del mercado. Cancelando orden de compra de {symbol} a {order_price}.")
                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                    self.saldo_insuficiente = False
                    break

                if order_price < nearest_buy_price - 0.00000003:
                    print(f"El precio ha subido mas de 4 puntos para {symbol} a {order_price}. Eliminando orden de compra.")
                    self.client.cancel_order(symbol=symbol, orderId=order_id)
                    self.saldo_insuficiente = False
                    break

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

    def realizar_venta(self, symbol, order_price, order_id=None):
        if not self.error_1003:
            try:
                base_asset = symbol.replace('BTC', '')
                balance_info = self.client.get_asset_balance(asset=base_asset)
                available_balance = float(balance_info['free'])

                order_quantity = int(math.floor(available_balance))

                if order_quantity <= 0:
                    print(f"No hay suficiente saldo disponible para vender en {symbol}.")
                    self.saldo_insuficiente = False
                    return

                tick_size = self.client.get_symbol_info(symbol)['filters'][0]['tickSize']
                tick_size = float(tick_size)
                precio_venta = round(order_price + tick_size, 8)
                precio_venta_rounded = round(precio_venta / tick_size) * tick_size

                if precio_venta_rounded == order_price:
                    precio_venta = round(precio_venta_rounded + tick_size, 8)

                precio_venta_str = "{:.8f}".format(precio_venta)

                print(f"Vendiendo al precio de {precio_venta_str}.")

                order = self.client.create_order(
                    symbol=symbol,
                    side='SELL',
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=order_quantity,
                    price=precio_venta_str
                )

                print(f"Orden de venta de {symbol} realizada exitosamente.")

                # Añadir la orden a estado_ordenes
                self.estado_ordenes_filtrado.append(order)
                self.update_open_orders_frame()

            except Exception as e:
                if isinstance(e, BinanceAPIException):
                    if e.code == -2010:
                        print(f"Balance insuficiente de {symbol}, orden finalizada.")
                        self.saldo_insuficiente = False
                        return
                    elif e.code == -1013:
                        print(f"Error de filtro: NOTIONAL para {symbol}, orden finalizada.")
                        return
                pygame.mixer.music.load('error.mp3')
                pygame.mixer.music.play()    
                print(f"Error al realizar la orden de venta de {symbol}: {e}")
                error_msg = f"Error al realizar la orden de venta de {symbol}: {e}\n"
                self.guardar_error(error_msg)

    def monitorear_venta(self, symbol, venta_price, sell_quantity, order_id=None, order_book=None, porcentaje_positivo_24h_venta=None):
        try:

            order_book_data = self.actualizar_libro_ordenes(symbol)

            summary_4H = self.analizar_grafico_4H(symbol)
            tendencia_4H = self.identificar_tendencia(summary_4H, symbol)
            summary_5m = self.analizar_grafico_5m(symbol)
            tendencia_5m = self.identificar_tendencia(summary_5m, symbol)

            order_book = order_book_data['order_book']
            porcentaje_compra = order_book_data['porcentaje_compra']

            nearest_sell_price = min(float(order[0]) for order in order_book['asks'])
            nearest_buy_price = float(order_book['bids'][0][0])
            nearest_buy_orders = [order for order in order_book['bids'] if float(order[0]) == nearest_buy_price]
            nearest_sell_orders = [order for order in order_book['asks'] if float(order[0]) == nearest_sell_price]
            total_buy_quantity = sum(float(order[1]) for order in nearest_buy_orders)
            total_sell_quantity = sum(float(order[1]) for order in nearest_sell_orders)

            # Ajustar valores de "X" basado en las condiciones actuales
            x_sell_quantity, x_sell_price = self.ajustar_valores_x(self.cambio_positivo, self.porcentaje_positivo_24h, tendencia_4H, tendencia_5m, porcentaje_positivo_24h_venta)

            if float(venta_price) == round(nearest_sell_price + (x_sell_price - 0.00000001), 8) and float(total_buy_quantity) < 0.2 * float(total_sell_quantity) or float(venta_price) >= round(nearest_sell_price + x_sell_price, 8):
                self.morado_orders[order_id] = True
            else:
                # Desmarca la orden si no cumple la condición
                if order_id in self.morado_orders:
                    del self.morado_orders[order_id]

            time.sleep(60)

            Perdidas = False  # Inicializar la variable Perdidas como False por defecto
            print(f"Iniciando monitoreo de la orden de venta de {symbol} a {venta_price} BTC")

            vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

            while not self.error_1003:
                self.definir_tiempo_espera()
                tiempo_espera = self.tiempo_espera['tiempo_monitoreo']
                time.sleep(tiempo_espera)

                summary_4H = self.analizar_grafico_4H(symbol)
                tendencia_4H = self.identificar_tendencia(summary_4H, symbol)
                summary_5m = self.analizar_grafico_5m(symbol)
                tendencia_5m = self.identificar_tendencia(summary_5m, symbol)

                # Filtrar las órdenes abiertas por el símbolo dado
                order_active = False
                for order in self.estado_ordenes:
                    if order['orderId'] == order_id:
                        order_active = True
                        break

                if not order_active:
                    print(f"Orden de venta de {symbol} finalizada.")

                    vwap, avg_buy_price, avg_sell_price = self.calcular_datos(symbol)

                    order_book_data = self.actualizar_libro_ordenes(symbol)
                    if order_book_data is None:
                        print("Order book vacío, reintentando obtenerlo.")
                        continue

                    order_book = order_book_data['order_book']
                    porcentaje_compra = order_book_data['porcentaje_compra']

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
                    self.enviar_respuesta(self.driver, f"*Orden de venta de {symbol} finalizada.*")

                    try:
                        self.estado_ordenes_filtrado.remove(order)
                    except ValueError:
                        pass

                    self.update_open_orders_frame()
                    break

                order_status = None
                for order in self.estado_ordenes:
                    if order['orderId'] == order_id:
                        order_status = order['status']
                        break

                if not self.modificar.get(order_id, True):
                    continue

                order_book_data = self.actualizar_libro_ordenes(symbol)
                if order_book_data is None:
                    print("Order book vacío, reintentando obtenerlo.")
                    continue

                order_book = order_book_data['order_book']
                porcentaje_compra = order_book_data['porcentaje_compra']

                if nearest_buy_price is None:
                    nearest_buy_price = float(order_book['bids'][0][0])

                if nearest_sell_price is None:
                    nearest_sell_price = float(order_book['asks'][0][0])

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
                x_sell_quantity, x_sell_price = self.ajustar_valores_x(self.cambio_positivo, self.porcentaje_positivo_24h, tendencia_4H, tendencia_5m, porcentaje_positivo_24h_venta)

                if float(venta_price) == round(nearest_sell_price + (x_sell_price - 0.00000001), 8) and float(total_buy_quantity) < 0.2 * float(total_sell_quantity) or float(venta_price) >= round(nearest_sell_price + x_sell_price, 8):
                    self.morado_orders[order_id] = True
                else:
                    # Desmarca la orden si no cumple la condición
                    if order_id in self.morado_orders:
                        del self.morado_orders[order_id]
                
                if (
                    float(total_sell_quantity) > x_sell_quantity * float(total_buy_quantity) and 
                     float(venta_price) >= round(nearest_sell_price + x_sell_price, 8) and
                     float(venta_price) != nearest_sell_price
                ):
                    if tendencia_4H == 'BAJISTA':
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
                        
                        print(f"Ajustando orden de venta de {symbol} a {venta_price}. Vendiendo al precio de venta mas cercano {nearest_sell_price_str} ya que el precio ha bajado 4 puntos.")
                        self.enviar_respuesta(self.driver, f"*Ajustando orden de venta de {symbol} a {venta_price}. Vendiendo al precio de venta mas cercano {nearest_sell_price_str} ya que el precio ha bajado 4 puntos.*")
                        pygame.mixer.music.load('ajustando_venta.mp3')
                        pygame.mixer.music.play()
                        
                        # Añadir el nuevo order_id a self.perdidas
                        self.perdidas.append(new_order_id)
                        break

                if (
                    float(total_sell_quantity) > x_sell_quantity * float(total_buy_quantity) and 
                    float(venta_price) == round(nearest_sell_price + x_sell_price, 8) and
                    float(venta_price) == nearest_sell_price
                ):
                    # Verificar el valor nominal antes de cancelar la orden actual y crear una nueva
                    notional = sell_quantity * nearest_sell_price
                    if notional < self.min_notional:
                        print(f"Error: el valor nominal de la nueva orden ({notional}) es menor que el mínimo requerido ({self.min_notional}). No se ajustará la orden de venta.")
                        continue

                    if float(total_sell_quantity) < 0.25 * float(total_buy_quantity):
                        sell_price = "{:.8f}".format(nearest_sell_price)
                    else:
                        sell_price = "{:.8f}".format(nearest_buy_price)

                    # Cancelar la orden de venta
                    self.client.cancel_order(symbol=symbol, orderId=order_id)

                    # Abrir una nueva orden de venta al valor con órdenes de compra más cercano al valor con órdenes de venta
                    new_order = self.client.create_order(symbol=symbol, side='SELL', type='LIMIT', quantity=sell_quantity, price=sell_price, timeInForce='GTC')
                    
                    # Obtener el nuevo order_id
                    new_order_id = new_order['orderId']
                    
                    print(f"Ajustando orden de venta de {symbol} a {sell_price}. Vendiendo a {sell_price} ya que el precio ha bajado mas de 4 puntos.")
                    self.enviar_respuesta(self.driver, f"*Ajustando orden de venta de {symbol} a {sell_price}. Vendiendo a {sell_price} ya que el precio ha bajado mas de 4 puntos.*")
                    pygame.mixer.music.load('ajustando_venta.mp3')
                    pygame.mixer.music.play()
                    
                    # Añadir el nuevo order_id a self.perdidas
                    self.perdidas.append(new_order_id)
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

    def ajustar_valores_x(self, cambio_positivo, porcentaje_positivo_24h, tendencia_4H, tendencia_5m, porcentaje_positivo_24h_venta):
        if porcentaje_positivo_24h_venta < 10:
            x_sell_quantity = 0.00
            x_sell_price = 0.000000065
        elif 10 <= porcentaje_positivo_24h_venta < 25:
            x_sell_quantity = 0.08
            x_sell_price = 0.000000056
        elif 25 <= porcentaje_positivo_24h_venta < 40:
            x_sell_quantity = 0.16
            x_sell_price = 0.000000048
        elif 40 <= porcentaje_positivo_24h_venta < 55:
            x_sell_quantity = 0.24
            x_sell_price = 0.000000040
        elif 55 <= porcentaje_positivo_24h_venta <= 70:
            x_sell_quantity = 0.32
            x_sell_price = 0.000000031
        elif 70 < porcentaje_positivo_24h_venta <= 85:
            x_sell_quantity = 0.40
            x_sell_price = 0.000000023
        elif porcentaje_positivo_24h_venta > 85:
            x_sell_quantity = 0.50
            x_sell_price = 0.000000015

        valores_permitidos = [0.00000000, 0.00000001, 0.00000002, 0.00000003, 0.00000004, 0.00000005]

        def redondeo_personalizado(valor):
            # Buscar el valor más cercano en valores_permitidos
            valor_redondeado = min(valores_permitidos, key=lambda x: abs(x - valor))
            return valor_redondeado

        if (porcentaje_positivo_24h - 7.5) <= porcentaje_positivo_24h_venta <= (porcentaje_positivo_24h + 7.5):
            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and cambio_positivo:
                x_sell_quantity += 0.04
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000004)
            else:  
                x_sell_quantity -= 0.05
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000005)

            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and not cambio_positivo:
                x_sell_quantity += 0.05
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000005)
            else:  
                x_sell_quantity -= 0.04
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000004)
        elif (porcentaje_positivo_24h - 15) <= porcentaje_positivo_24h_venta <= (porcentaje_positivo_24h + 15):
            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and cambio_positivo:
                x_sell_quantity += 0.08
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000008)
            else:  
                x_sell_quantity -= 0.10
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000010)

            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and not cambio_positivo:
                x_sell_quantity += 0.10
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000010)
            else:  
                x_sell_quantity -= 0.08
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000008)
        elif (porcentaje_positivo_24h - 22.5) <= porcentaje_positivo_24h_venta <= (porcentaje_positivo_24h + 22.5):
            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and cambio_positivo:
                x_sell_quantity += 0.12
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000012)
            else:  
                x_sell_quantity -= 0.15
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000015)

            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and not cambio_positivo:
                x_sell_quantity += 0.15
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000015)
            else:  
                x_sell_quantity -= 0.12
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000012)

        elif (porcentaje_positivo_24h - 30) <= porcentaje_positivo_24h_venta <= (porcentaje_positivo_24h + 30):
            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and cambio_positivo:
                x_sell_quantity += 0.16
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000016)
            else:  
                x_sell_quantity -= 0.20
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000020)

            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and not cambio_positivo:
                x_sell_quantity += 0.20
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000020)
            else:  
                x_sell_quantity -= 0.16
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000016)
        elif (porcentaje_positivo_24h - 37.5) <= porcentaje_positivo_24h_venta <= (porcentaje_positivo_24h + 37.5):
            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and cambio_positivo:
                x_sell_quantity += 0.20
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000020)
            else:  
                x_sell_quantity -= 0.25
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000025)

            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and not cambio_positivo:
                x_sell_quantity += 0.25
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000025)
            else:  
                x_sell_quantity -= 0.20
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000020)
        elif (porcentaje_positivo_24h - 45) <= porcentaje_positivo_24h_venta <= (porcentaje_positivo_24h + 45):
            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and cambio_positivo:
                x_sell_quantity += 0.24
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000024)
            else:  
                x_sell_quantity -= 0.30
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000030)

            if porcentaje_positivo_24h_venta >= porcentaje_positivo_24h and not cambio_positivo:
                x_sell_quantity += 0.30
                x_sell_price = redondeo_personalizado(x_sell_price - 0.000000030)
            else:  
                x_sell_quantity -= 0.24
                x_sell_price = redondeo_personalizado(x_sell_price + 0.000000024)

        # Ajuste basado en tendencia_4H
        if tendencia_4H == 'BAJISTA' and cambio_positivo:
            x_sell_quantity += 0.11
            x_sell_price = redondeo_personalizado(x_sell_price - 0.000000011)
        else:
            x_sell_quantity -= 0.15
            x_sell_price = redondeo_personalizado(x_sell_price + 0.000000015)

        if tendencia_4H == 'BAJISTA' and not cambio_positivo:
            x_sell_quantity += 0.15
            x_sell_price = redondeo_personalizado(x_sell_price - 0.000000015)
        else:
            x_sell_quantity -= 0.11
            x_sell_price = redondeo_personalizado(x_sell_price + 0.000000011)

        if self.condiciones_operar:
            x_sell_quantity -= 0.10
            x_sell_price = redondeo_personalizado(x_sell_price + 0.000000010)
        else:
            x_sell_quantity += 0.10
            x_sell_price = redondeo_personalizado(x_sell_price - 0.000000010)

        # Ajuste basado en tendencia_5m
        if tendencia_5m == 'BAJISTA' and cambio_positivo:
            x_sell_quantity += 0.03
            x_sell_price = redondeo_personalizado(x_sell_price - 0.000000003)
        else:
            x_sell_quantity -= 0.05
            x_sell_price = redondeo_personalizado(x_sell_price + 0.000000005)

        if tendencia_5m == 'BAJISTA' and not cambio_positivo:
            x_sell_quantity += 0.05
            x_sell_price = redondeo_personalizado(x_sell_price - 0.000000005)
        else:
            x_sell_quantity -= 0.03
            x_sell_price = redondeo_personalizado(x_sell_price + 0.000000003)

        # Limitar valores de "X" a los rangos especificados y aplicar valores mínimos
        x_sell_quantity = max(0.15, min(x_sell_quantity, 0.65))
        x_sell_price = min(valores_permitidos, key=lambda x: abs(x - x_sell_price))

        return x_sell_quantity, x_sell_price

    def analizar_grafico_1D(self, symbol):
        exchanges = ["BINANCE", "HITBTC", "COINBASE", "KRAKEN", "BITFINEX"]
        summary = None

        if symbol in self.symbols_to_skip:
            return {'RECOMMENDATION': 'LATERAL'}

        for exchange in exchanges:
            while True:
                try:
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
                    error_msg = f"Error al analizar gráfico 1D para {symbol} en {exchange}: {e}"
                    if "Exchange or symbol not found" in str(e):
                        print(error_msg)
                        self.symbols_to_skip.add(symbol)
                        summary = {'RECOMMENDATION': 'LATERAL'}
                        return summary
                    print(error_msg)
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

        if symbol in self.symbols_to_skip:
            return {'RECOMMENDATION': 'LATERAL'}

        for exchange in exchanges:
            while True:
                try:
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
                    error_msg = f"Error al analizar gráfico 4H para {symbol} en {exchange}: {e}"
                    if "Exchange or symbol not found" in str(e):
                        print(error_msg)
                        self.symbols_to_skip.add(symbol)
                        summary = {'RECOMMENDATION': 'LATERAL'}
                        return summary
                    print(error_msg)
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

        if symbol in self.symbols_to_skip:
            return {'RECOMMENDATION': 'LATERAL'}

        for exchange in exchanges:
            while True:
                try:
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
                    error_msg = f"Error al analizar gráfico 5m para {symbol} en {exchange}: {e}"
                    if "Exchange or symbol not found" in str(e):
                        print(error_msg)
                        self.symbols_to_skip.add(symbol)
                        summary = {'RECOMMENDATION': 'LATERAL'}
                        return summary
                    print(error_msg)
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
        self.porcentaje_positivo_24h_anterior = None  # Inicializar como None
        self.historico_porcentaje_24h = []  # Inicializar la lista para almacenar valores históricos

        hilo = threading.Thread(target=self.mostrar_monedas)
        hilo.start()

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
                    time.sleep(5)  # Esperar 5 segundos antes de reintentar
                except requests.exceptions.RequestException as e:
                    print(f"Ocurrió un error al obtener datos iniciales: {e}")
                    error_msg = f"Ocurrió un error al obtener datos iniciales: {e}\n"
                    # Aquí asumes que hay un método para reproducir un sonido de error
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

            # Verificar si positive_symbols < (total_symbols * porcentaje_requerido / 100) y si no ha habido un aumento significativo
            if positive_symbols < (total_symbols * porcentaje_requerido / 100) and not aumento_significativo:
                # Verificar si hay un aumento positivo del 1.5% o más en el 50% o más de las monedas
                symbols_with_positive_jumps = 0
                for symbol, changes in self.symbols_price_changes.items():
                    if len(changes) > 1:
                        last_change = changes[-1]
                        positive_jumps = [change for change in changes[:-1] if last_change - change >= 1.5]
                        if len(positive_jumps) >= len(changes[:-1]) / 2:
                            symbols_with_positive_jumps += 1

            porcentaje_minimo_requerido = total_symbols * porcentaje_requerido / 100
            positive_jump_threshold = len(self.symbols_price_changes) / 2

            # Verificar si la cantidad de símbolos con porcentaje positivo es menor al porcentaje requerido
            if positive_symbols < porcentaje_minimo_requerido:
                if not aumento_significativo and symbols_with_positive_jumps < positive_jump_threshold:
                    print(f"No se ha detectado un aumento del 12% de monedas con porcentaje positivo, la cantidad de monedas con un cambio de precio positivo en las últimas 24 horas es del {self.porcentaje_positivo_24h}% y no llega al porcentaje mínimo del {porcentaje_requerido}%, y no se ha detectado un aumento del 1.5% en la mitad o más de las monedas. No se recomienda abrir nuevas ordenes.")
                    self.mensaje_operar = f"No se ha detectado un aumento del 12% de monedas con porcentaje positivo, la cantidad de monedas con un cambio de precio positivo en las últimas 24 horas es del {self.porcentaje_positivo_24h}% y no llega al porcentaje mínimo del {porcentaje_requerido}%, y no se ha detectado un aumento del 1.5% en la mitad o más de las monedas. No se recomienda abrir nuevas ordenes."
                    self.condiciones_operar = False
                elif not aumento_significativo and symbols_with_positive_jumps >= positive_jump_threshold:
                    print(f"Se ha detectado un aumento del 1.5% en el 50% o más de las monedas, se recomienda abrir ordenes de compra.")
                    self.mensaje_operar = f"Se ha detectado un aumento del 1.5% en el 50% o más de las monedas, se recomienda abrir ordenes de compra."
                    self.condiciones_operar = True
                elif aumento_significativo:
                    print(f"Se ha detectado un aumento igual o mayor al 12% en la cantidad de monedas con porcentaje positivo en las últimas 24h, se recomienda abrir ordenes de compra.")
                    self.mensaje_operar = f"Se ha detectado un aumento igual o mayor al 12% en la cantidad de monedas con porcentaje positivo en las últimas 24h, se recomienda abrir ordenes de compra."
                    self.condiciones_operar = True

            if bajada_significativa:
                print(f"Se ha detectado una bajada igual o mayor al 12% en la cantidad de monedas con porcentaje positivo en las últimas 24h, No se abrirán nuevas órdenes de compra.")
                self.mensaje_operar = f"Se ha detectado una bajada igual o mayor al 12% en la cantidad de monedas con porcentaje positivo en las últimas 24h, No se abrirán nuevas órdenes de compra."
                self.condiciones_operar = False

            # Verificar si el 50% o más de los valores almacenados ha bajado igual o más de un 1%
            symbols_with_drops = 0
            for symbol, changes in self.symbols_price_changes.items():
                if len(changes) > 1:
                    last_change = changes[-1]
                    drops = [change for change in changes[:-1] if change - last_change >= 1]
                    if len(drops) >= len(changes[:-1]) / 2:
                        symbols_with_drops += 1

            if symbols_with_drops >= len(self.symbols_price_changes) / 2:
                print("Se ha detectado una bajada del 1% en más del 50% de los valores históricos. No se recomienda abrir nuevas ordenes.")
                self.mensaje_operar = f"Se ha detectado una bajada del 1% en más del 50% de los valores históricos. No se recomienda abrir nuevas ordenes."
                self.condiciones_operar = False

            for ticker in tickers:
                symbol = ticker.get('symbol', '')
                price = float(ticker.get('lastPrice', 0))
                price_change_percent = float(ticker.get('priceChangePercent', 0))
                quote_volume = float(ticker.get('quoteVolume', 0))

                # Verificar si los datos son válidos y cumplen con las condiciones
                if symbol.endswith('BTC') and symbol != 'ZKBTC' and price <= 0.00000333 and quote_volume >= 0.1:  # 333
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
                self.simbolos_win = {}
                # Iniciar un hilo para cada símbolo en self.symbols_list
                futures = [executor.submit(self.recomendar_compra, symbol) for symbol in self.symbols_list]
                # Esperar a que todos los hilos hayan terminado
                for future in futures:
                    try:
                        future.result()  # Esto asegura que el hilo actual haya terminado antes de continuar
                    except Exception as e:
                        print(f"Error en la ejecución del hilo: {e}")

            # Poner los datos en la cola para ser actualizados en la interfaz de usuario
            self.queue.put({'simbolos_win': self.simbolos_win, 'mensaje_operar': self.mensaje_operar})
            #pygame.mixer.music.load('nuevas_monedas.mp3')
            #pygame.mixer.music.play()

            time.sleep(25)  # Esperar 65 segundos antes de volver a iniciar el proceso

    def imprimir_cantidad_equivalente_en_btc(self):
        self.convertir_usdt_a_btc()
        if self.cantidad_btc is not None:
            print(f"La cantidad de USDT ingresada es equivalente a {self.cantidad_btc} BTC.")
        else:
            print("No se pudo realizar la conversión de USDT a BTC.")

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

                # Redondear la cantidad de BTC a 8 decimales si no es None
                if cantidad_btc is not None:
                    self.cantidad_btc = round(cantidad_btc, 8)
                else:
                    self.cantidad_btc = None

            else:
                print("Error: No se pudo obtener el precio de BTCUSDT")
                self.cantidad_btc = None

        except requests.exceptions.Timeout:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print("Error: La solicitud a la API de Binance excedió el tiempo de espera")
            self.cantidad_btc = None
        except requests.exceptions.RequestException as e:
            pygame.mixer.music.load('error.mp3')
            pygame.mixer.music.play()
            print(f"Error al convertir USDT a BTC: {e}")
            self.cantidad_btc = None

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

    def verificar_estado_orden(self):
        with self.lock:
            while not self.error_1003:
                self.definir_tiempo_espera()
                tiempo_espera = self.tiempo_espera['tiempo_verificar_ordenes_grupales']
                time.sleep(tiempo_espera)
                try:
                    open_orders = self.client.get_open_orders()
                    
                    open_orders_dict = {order['orderId']: order for order in open_orders}

                    updated_estado_ordenes = []
                    for order in self.estado_ordenes:
                        order_id = order['orderId']
                        if order_id in open_orders_dict:
                            updated_estado_ordenes.append(open_orders_dict.pop(order_id))
                    
                    updated_estado_ordenes.extend(open_orders_dict.values())
                    self.estado_ordenes = updated_estado_ordenes
                    
                    # Filtrar los datos necesarios
                    self.estado_ordenes_filtrado = [
                        {
                            key: order[key] for key in ['symbol', 'price', 'side', 'orderId', 'origQty']
                        } for order in self.estado_ordenes
                    ]
                    
                    self.total_ordenes = len(self.estado_ordenes)
                    self.cantidad_ordenes = {}

                    for order in self.estado_ordenes:
                        symbol = order['symbol']
                        if symbol not in self.cantidad_ordenes:
                            self.cantidad_ordenes[symbol] = 0
                        self.cantidad_ordenes[symbol] += 1

                        order_id = order['orderId']
                        hilo_compra_activo = any(
                            thread.name == f"monitorear_compra_{order_id}" for thread in threading.enumerate()
                        )
                        hilo_venta_activo = any(
                            thread.name == f"monitorear_venta_{order_id}" for thread in threading.enumerate()
                        )
                        
                        if not hilo_compra_activo and not hilo_venta_activo:
                            self.order_ids_in_monitoring.add(order_id)
                            order_price = float(order['price'])
                            order_quantity = float(order['origQty'])

                            if order['side'] == 'BUY':
                                order_book_data = self.actualizar_libro_ordenes(symbol)
                                order_book = order_book_data['order_book']
                                threading.Thread(target=self.monitorear_compra, args=(symbol, order_price, order_book, order_id, order_quantity), name=f"monitorear_compra_{order_id}").start()
                            elif order['side'] == 'SELL':
                                order_book_data = self.actualizar_libro_ordenes(symbol)
                                order_book = order_book_data['order_book']
                                porcentaje_positivo_24h_venta = self.porcentaje_positivo_24h  # Nuevo argumento
                                threading.Thread(target=self.monitorear_venta, args=(symbol, order_price, order_quantity, order_id, order_book, porcentaje_positivo_24h_venta), name=f"monitorear_venta_{order_id}").start()

                    balances = self.client.get_account()['balances']

                    # Filtra los balances con "free" mayor a 0.0
                    balances_filtrados = [balance for balance in balances if float(balance['free']) > 0.0]

                    # Obtiene el precio actual de BTC en USDT
                    price = float(self.client.get_symbol_ticker(symbol='BTCUSDT')['price'])

                    for balance in balances_filtrados:
                        asset = balance['asset']
                        free = float(balance['free'])
                        symbol = f"{asset}BTC"

                        if asset == 'BTC':
                            # Convierte el balance "free" de BTC a USDT
                            self.free_usdt = free * price
                            self.free_btc = free

                        if asset not in ['BTC', 'USDT', 'QSP', 'POA', 'WPR', 'DLT'] and symbol in self.pares_btc:
                            try:
                                max_retries = 5
                                for attempt in range(max_retries):
                                    try:
                                        avg_price = float(self.client.get_avg_price(symbol=symbol)['price'])
                                        break
                                    except requests.exceptions.ReadTimeout:
                                        if attempt < max_retries - 1:
                                            time.sleep(2)
                                        else:
                                            print('Se alcanzó el número máximo de reintentos. No se pudo obtener el precio promedio.')
                                            pygame.mixer.music.load('error.mp3')
                                            pygame.mixer.music.play()
                                            raise

                                value_in_btc = free * avg_price

                                if value_in_btc >= self.min_qty_btc:
                                    asset_open_orders = [order for order in open_orders if order['symbol'] == symbol and order['side'] == 'SELL']

                                    if asset_open_orders:
                                        min_sell_price = min(float(order['price']) for order in asset_open_orders)
                                        sell_price = min_sell_price - 0.00000001
                                    else:
                                        historial = self.obtener_historial_operaciones(symbol)
                                        if historial:
                                            compras = [trade for trade in historial if trade['isBuyer']]
                                            if compras:
                                                ultima_compra = max(compras, key=lambda x: x['time'])
                                                sell_price = float(ultima_compra['price'])
                                            else:
                                                print(f"No se encontraron órdenes de compra en el historial para {symbol}. No se puede abrir una orden de venta.")
                                                pygame.mixer.music.load('error.mp3')
                                                pygame.mixer.music.play()
                                                continue
                                        else:
                                            print(f"No se pudo obtener el historial de operaciones para {symbol}. No se puede abrir una orden de venta.")
                                            pygame.mixer.music.load('error.mp3')
                                            pygame.mixer.music.play()
                                            continue

                                    threading.Thread(target=self.realizar_venta, args=(symbol, sell_price)).start()
                                    print(f"Intentando abrir una orden de venta para {asset} a {sell_price + 0.00000001}")

                            except BinanceAPIException as e:
                                if e.code == -1121:
                                    pygame.mixer.music.load('error.mp3')
                                    pygame.mixer.music.play()
                                    print(f"Símbolo inválido: {symbol}")

                    balances_btc = [balance for balance in balances if float(balance['free']) > 0.0 or float(balance['locked']) > 0.0]

                    total_btc = 0.0

                    for balance in balances_btc:
                        asset = balance['asset']
                        free = float(balance['free'])
                        locked = float(balance['locked'])
                        total_asset_balance = free + locked
                        symbol = f"{asset}BTC"

                        if asset == 'BTC':
                            total_btc += total_asset_balance
                        elif asset == 'USDT' and asset not in ['QSP', 'POA', 'WPR', 'DLT']:
                            # Convertir USDT a BTC
                            try:
                                avg_price = float(self.client.get_avg_price(symbol='BTCUSDT')['price'])
                                value_in_btc = total_asset_balance / avg_price
                                total_btc += value_in_btc
                            except BinanceAPIException as e:
                                if e.code == -1121:
                                    pygame.mixer.music.load('error.mp3')
                                    pygame.mixer.music.play()
                                    print(f"Símbolo inválido: BTCUSDT")
                        else:
                            if symbol in self.pares_btc:
                                max_retries = 5
                                for attempt in range(max_retries):
                                    try:
                                        avg_price = float(self.client.get_avg_price(symbol=symbol)['price'])
                                        break
                                    except requests.exceptions.ReadTimeout:
                                        if attempt < max_retries - 1:
                                            time.sleep(2)
                                        else:
                                            print('Se alcanzó el número máximo de reintentos. No se pudo obtener el precio promedio.')
                                            pygame.mixer.music.load('error.mp3')
                                            pygame.mixer.music.play()
                                            raise

                                value_in_btc = total_asset_balance * avg_price
                                total_btc += value_in_btc

                    self.btc = total_btc

                except (BinanceAPIException, requests.exceptions.ReadTimeout, Exception) as e:
                    pygame.mixer.music.load('error.mp3')
                    pygame.mixer.music.play()
                    if isinstance(e, BinanceAPIException) and e.code == -1003:
                        print("Error -1003: Demasiado peso utilizado para llamar a la API. Deteniendo el programa para evitar un posible baneo de la API.")
                        self.error_1003 = True
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
