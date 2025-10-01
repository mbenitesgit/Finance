from flask import Flask, render_template, request, redirect
from models import db, Transacao
import os
import pandas as pd
from ofxparse import OfxParser
import matplotlib.pyplot as plt
import io
import base64
import fitz
import pytesseract
from PIL import Image
import re
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financeiro.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    transacoes = Transacao.query.order_by(Transacao.data.desc()).all()
    return render_template('index.html', transacoes=transacoes)

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        tipo = request.form['tipo']
        descricao = request.form['descricao']
        valor = float(request.form['valor'])
        categoria = request.form['categoria']
        nova = Transacao(
            tipo=tipo,
            descricao=descricao,
            valor=valor,
            categoria=categoria,
            data=datetime.today().date()
        )
        db.session.add(nova)
        db.session.commit()
        return redirect('/')
    return render_template('cadastro.html')

@app.route('/importar', methods=['GET', 'POST'])
def importar():
    if request.method == 'POST':
        arquivo = request.files['arquivo']
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], arquivo.filename)
        arquivo.save(caminho)

        if arquivo.filename.endswith('.csv'):
            df = pd.read_csv(caminho)
            for _, row in df.iterrows():
                data = pd.to_datetime(row.get('Data', datetime.today()), dayfirst=True).date()
                nova = Transacao(
                    tipo='despesa' if row['Valor'] < 0 else 'receita',
                    descricao=row['Descrição'],
                    valor=abs(row['Valor']),
                    categoria=row.get('Categoria', 'CSV Importado'),
                    data=data
                )
                db.session.add(nova)

        elif arquivo.filename.endswith('.ofx'):
            with open(caminho) as f:
                ofx = OfxParser.parse(f)
                for trans in ofx.account.statement.transactions:
                    nova = Transacao(
                        tipo='despesa' if trans.amount < 0 else 'receita',
                        descricao=trans.memo,
                        valor=abs(trans.amount),
                        categoria='OFX Importado',
                        data=trans.date.date()
                    )
                    db.session.add(nova)

        elif arquivo.filename.endswith('.pdf'):
            doc = fitz.open(caminho)
            for pagina in doc:
                texto = pagina.get_text()
                if not texto.strip():
                    imagem = pagina.get_pixmap()
                    img_bytes = imagem.tobytes("png")
                    imagem_pil = Image.open(io.BytesIO(img_bytes))
                    texto = pytesseract.image_to_string(imagem_pil)

                linhas = texto.split('\n')
                for linha in linhas:
                    if 'R$' in linha:
                        partes = linha.strip().split()
                        match = re.search(r'\d{2}/\d{2}/\d{4}', linha)
                        data = datetime.strptime(match.group(), '%d/%m/%Y').date() if match else datetime.today().date()
                        try:
                            valor_str = partes[-1].replace('R$', '').replace('.', '').replace(',', '.')
                            valor = float(valor_str)
                            descricao = ' '.join(partes[:-1])
                            tipo = 'despesa' if valor < 0 else 'receita'
                            nova = Transacao(
                                tipo=tipo,
                                descricao=descricao,
                                valor=abs(valor),
                                categoria='PDF Importado',
                                data=data
                            )
                            db.session.add(nova)
                        except:
                            continue

        elif arquivo.filename.endswith('.txt') or arquivo.filename.endswith('.ofc'):
            with open(caminho, encoding='utf-8') as f:
                linhas = f.readlines()
                for linha in linhas:
                    if 'R$' in linha or linha.strip():
                        partes = linha.strip().split()
                        match = re.search(r'\d{2}/\d{2}/\d{4}', linha)
                        data = datetime.strptime(match.group(), '%d/%m/%Y').date() if match else datetime.today().date()
                        try:
                            valor_str = partes[-1].replace('R$', '').replace('.', '').replace(',', '.')
                            valor = float(valor_str)
                            descricao = ' '.join(partes[:-1])
                            tipo = 'despesa' if valor < 0 else 'receita'
                            nova = Transacao(
                                tipo=tipo,
                                descricao=descricao,
                                valor=abs(valor),
                                categoria='TXT/OFC Importado',
                                data=data
                            )
                            db.session.add(nova)
                        except:
                            continue

        db.session.commit()
        return redirect('/')
    return render_template('importar.html')

@app.route('/relatorio')
def relatorio():
    transacoes = Transacao.query.all()
    receitas = sum(t.valor for t in transacoes if t.tipo == 'receita')
    despesas = sum(t.valor for t in transacoes if t.tipo == 'despesa')
    saldo = receitas - despesas

    meses = {}
    for t in transacoes:
        mes = t.data.strftime('%Y-%m')
        if mes not in meses:
            meses[mes] = {'receita': 0, 'despesa': 0}
        meses[mes][t.tipo] += t.valor

    labels = list(meses.keys())
    receitas_mensais = [meses[m]['receita'] for m in labels]
    despesas_mensais = [meses[m]['despesa'] for m in labels]

    fig, ax = plt.subplots()
    ax.bar(labels, receitas_mensais, label='Receitas', color='green')
    ax.bar(labels, despesas_mensais, label='Despesas', color='red', bottom=receitas_mensais)
    ax.set_ylabel('R$')
    ax.set_title('Movimentações Mensais')
    ax.legend()

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    grafico = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.close()

    return render_template('relatorio.html', receitas=receitas, despesas=despesas, saldo=saldo, grafico=grafico)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
