import os
import re
from decimal import Decimal, InvalidOperation
from getpass import getpass

import mysql.connector
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder='../frontend', static_url_path='')


def conectar():
    return mysql.connector.connect(
        host=os.environ.get('MYSQL_HOST', 'localhost'),
        user=os.environ.get('MYSQL_USER', 'root'),
        password=os.environ['MYSQL_PASSWORD'],
        database='supermercado_nobre'
    )


@app.errorhandler(mysql.connector.Error)
def erro_banco(erro):
    app.logger.error('Falha MySQL: %s', erro)
    return jsonify(erro='Não foi possível acessar o banco. Confira o terminal do servidor.'), 503


@app.route('/')
def inicio():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/produtos')
def listar_produtos():
    conexao = conectar()
    try:
        cursor = conexao.cursor(dictionary=True)
        try:
            cursor.execute('''SELECT p.*, c.nome AS categoria_nome,
                              f.nome AS fornecedor_nome
                              FROM Produto p
                              LEFT JOIN Categoria c ON c.id_categoria = p.id_categoria
                              LEFT JOIN Fornecedor f ON f.id_fornecedor = p.id_fornecedor
                              ORDER BY p.id_produto DESC''')
            return jsonify(cursor.fetchall())
        finally:
            cursor.close()
    finally:
        conexao.close()


def texto(dados, chave, limite, obrigatorio=False):
    valor = dados.get(chave, '')
    if not isinstance(valor, str):
        raise ValueError(f'{chave}: informe um texto.')
    valor = valor.strip()
    if (obrigatorio and not valor) or len(valor) > limite:
        raise ValueError(f'{chave}: informe de {1 if obrigatorio else 0} a {limite} caracteres.')
    return valor


def inteiro(dados, chave):
    valor = str(dados.get(chave, '0'))
    if not re.fullmatch(r'[0-9]+', valor) or int(valor) > 2147483647:
        raise ValueError(f'{chave}: informe um número inteiro não negativo até 2147483647.')
    return int(valor)


@app.route('/produtos', methods=['POST'])
def cadastrar_produto():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify(erro='Envie os dados do produto em JSON.'), 400
    try:
        codigo = texto(dados, 'codigo', 50, True)
        nome = texto(dados, 'nome', 150, True)
        descricao = texto(dados, 'descricao', 255)
        unidade = texto(dados, 'unidade_media', 30, True)
        quantidade = inteiro(dados, 'quantidade_estoque')
        minimo = inteiro(dados, 'estoque_minimo')
        preco = Decimal(str(dados.get('preco', '')).replace(',', '.'))
        if not preco.is_finite() or preco < 0 or preco > Decimal('99999999.99'):
            raise ValueError('Preço fora do intervalo permitido.')
        if preco != preco.quantize(Decimal('0.01')):
            raise ValueError('O preço deve ter no máximo duas casas decimais.')
    except (ValueError, InvalidOperation):
        # InvalidOperation também cobre valores que não podem ser convertidos.
        return jsonify(erro='Confira os campos: código, nome e unidade são obrigatórios; '
                            'preço deve ser não negativo, até 99999999,99 e ter até duas casas; '
                            'estoque e mínimo devem ser inteiros não negativos. '
                            'Respeite os limites de tamanho dos campos.'), 400

    conexao = conectar()
    try:
        cursor = conexao.cursor()
        try:
            cursor.execute('''INSERT INTO Produto
                (codigo, nome, descricao, preco, quantidade_estoque,
                 estoque_minimo, unidade_media, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)''',
                (codigo, nome, descricao, preco, quantidade, minimo, unidade))
            id_produto = cursor.lastrowid
            conexao.commit()
            return jsonify(id_produto=id_produto, mensagem='Produto cadastrado com sucesso.'), 201
        except mysql.connector.IntegrityError as erro:
            conexao.rollback()
            if erro.errno == 1062:
                return jsonify(erro='Já existe um produto com esse código.'), 409
            raise
        except mysql.connector.Error:
            conexao.rollback()
            raise
        finally:
            cursor.close()
    finally:
        conexao.close()


if __name__ == '__main__':
    # Solicita a senha localmente caso este terminal ainda não tenha a variável.
    if 'MYSQL_PASSWORD' not in os.environ:
        os.environ['MYSQL_PASSWORD'] = getpass('Senha do MySQL (não aparece ao digitar): ')
    app.run(host='127.0.0.1', port=5001, debug=False)
