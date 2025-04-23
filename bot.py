import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import warnings
warnings.filterwarnings("ignore")

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
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz
from threading import Thread
import asyncio
import traceback

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("TELEGRAM_TOKEN", "7595299972:AAHe8kB0YSHl5e6AkJ_jYdcC5lf4Eu5rFv8")
TIMEZONE = pytz.timezone('America/Sao_Paulo')
PORT = int(os.getenv("PORT", 8080))

# Lista das 100 ações mais negociadas
ACOES_B3 = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", "ABEV3", "BBAS3", "PETR3", 
    "ITSA4", "WEGE3", "JBSS3", "RENT3", "BPAC11", "SUZB3", "ELET3", "BBDC3",
    "HAPV3", "GGBR4", "VALE5", "ITUB3", "LREN3", "RAIL3", "NTCO3", "BBSE3",
    "EQTL3", "UGPA3", "CIEL3", "CSNA3", "KLBN11", "SBSP3", "MGLU3", "BRFS3",
    "EMBR3", "TOTS3", "CYRE3", "BRDT3", "BRML3", "QUAL3", "CCRO3", "VIVT3",
    "RADL3", "ENBR3", "PRIO3", "IRBR3", "MRFG3", "TAEE11", "GOAU4", "BEEF3",
    "ECOR3", "BRAP4", "EGIE3", "CRFB3", "TIMS3", "MRVE3", "AZUL4", "YDUQ3",
    "MULT3", "COGN3", "CVCB3", "LAME4", "PCAR3", "BRKM5", "SULA11", "SANB11",
    "HYPE3", "FLRY3", "LWSA3", "CPLE6", "CPFE3", "BRSR6", "GOLL4", "SLCE3",
    "USIM5", "DXCO3", "VULC3", "RRRP3", "ALPA4", "CMIG4", "JHSF3", "ELET6",
    "SOMA3", "GRND3", "CASH3", "TUPY3", "SMTO3", "ARZZ3", "IGTA3", "EZTC3",
    "LEVE3", "ALSO3", "ENGI11", "ASAI3", "BTOW3", "MOVI3", "AERI3", "BLAU3",
    "GMAT3", "VIIA3", "POSI3", "CSAN3", "RECV3", "AURE3", "TRPL4", "PTBL3"
]

# Fontes de notícias (10 sites)
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

# ================= SERVIDOR WEB (Render Fix) =================
app = Flask(__name__)

@app.route('/')
def home():
    return "RadarB3 Online - Acesse via Telegram"

@app.route('/health')
def health_check():
    return {"status": "online", "acoes_monitoradas": len(ACOES_B3)}, 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ================= ANÁLISE DE MERCADO =================
class AnalisadorMercado:
    def __init__(self):
        self.historico = pd.DataFrame(columns=['ativo', 'impacto', 'confianca', 'data', 'fonte'])
        self.sentiment_pipeline = pipeline(
            "text-classification",
            model="neuralmind/bert-base-portuguese-cased",
            tokenizer="neuralmind/bert-base-portuguese-cased"
        )
    
    async def buscar_noticias(self):
        oportunidades = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extração específica por site
                if "infomoney" in url:
                    noticias = soup.find_all('a', class_='hl-title', href=True)[:10]
                elif "investing" in url:
                    noticias = soup.find_all('a', class_='title', href=True)[:10]
                else:  # Fallback genérico
                    noticias = soup.find_all('a', href=True)[:15]
                
                for noticia in noticias:
                    titulo = noticia.get_text(strip=True)
                    link = noticia['href']
                    
                    # Verifica ações mencionadas
                    for acao in ACOES_B3:
                        if acao.lower() in titulo.lower():
                            oportunidades.append({
                                'acao': acao,
                                'titulo': titulo,
                                'link': link if link.startswith('http') else f"{url}{link}",
                                'fonte': site,
                                'timestamp': datetime.now(TIMEZONE)
                            })
                            break
            except:
                continue
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

# ================= API DE OPÇÕES =================
class OpcoesManager:
    @staticmethod
    async def get_opcoes(acao: str):
        try:
            ticker = yf.Ticker(f"{acao}.SA")
            if not ticker.options:
                return None
                
            expiry = ticker.options[0]
            chain = ticker.option_chain(expiry)
            
            return {
                'acao': acao,
                'vencimento': expiry,
                'calls': chain.calls[['strike', 'lastPrice', 'volume']].to_dict('records'),
                'puts': chain.puts[['strike', 'lastPrice', 'volume']].to_dict('records')
            }
        except:
            return None

