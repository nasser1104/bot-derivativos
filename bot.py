import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import werkzeug
werkzeug.urls.url_quote = werkzeug.urls.quote
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    JobQueue
)
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz
from threading import Thread
import asyncio

# ================= CONFIGURAÇÕES =================
TOKEN = "7595299972:AAHe8kB0YSHl5e6AkJ_jYdcC5lf4Eu5rFv8"
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Lista de ações monitoradas
ACOES_MONITORADAS = ["PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", "JBSS3"]

# Fontes de notícias
FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Investing Brasil": "https://br.investing.com/news/stock-market-news",
    "Valor Econômico": "https://valor.globo.com/financas/"
}

# ================= ANÁLISE DE MERCADO =================
class AnalisadorMercado:
    def __init__(self):
        self.historico = pd.DataFrame(columns=['ativo', 'impacto', 'confianca', 'data'])
    
    async def buscar_noticias(self):
        oportunidades = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for noticia in soup.find_all('a', href=True)[:10]:
                    titulo = noticia.get_text(strip=True)
                    link = noticia['href'] if noticia['href'].startswith('http') else f"https://{url.split('/')[2]}{noticia['href']}"
                    
                    for acao in ACOES_MONITORADAS:
                        if acao.lower() in titulo.lower():
                            oportunidades.append({
                                'acao': acao,
                                'titulo': titulo,
                                'link': link,
                                'fonte': site
                            })
            except Exception as e:
                print(f"Erro em {site}: {e}")
        return oportunidades

    async def analisar_noticia(self, noticia):
        try:
            analise = pipeline("sentiment-analysis")(noticia['titulo'])[0]
            impacto = "alta" if analise['label'] == "POSITIVE" else "baixa"
            return {
                'impacto': impacto,
                'confianca': analise['score']
            }
        except:
            return {'impacto': 'neutro', 'confianca': 0}

# ================= FUNÇÕES DO BOT =================
analisador = AnalisadorMercado()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ *RadarAções Ativado!*\n"
        f"Monitorando {len(ACOES_MONITORADAS)} ações\n"
        "Use /opcoes para análises",
        parse_mode='Markdown'
    )

async def menu_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(acao, callback_data=f'opcao_{acao}')] 
        for acao in ACOES_MONITORADAS
    ]
    await update.message.reply_text(
        "📈 Selecione um ativo:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_opcao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acao = query.data.split('_')[1]
    
    # Busca dados
    ticker = yf.Ticker(f"{acao}.SA")
    preco = ticker.history(period="1d")['Close'].iloc[-1]
    noticias = await analisador.buscar_noticias()
    noticias_acao = [n for n in noticias if n['acao'] == acao][:3]
    
    # Monta relatório
    mensagem = f"📊 *{acao}* - R${preco:.2f}\n\n"
    for noticia in noticias_acao:
        analise = await analisador.analisar_noticia(noticia)
        mensagem += (
            f"▪️ *{noticia['fonte']}*: {noticia['titulo']}\n"
            f"   → Impacto: {analise['impacto'].upper()} "
            f"(Confiança: {analise['confianca']*100:.0f}%)\n\n"
        )
    
    await query.edit_message_text(
        text=mensagem,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def alertas_automaticos(context: ContextTypes.DEFAULT_TYPE):
    noticias = await analisador.buscar_noticias()
    alertas = []
    
    for noticia in noticias:
        analise = await analisador.analisar_noticia(noticia)
        if analise['confianca'] > 0.7:
            alertas.append(f"🚨 *{noticia['acao']}*: {noticia['titulo']} ({analise['impacto'].upper()})")
    
    if alertas:
        await context.bot.send_message(
            chat_id=context.job.chat_id,
            text="\n\n".join(alertas[:3]),  # Limita a 3 alertas
            parse_mode='Markdown'
        )

# ================= SERVIDOR FLASK =================
app = Flask(__name__)

@app.route('/')
def home():
    return "RadarAções Online"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def main():
    # Configuração do bot com JobQueue
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("opcoes", menu_opcoes))
    application.add_handler(CallbackQueryHandler(handle_opcao))
    
    # Job de alertas (se estiver disponível)
    if hasattr(application, 'job_queue'):
        application.job_queue.run_repeating(
            alertas_automaticos,
            interval=3600,  # 1 hora
            first=10
        )
        print("✅ JobQueue configurado com sucesso!")
    else:
        print("⚠️ JobQueue não disponível")
    
    # Inicia servidor em segundo plano
    Thread(target=run_flask).start()
    
    # Inicia o bot
    application.run_polling()

if __name__ == '__main__':
    main()