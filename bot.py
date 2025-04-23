import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Silencia avisos do TensorFlow/PyTorch

# Correção para o conflito Flask/Werkzeug
import werkzeug
werkzeug.urls.url_quote = werkzeug.urls.quote  # Patch para versões incompatíveis
from flask import Flask, request

# ========== SEU CÓDIGO ORIGINAL (COM TOKEN ATUALIZADO) ==========
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz

# Configurações
TOKEN = "7599002954:AAFhh9jpTn-PUBIXpbOUuu3fatf_NuxFz4A"  # SEU TOKEN JÁ INSERIDO
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Inicialização do Flask (para manter o bot online)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot de Derivativos B3 Online"

class BotDerivativos:
    def __init__(self):
        self.historico = pd.DataFrame(columns=[
            'ativo', 'tipo', 'sentimento', 'impacto', 'preco_atual',
            'volume', 'delta', 'gamma', 'data'
        ])

    async def analisar_opcoes(self, ativo):
        try:
            ticker = yf.Ticker(f"{ativo}.SA")
            opts = ticker.options
            if not opts:
                return None
                
            chain = ticker.option_chain(opts[0])
            return {
                'ativo': ativo,
                'preco_atual': ticker.history(period='1d')['Close'].iloc[-1],
                'delta_calls': chain.calls['delta'].mean(),
                'gamma_calls': chain.calls['gamma'].mean(),
                'volume_calls': chain.calls['volume'].sum(),
                'volume_puts': chain.puts['volume'].sum(),
                'data': datetime.now(TIMEZONE)
            }
        except Exception as e:
            logging.error(f"Erro em {ativo}: {str(e)}")
            return None

# ... (ADICIONE AQUI O RESTO DO SEU CÓDIGO ORIGINAL)

def main():
    # Inicia o bot do Telegram
    app_telegram = ApplicationBuilder().token(TOKEN).build()
    app_telegram.add_handler(CommandHandler("opcoes", menu_opcoes))
    app_telegram.add_handler(CallbackQueryHandler(handle_opcao, pattern='^opcao_'))
    app_telegram.run_polling()

if __name__ == '__main__':
    # Inicia o servidor Flask em segundo plano
    from threading import Thread
    Thread(target=app.run, kwargs={'host':'0.0.0.0','port':8080}).start()
    
    # Inicia o bot principal
    main()