# ================= FUNÇÕES DO BOT =================
analisador = AnalisadorMercado()
opcoes_manager = OpcoesManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"✅ *RadarB3 Premium Ativado!*\n"
        f"📈 Monitorando {len(ACOES_B3)} ações\n"
        f"📰 Fontes: {len(FONTES_NOTICIAS)} sites financeiros\n\n"
        "🔍 Envie o código de uma ação (ex: PETR4) para análise\n"
        "💹 Use /opcoes [ação] para dados de opções",
        parse_mode='Markdown'
    )

async def handle_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.upper().strip()
    
    if texto not in ACOES_B3:
        await update.message.reply_text("❌ Ação não encontrada. Use /start para lista completa")
        return
    
    try:
        # Dados da ação
        ticker = yf.Ticker(f"{texto}.SA")
        hist = ticker.history(period="1d")
        preco = hist['Close'].iloc[-1]
        
        # Notícias
        noticias = await analisador.buscar_noticias()
        noticias_acao = [n for n in noticias if n['acao'] == texto][:3]
        
        # Monta resposta
        msg = f"📊 *{texto}* - R$ {preco:.2f}\n\n"
        if noticias_acao:
            msg += "📌 *Notícias recentes:*\n"
            for noticia in noticias_acao:
                analise = await analisador.analisar_noticia(noticia)
                msg += (
                    f"▪️ {noticia['fonte']}: {noticia['titulo']}\n"
                    f"   → Impacto: {analise['impacto'].upper()} "
                    f"(Confiança: {analise['confianca']*100:.0f}%)\n\n"
                )
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro: {str(e)}")

async def opcoes_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "📋 *Uso correto:* /opcoes [código da ação]\n"
            "Ex: /opcoes PETR4\n\n"
            "📌 Ações com opções ativas: PETR4, VALE3, ITUB4, BBDC4, etc.",
            parse_mode='Markdown'
        )
        return
    
    acao = args[0].upper()
    if acao not in ACOES_B3:
        await update.message.reply_text("❌ Ação não encontrada")
        return
    
    try:
        dados = await opcoes_manager.get_opcoes(acao)
        if not dados:
            raise Exception("Dados não disponíveis")
            
        ticker = yf.Ticker(f"{acao}.SA")
        preco_spot = ticker.history(period="1d")['Close'].iloc[-1]
        
        # Formata mensagem
        msg = (
            f"📊 *OPÇÕES {acao}* (Spot: R$ {preco_spot:.2f})\n"
            f"📅 Vencimento: {dados['vencimento']}\n\n"
            "🔷 *CALLS (Compra)*\n"
        )
        
        # Top 5 calls
        for call in sorted(dados['calls'], key=lambda x: x['strike'])[:5]:
            msg += f"Strike {call['strike']:.2f} | Último {call['lastPrice']:.2f} | Vol {call['volume']}\n"
        
        msg += "\n🔶 *PUTS (Venda)*\n"
        # Top 5 puts
        for put in sorted(dados['puts'], key=lambda x: x['strike'], reverse=True)[:5]:
            msg += f"Strike {put['strike']:.2f} | Último {put['lastPrice']:.2f} | Vol {put['volume']}\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro nas opções: {str(e)}")

async def alertas_automaticos(context: ContextTypes.DEFAULT_TYPE):
    try:
        noticias = await analisador.buscar_noticias()
        alertas = []
        
        for noticia in noticias[:5]:  # Limita a 5 alertas
            analise = await analisador.analisar_noticia(noticia)
            if analise['confianca'] > 0.7:
                alertas.append(
                    f"🚨 *{noticia['acao']}*: {noticia['titulo']}\n"
                    f"📌 {noticia['fonte']} | Impacto: {analise['impacto'].upper()}\n"
                    f"🔗 {noticia['link']}"
                )
        
        if alertas:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text="\n\n".join(alertas),
                parse_mode='Markdown'
            )
    except:
        pass

# ================= INICIALIZAÇÃO =================
def main():
    # Configuração do bot
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("opcoes", opcoes_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_acao))
    
    # Job de alertas (se houver JobQueue)
    if application.job_queue:
        application.job_queue.run_repeating(
            alertas_automaticos,
            interval=3600,  # 1 hora
            first=10
        )
    
    # Inicia servidor Flask em thread separada
    Thread(target=run_flask, daemon=True).start()
    
    # Inicia o bot
    print("🟢 Bot iniciado com sucesso!")
    application.run_polling()

if __name__ == '__main__':
    main()