import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import werkzeug
werkzeug.urls.url_quote = werkzeug.urls.quote
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
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
import traceback
import json

# ================= CONFIGURAÇÕES =================
TOKEN = "7595299972:AAHe8kB0YSHl5e6AkJ_jYdcC5lf4Eu5rFv8"
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Lista das 100 ações mais negociadas com opções listadas
ACOES_COM_OPCOES = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", "ABEV3", "BBAS3", "PETR3",
    "ITSA4", "WEGE3", "JBSS3", "RENT3", "SUZB3", "ELET3", "BBDC3", "GGBR4",
    "VALE5", "LREN3", "RAIL3", "NTCO3", "EQTL3", "UGPA3", "CIEL3", "CSNA3",
    "MGLU3", "BRFS3", "EMBR3", "TOTS3", "CYRE3", "GOAU4", "PRIO3", "TAEE11",
    "CRFB3", "HYPE3", "BRKM5", "BRML3", "QUAL3", "RADL3", "ENBR3", "MRFG3",
    "IRBR3", "ECOR3", "BRAP4", "EGIE3", "COGN3", "CVCB3", "BRDT3", "SLCE3",
    "JHSF3", "MULT3", "SOMA3", "AZUL4", "YDUQ3", "PCAR3", "BPAC11", "BEEF3",
    "TIMS3", "MRVE3", "FLRY3", "LWSA3", "CPLE6", "CPFE3", "USIM5", "VULC3",
    "RRRP3", "ALPA4", "CMIG4", "GRND3", "CASH3", "TUPY3", "SMTO3", "ARZZ3",
    "IGTA3", "EZTC3", "LEVE3", "ALSO3", "ENGI11", "ASAI3", "MOVI3", "VIIA3",
    "POSI3", "CSAN3", "AERI3", "BLAU3", "GMAT3", "RECV3", "AURE3", "PTBL3"
]

# Fontes de notícias
FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Investing Brasil": "https://br.investing.com/news/stock-market-news",
    "Valor Econômico": "https://valor.globo.com/financas/",
    "Reuters Brasil": "https://www.reuters.com.br/",
    "CNN Brasil Economia": "https://www.cnnbrasil.com.br/economia/",
    "Sunoresearch": "https://sunoresearch.com.br/noticias/",
    "TradersClub": "https://www.tradersclub.com.br/noticias",
    "Money Times": "https://www.moneytimes.com.br/ultimas-noticias/",
    "Seu Dinheiro": "https://www.seudinheiro.com.br/noticias/",
    "Economia UOL": "https://economia.uol.com.br/ultimas/"
}

# ================= API DE OPÇÕES =================
class OpcoesB3:
    @staticmethod
    async def get_opcoes_yfinance(acao: str):
        """Busca dados de opções usando Yahoo Finance"""
        try:
            ticker = yf.Ticker(f"{acao}.SA")
            opts = ticker.options
            if not opts:
                return None
                
            # Pega opções do próximo vencimento
            next_expiry = opts[0]
            calls = ticker.option_chain(next_expiry).calls
            puts = ticker.option_chain(next_expiry).puts
            
            return {
                'acao': acao,
                'vencimento': next_expiry,
                'calls': calls[['strike', 'lastPrice', 'bid', 'ask', 'volume']].to_dict('records'),
                'puts': puts[['strike', 'lastPrice', 'bid', 'ask', 'volume']].to_dict('records')
            }
        except Exception as e:
            print(f"Erro Yahoo Finance opções: {str(e)}")
            return None

    @staticmethod
    async def get_opcoes_b3(acao: str):
        """Busca dados de opções da B3 (simulação - na prática usar API real)"""
        try:
            # Simulação - na prática usar:
            # 1. API da B3 (requer cadastro)
            # 2. Ou scraping de sites como http://www.opcoes.net.br
            return None
        except Exception as e:
            print(f"Erro B3 opções: {str(e)}")
            return None

# ================= ANÁLISE DE MERCADO =================
class AnalisadorMercado:
    def __init__(self):
        self.historico = pd.DataFrame(columns=['ativo', 'impacto', 'confianca', 'data', 'fonte'])
        self.sentiment_pipeline = pipeline("sentiment-analysis")
    
    async def buscar_noticias(self):
        oportunidades = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extrai notícias (adaptar por site)
                noticias = soup.find_all('a', href=True)[:15]
                for noticia in noticias:
                    titulo = noticia.get_text(strip=True)
                    if not titulo or len(titulo) < 15:
                        continue
                        
                    link = noticia['href']
                    if not link.startswith('http'):
                        link = f"{url.rsplit('/', 1)[0]}/{link.lstrip('/')}"
                    
                    # Verifica menção a ações
                    for acao in ACOES_COM_OPCOES:
                        if acao.lower() in titulo.lower():
                            oportunidades.append({
                                'acao': acao,
                                'titulo': titulo,
                                'link': link,
                                'fonte': site,
                                'timestamp': datetime.now(TIMEZONE)
                            })
                            break
            except Exception as e:
                print(f"Erro em {site}: {str(e)}")
        return oportunidades

    async def analisar_noticia(self, noticia):
        try:
            analise = self.sentiment_pipeline(noticia['titulo'])[0]
            impacto = "alta" if analise['label'] == "POSITIVE" else "baixa"
            return {
                'impacto': impacto,
                'confianca': analise['score']
            }
        except:
            return {'impacto': 'neutro', 'confianca': 0.5}

