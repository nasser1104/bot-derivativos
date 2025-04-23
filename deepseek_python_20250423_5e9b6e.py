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
from flask import Flask

# Configurações
TOKEN = "7599002954:AAFhh9jpTn-PUBIXpbOUuu3fatf_NuxFz4A"  # SEU TOKEN JÁ INSERIDO
TIMEZONE = pytz.timezone('America/Sao_Paulo')
MODELO_IA = "finiteautomata/bertweet-base-sentiment-analysis"

# Inicialização
app_flask = Flask(__name__)
analisador_sentimento = pipeline("sentiment-analysis", model=MODELO_IA)

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

# ... (restante do código das funções principais)

@app_flask.route('/')
def home():
    return "Bot de Derivativos B3 Online"

def keep_alive():
    app_flask.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    keep_alive()
    main()