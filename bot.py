import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import werkzeug
werkzeug.urls.url_quote = werkzeug.urls.quote
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz
from threading import Thread

# Configurações
TOKEN = "7599002954:AAFhh9jpTn-PUBIXpbOUuu3fatf_NuxFz4A"
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Inicialização do Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot de Derivativos B3 Online"

# --- Funções do Bot ---
async def menu_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("PETR4", callback_data='opcao_PETR4')],
        [InlineKeyboardButton("VALE3", callback_data='opcao_VALE3')],
        [InlineKeyboardButton("ITUB4", callback_data='opcao_ITUB4')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📊 Escolha um ativo para análise:",
        reply_markup=reply_markup
    )

async def handle_opcao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ativo = query.data.split('_')[1]
    await query.edit_message_text(f"Análise para {ativo} carregando...")

# --- Configuração Principal ---
def main():
    app_telegram = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app_telegram.add_handler(CommandHandler("opcoes", menu_opcoes))
    app_telegram.add_handler(CallbackQueryHandler(handle_opcao, pattern='^opcao_'))
    
    # Inicia em segundo plano
    Thread(target=app.run, kwargs={'host':'0.0.0.0','port':8080}).start()
    app_telegram.run_polling()

if __name__ == '__main__':
    main()