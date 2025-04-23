import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Silencia avisos do PyTorch/TensorFlow
import werkzeug
werkzeug.urls.url_quote = werkzeug.urls.quote  # Correção para Flask
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, JobQueue
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz
from threading import Thread

# ================= CONFIGURAÇÕES =================
TOKEN = "7599002954:AAFhh9jpTn-PUBIXpbOUuu3fatf_NuxFz4A"
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Lista COMPLETA de ações monitoradas (TOP 30 B3 + suas preferências)
ACOES_MONITORADAS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", 
    "ABEV3", "BBAS3", "WEGE3", "RENT3", "SUZB3",
    "JBSS3", "BPAC11", "ELET3", "GGBR4", "HAPV3",
    "NTCO3", "RAIL3", "SANB11", "TAEE11", "VBBR3",
    "CIEL3", "EQTL3", "KLBN11", "LREN3", "MGLU3",
    "PCAR3", "QUAL3", "SBSP3", "TOTS3", "UGPA3"
]

# Fontes de notícias (12 sites premium)
FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Investing Brasil": "https://br.investing.com/news/stock-market-news",
    "TradingView BR": "https://br.tradingview.com/news/",
    "Bloomberg Brasil": "https://www.bloomberglinea.com.br/",
    "Valor Econômico": "https://valor.globo.com/financas/",
    "CNN Brasil Mercado": "https://www.cnnbrasil.com.br/business/mercados/",
    "Seu Dinheiro": "https://www.seudinheiro.com.br/mercados/",
    "Suno Notícias": "https://www.suno.com.br/noticias/mercado/",
    "Money Times": "https://www.moneytimes.com.br/ultimas-noticias/",
    "Investidor Sardinha": "https://investidorsardinha.r7.com/noticias/",
    "Analise de Acoes": "https://analisedeacoes.com.br/noticias/",
    "Exame Mercado": "https://exame.com/mercados/"
}

# ================= FUNÇÕES PRINCIPAIS =================
class AnalisadorMercado:
    def __init__(self):
        self.historico = pd.DataFrame(columns=[
            'ativo', 'sentimento', 'impacto', 'preco', 
            'volume', 'delta', 'gamma', 'data'
        ])
    
    async def buscar_noticias(self):
        """Varre todos os sites e filtra notícias relevantes"""
        oportunidades = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Padrões de busca específicos por site
                if "infomoney" in url:
                    noticias = soup.find_all('a', class_='hl-title')
                elif "investing" in url:
                    noticias = soup.find_all('a', class_='title')
                else:  # Fallback genérico
                    noticias = soup.find_all('a', href=True)
                
                for noticia in noticias[:15]:  # Limita por site
                    titulo = noticia.get_text(strip=True)
                    link = noticia['href'] if noticia['href'].startswith('http') else f"https://{url.split('/')[2]}{noticia['href']}"
                    
                    # Filtra por ações monitoradas
                    for acao in ACOES_MONITORADAS:
                        if acao.lower() in titulo.lower():
                            oportunidades.append({
                                'acao': acao,
                                'titulo': titulo,
                                'fonte': site,
                                'link': link,
                                'data': datetime.now(TIMEZONE)
                            })
            except Exception as e:
                print(f"Erro em {site}: {str(e)}")
        return oportunidades

    async def analisar_impacto(self, noticia):
        """Classifica o impacto usando IA"""
        analise = pipeline("sentiment-analysis")(noticia['titulo'])[0]
        return {
            'sentimento': analise['label'],
            'confianca': analise['score'],
            'impacto': self._detectar_tendencia(noticia['titulo'])
        }
    
    def _detectar_tendencia(self, texto):
        """Regras para tendências"""
        palavras_alta = ["alta", "compra", "lucro", "valorizar", "upgrade"]
        palavras_baixa = ["queda", "venda", "prejuízo", "downgrade", "perda"]
        
        if any(palavra in texto.lower() for palavra in palavras_alta):
            return "alta"
        elif any(palavra in texto.lower() for palavra in palavras_baixa):
            return "baixa"
        return "neutro"

# ================= TELEGRAM BOT =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ *Bot de Derivativos B3 Ativado!*\n"
        f"Monitorando {len(ACOES_MONITORADAS)} ativos em {len(FONTES_NOTICIAS)} fontes\n\n"
        "Comandos disponíveis:\n"
        "/opcoes - Menu de análise por ativo\n"
        "/alertas - Configurar alertas automáticos",
        parse_mode='Markdown'
    )

async def menu_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu interativo de ações"""
    keyboard = [
        [InlineKeyboardButton(acao, callback_data=f'opcao_{acao}')] 
        for acao in ACOES_MONITORADAS[:10]  # Mostra as 10 primeiras
    ]
    keyboard.append([InlineKeyboardButton("Próxima página →", callback_data='pagina_2')])
    
    await update.message.reply_text(
        "📈 *Selecione um ativo para análise detalhada:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ... (continuam as outras funções do bot)

# ================= SERVIDOR FLASK =================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot de Derivativos B3 Online"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    # Inicia o Flask em segundo plano
    Thread(target=run_flask).start()
    
    # Inicia o bot do Telegram
    main()