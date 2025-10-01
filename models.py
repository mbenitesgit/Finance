from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10))
    descricao = db.Column(db.String(100))
    valor = db.Column(db.Float)
    categoria = db.Column(db.String(50))
    data = db.Column(db.Date, default=datetime.today)