# ================= FUNÇÕES DO BOT =================
analisador = AnalisadorMercado()
opcoes_b3 = OpcoesB3()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ *RadarOpções Ativado!*\n"
        f"📈 Monitorando {len(ACOES_COM_OPCOES)} ações com opções\n"
        "📰 10 fontes de notícias em tempo real\n\n"
        "🔍 Envie o código de uma ação (ex: PETR4) para informações\n"
        "💹 Use /opcoes [ação] para dados completos de opções",
        parse_mode='Markdown'
    )

async def handle_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.upper().strip()
    
    if texto not in ACOES_COM_OPCOES:
        await update.message.reply_text(
            "❌ Ação não encontrada ou sem opções listadas\n"
            f"📊 Ações com opções: {', '.join(ACOES_COM_OPCOES[:5])}...",
            parse_mode='Markdown'
        )
        return
    
    try:
        # Busca dados da ação
        ticker = yf.Ticker(f"{texto}.SA")
        hist = ticker.history(period="1d")
        preco = hist['Close'].iloc[-1]
        
        # Busca notícias
        noticias = await analisador.buscar_noticias()
        noticias_acao = [n for n in noticias if n['acao'] == texto][:3]
        
        # Monta mensagem
        msg = f"📊 *{texto}* - R$ {preco:.2f}\n"
        msg += f"📅 Vencimentos opções: {', '.join(ticker.options[:3])}\n\n"
        
        if noticias_acao:
            msg += "📌 *Notícias recentes:*\n"
            for noticia in noticias_acao:
                analise = await analisador.analisar_noticia(noticia)
                msg += (
                    f"▪️ [{noticia['fonte']}]({noticia['link']}): {noticia['titulo']}\n"
                    f"   → Impacto: {analise['impacto'].upper()} "
                    f"(Confiança: {analise['confianca']*100:.0f}%)\n\n"
                )
        
        await update.message.reply_text(
            text=msg,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Erro: {traceback.format_exc()}")
        await update.message.reply_text(f"⚠️ Erro ao processar {texto}")

async def opcoes_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "📋 *Modo Opções*\n\n"
            "Envie o código de uma ação com opções listadas:\n"
            "Ex: /opcoes PETR4\n\n"
            f"📌 Ações disponíveis: {', '.join(ACOES_COM_OPCOES[:5])}...",
            parse_mode='Markdown'
        )
        return
    
    acao = args[0].upper()
    if acao not in ACOES_COM_OPCOES:
        await update.message.reply_text("❌ Ação não tem opções listadas na B3")
        return
    
    try:
        # Busca dados reais das opções
        dados_opcoes = await opcoes_b3.get_opcoes_yfinance(acao)
        if not dados_opcoes:
            await update.message.reply_text("⚠️ Dados de opções temporariamente indisponíveis")
            return
        
        # Preço da ação
        ticker = yf.Ticker(f"{acao}.SA")
        preco_acao = ticker.history(period="1d")['Close'].iloc[-1]
        
        # Formata mensagem
        msg = (
            f"📊 *OPÇÕES PARA {acao}* (Preço: R$ {preco_acao:.2f})\n"
            f"📅 Vencimento: {dados_opcoes['vencimento']}\n\n"
            "🔷 *CALLS (Compra)*\n"
            "Strike | Prêmio | Volume\n"
        )
        
        # Top 5 calls
        for call in sorted(dados_opcoes['calls'], key=lambda x: x['strike'])[:5]:
            msg += f"{call['strike']:.2f} | {call['lastPrice']:.2f} | {call['volume']}\n"
        
        msg += "\n🔶 *PUTS (Venda)*\n"
        # Top 5 puts
        for put in sorted(dados_opcoes['puts'], key=lambda x: x['strike'], reverse=True)[:5]:
            msg += f"{put['strike']:.2f} | {put['lastPrice']:.2f} | {put['volume']}\n"
        
        msg += "\nℹ️ Dados em tempo real via Yahoo Finance"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Erro opções: {traceback.format_exc()}")
        await update.message.reply_text(f"⚠️ Erro ao buscar opções: {str(e)}")

async def alertas_automaticos(context: ContextTypes.DEFAULT_TYPE):
    try:
        noticias = await analisador.buscar_noticias()
        alertas = []
        
        for noticia in noticias:
            analise = await analisador.analisar_noticia(noticia)
            if analise['confianca'] > 0.7:
                alertas.append(
                    f"🚨 *{noticia['acao']}*: {noticia['titulo']}\n"
                    f"📌 Impacto: {analise['impacto'].upper()} "
                    f"(Conf: {analise['confianca']*100:.0f}%)\n"
                    f"🔗 [Leia mais]({noticia['link']})"
                )
        
        if alertas:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text="\n\n".join(alertas[:3]),  # Limita a 3 alertas
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    except Exception as e:
        print(f"Erro alertas: {str(e)}")

# ================= SERVIDOR FLASK =================
app = Flask(__name__)

@app.route('/')
def home():
    return "RadarOpções Online"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("opcoes", opcoes_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_acao))
    
    # Job de alertas
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            alertas_automaticos,
            interval=3600,  # 1 hora
            first=10
        )
        print("✅ Alertas automáticos ativados!")
    
    # Inicia servidor Flask
    Thread(target=run_flask).start()
    
    # Inicia o bot
    application.run_polling()

if __name__ == '__main__':
    main()