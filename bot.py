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
import numpy as np
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz
from threading import Thread
import asyncio

# ================= CONFIGURAÇÕES =================
TOKEN = "7595299972:AAHe8kB0YSHl5e6AkJ_jYdcC5lf4Eu5rFv8"  # Novo token do RadarAções
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Lista de ações monitoradas (TOP 30 B3)
ACOES_MONITORADAS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", 
    "ABEV3", "BBAS3", "WEGE3", "RENT3", "SUZB3",
    "JBSS3", "BPAC11", "ELET3", "GGBR4", "HAPV3",
    "NTCO3", "RAIL3", "SANB11", "TAEE11", "VBBR3",
    "CIEL3", "EQTL3", "KLBN11", "LREN3", "MGLU3",
    "PCAR3", "QUAL3", "SBSP3", "TOTS3", "UGPA3"
]

# Fontes de notícias premium
FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Investing Brasil": "https://br.investing.com/news/stock-market-news",
    "Valor Econômico": "https://valor.globo.com/financas/",
    "CNN Brasil Mercado": "https://www.cnnbrasil.com.br/business/mercados/",
    "Suno Notícias": "https://www.suno.com.br/noticias/mercado/",
    "Money Times": "https://www.moneytimes.com.br/ultimas-noticias/"
}

# ================= ANÁLISE DE MERCADO =================
class AnalisadorMercado:
    def __init__(self):
        self.historico = pd.DataFrame(columns=[
            'ativo', 'sentimento', 'impacto', 'preco', 
            'volume', 'delta', 'gamma', 'data'
        ])
    
    async def buscar_noticias(self):
        """Coleta notícias de todas as fontes"""
        oportunidades = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Padrões de busca por site
                if "infomoney" in url:
                    noticias = soup.find_all('a', class_='hl-title')
                elif "investing" in url:
                    noticias = soup.find_all('a', class_='title')
                else:
                    noticias = soup.find_all('a', href=True)
                
                for noticia in noticias[:15]:
                    titulo = noticia.get_text(strip=True)
                    link = noticia['href'] if noticia['href'].startswith('http') else f"https://{url.split('/')[2]}{noticia['href']}"
                    
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
        """Classifica notícias com IA"""
        analise = pipeline("sentiment-analysis")(noticia['titulo'])[0]
        impacto = self._detectar_tendencia(noticia['titulo'])
        return {
            'sentimento': analise['label'],
            'impacto': impacto,
            'confianca': analise['score']
        }
    
    def _detectar_tendencia(self, texto):
        """Detecta tendência baseada em palavras-chave"""
        palavras_alta = ["alta", "compra", "lucro", "valorizar", "upgrade", "positivo"]
        palavras_baixa = ["queda", "venda", "prejuízo", "downgrade", "perda", "negativo"]
        
        if any(palavra in texto.lower() for palavra in palavras_alta):
            return "alta"
        elif any(palavra in texto.lower() for palavra in palavras_baixa):
            return "baixa"
        return "neutro"

    async def analisar_opcoes(self, ativo):
        """Busca dados de opções para um ativo"""
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
                'delta_puts': chain.puts['delta'].mean(),
                'volume_calls': chain.calls['volume'].sum(),
                'volume_puts': chain.puts['volume'].sum()
            }
        except Exception as e:
            print(f"Erro ao analisar {ativo}: {str(e)}")
            return None

