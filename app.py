from flask import Flask, render_template, request, redirect
from models import db, Transacao
import os
import pandas as pd
from ofxparse import OfxParser
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financeiro.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
db.init_app(app)

@app.route('/')
def index():
    transacoes = Transacao.query.all()
    return render_template('index.html', transacoes=transacoes)

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        tipo = request.form['tipo']
        descricao = request.form['descricao']
        valor = float(request.form['valor'])
        categoria = request.form['categoria']
        nova = Transacao(tipo=tipo, descricao=descricao, valor=valor, categoria=categoria)
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
                nova = Transacao(
                    tipo='despesa' if row['Valor'] < 0 else 'receita',
                    descricao=row['Descrição'],
                    valor=abs(row['Valor']),
                    categoria=row.get('Categoria', 'Importado')
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
                        categoria='Importado'
                    )
                    db.session.add(nova)

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
        mes = t.descricao[:7] if '-' in t.descricao else 'Outro'
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
    with app.app_context():
        db.create_all()
    app.run(debug=True)