# ================= FUNÇÕES DO BOT =================
analisador = AnalisadorMercado()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagem de boas-vindas"""
    await update.message.reply_text(
        "📈 *RadarAções - Ativado!*\n"
        f"Monitorando {len(ACOES_MONITORADAS)} ações em {len(FONTES_NOTICIAS)} fontes\n\n"
        "Comandos disponíveis:\n"
        "/opcoes - Menu de análise por ativo\n"
        "/alertas - Configurar alertas automáticos",
        parse_mode='Markdown'
    )

async def menu_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu interativo de ações"""
    keyboard = [
        [InlineKeyboardButton(acao, callback_data=f'opcao_{acao}')] 
        for acao in ACOES_MONITORADAS[:8]  # Primeira página
    ]
    keyboard.append([InlineKeyboardButton("Próxima página →", callback_data='pagina_2')])
    
    await update.message.reply_text(
        "📊 *Selecione um ativo para análise completa:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_opcao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa seleção de ações"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('opcao_'):
        acao = query.data.split('_')[1]
        await query.edit_message_text(f"🔍 Analisando {acao}...")
        
        # Análise completa
        mensagem = await gerar_relatorio_acao(acao)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=mensagem,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

async def gerar_relatorio_acao(acao: str):
    """Gera relatório completo para uma ação"""
    # Dados do ativo
    ticker = yf.Ticker(f"{acao}.SA")
    dados = ticker.history(period="1d")
    preco_atual = dados['Close'].iloc[-1]
    
    # Notícias recentes
    noticias = await analisador.buscar_noticias()
    noticias_acao = [n for n in noticias if n['acao'] == acao][:3]  # Limita a 3
    
    # Dados de opções
    dados_opcoes = await analisador.analisar_opcoes(acao)
    
    # Monta relatório
    mensagem = f"📊 *Relatório {acao}*\n"
    mensagem += f"Preço Atual: R${preco_atual:.2f}\n"
    
    if dados_opcoes:
        mensagem += (
            f"\n📈 *Opções (Vencimento mais próximo)*\n"
            f"Delta Calls: {dados_opcoes['delta_calls']:.2f}\n"
            f"Delta Puts: {dados_opcoes['delta_puts']:.2f}\n"
            f"Volume Calls: {dados_opcoes['volume_calls']:,}\n"
            f"Volume Puts: {dados_opcoes['volume_puts']:,}\n"
        )
    
    if noticias_acao:
        mensagem += "\n📰 *Notícias Impactantes*\n"
        for noticia in noticias_acao:
            analise = await analisador.analisar_impacto(noticia)
            mensagem += (
                f"- [{analise['impacto'].upper()}] {noticia['titulo']}\n"
                f"  Confiança: {analise['confianca']*100:.0f}%\n"
                f"  Fonte: {noticia['fonte']}\n\n"
            )
    else:
        mensagem += "\nℹ️ Nenhuma notícia impactante recente\n"
    
    # Recomendação
    recomendacao = await gerar_recomendacao(acao, noticias_acao, dados_opcoes)
    mensagem += f"\n💡 *Recomendação:* {recomendacao}"
    
    return mensagem

async def gerar_recomendacao(acao, noticias, dados_opcoes):
    """Gera recomendação automatizada"""
    if not noticias:
        return "🔴 Sem dados suficientes"
    
    # Contagem de notícias positivas/negativas
    positivas = sum(1 for n in noticias if (await analisador.analisar_impacto(n))['impacto'] == 'alta')
    negativas = sum(1 for n in noticias if (await analisador.analisar_impacto(n))['impacto'] == 'baixa')
    
    # Análise de opções
    if dados_opcoes:
        delta_liquido = dados_opcoes['delta_calls'] - dados_opcoes['delta_puts']
        if delta_liquido > 0.3:
            return "🟢 COMPRA CALL (Força nas Calls)"
        elif delta_liquido < -0.3:
            return "🟢 COMPRA PUT (Força nas Puts)"
    
    # Recomendação baseada em notícias
    if positivas >= 2:
        return "🟢 COMPRA (Sinal positivo)"
    elif negativas >= 2:
        return "🔴 VENDA (Sinal negativo)"
    return "🟡 NEUTRO (Aguardar confirmação)"

async def alertas_automaticos(context: ContextTypes.DEFAULT_TYPE):
    """Envia alertas periódicos das melhores oportunidades"""
    noticias = await analisador.buscar_noticias()
    oportunidades = []
    
    for noticia in noticias:
        analise = await analisador.analisar_impacto(noticia)
        if analise['impacto'] in ['alta', 'baixa'] and analise['confianca'] > 0.7:
            oportunidades.append((
                noticia['acao'],
                analise['impacto'],
                noticia['titulo'],
                analise['confianca'],
                noticia['fonte']
            ))
    
    if oportunidades:
        # Ordena por confiança e pega as top 3
        oportunidades.sort(key=lambda x: x[3], reverse=True)
        mensagem = "🚨 *ALERTAS DE MERCADO* 🚨\n\n"
        
        for acao, impacto, titulo, confianca, fonte in oportunidades[:3]:
            mensagem += (
                f"📌 *{acao}* - Tendência de {impacto.upper()} "
                f"(Confiança: {confianca*100:.0f}%)\n"
                f"_{titulo}_\n"
                f"Fonte: {fonte}\n\n"
            )
        
        await context.bot.send_message(
            chat_id=context.job.chat_id,
            text=mensagem,
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
    """Configuração principal do bot"""
    app_telegram = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("opcoes", menu_opcoes))
    app_telegram.add_handler(CallbackQueryHandler(handle_opcao))
    
    # Agendamento de tarefas
    job_queue = app_telegram.job_queue
    job_queue.run_repeating(
        callback=alertas_automaticos,
        interval=3600,  # A cada 1 hora
        first=10
    )
    
    # Inicia servidor Flask em segundo plano
    Thread(target=run_flask).start()
    
    # Inicia o bot
    app_telegram.run_polling()

if __name__ == '__main__':
    main()