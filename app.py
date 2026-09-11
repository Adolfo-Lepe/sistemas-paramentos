import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sqlalchemy import create_engine
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from datetime import date

# --- CONEXÃO BANCO DE DADOS (NEON) ---
# Tenta ler das configurações do Render/Streamlit Secrets ou variável local
DATABASE_URL = os.environ.get("DATABASE_URL") or st.secrets.get("DATABASE_URL")

@st.cache_resource
def get_engine():
    # Neon exige prefixo postgresql://
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url)

engine = get_engine()

# --- INICIALIZAÇÃO DAS TABELAS ---
def init_db():
    with engine.connect() as conn:
        conn.execute(tf.raw_symbolic_text if False else """
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                tipo_doc VARCHAR(10),
                documento VARCHAR(20) UNIQUE,
                data_nasc DATE,
                data_ordenacao DATE,
                paroquia VARCHAR(255),
                telefone VARCHAR(50),
                endereco TEXT
            );
            CREATE TABLE IF NOT EXISTS vendas (
                id SERIAL PRIMARY KEY,
                cliente_id INTEGER REFERENCES clientes(id),
                produto VARCHAR(255) NOT NULL,
                data_compra DATE NOT NULL,
                valor_pago NUMERIC(10,2) NOT NULL,
                metodo_pagamento VARCHAR(50),
                status_envio VARCHAR(50)
            );
        """)

try:
    init_db()
except Exception as e:
    pass

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Paramentos Litúrgicos 24/7", layout="wide")
st.title("⛪ Gestão de Paramentos Litúrgicos & Previsão com Deep Learning")

menu = st.sidebar.selectbox("Menu", ["Dashboard", "Previsão (Deep Learning)", "Cadastrar Cliente", "Registrar Venda", "Atualizar Envio"])

if menu == "Dashboard":
    st.header("📊 Painel de Vendas e Logística (Neon DB)")
    df_vendas = pd.read_sql('''
        SELECT v.id, c.nome AS cliente, c.paroquia, v.produto, v.data_compra, 
               v.valor_pago, v.metodo_pagamento, v.status_envio
        FROM vendas v JOIN clientes c ON v.cliente_id = c.id
    ''', engine)

    if not df_vendas.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Faturamento Total", f"R$ {df_vendas['valor_pago'].sum():,.2f}")
        col2.metric("Pedidos Enviados", len(df_vendas[df_vendas['status_envio'].isin(['Postado', 'Entregue'])]))
        col3.metric("Pendentes/Atrasados", len(df_vendas[df_vendas['status_envio'].isin(['Pendente', 'Atrasado'])]))

        st.divider()
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_pag = px.bar(df_vendas, x="metodo_pagamento", y="valor_pago", color="metodo_pagamento", title="Vendas por Meio de Pagamento")
            st.plotly_chart(fig_pag, use_container_width=True)
        with col_g2:
            fig_status = px.pie(df_vendas, names="status_envio", hole=0.4, title="Situação dos Envios")
            st.plotly_chart(fig_status, use_container_width=True)
            
        st.dataframe(df_vendas, use_container_width=True)
    else:
        st.info("Nenhuma venda cadastrada no Neon PostgreSQL ainda.")

elif menu == "Previsão (Deep Learning)":
    st.header("🧠 Previsão de Demandas de Vendas (Rede Neuronal Keras)")
    df = pd.read_sql("SELECT data_compra, valor_pago FROM vendas", engine)
    
    if len(df) >= 5:
        df['data_compra'] = pd.to_datetime(df['data_compra'])
        df_daily = df.groupby('data_compra')['valor_pago'].sum().reset_index()
        
        # Preparação dos dados para a Rede Neural
        df_daily['dias'] = (df_daily['data_compra'] - df_daily['data_compra'].min()).dt.days
        X = df_daily[['dias']].values
        y = df_daily['valor_pago'].values
        
        # Modelo Perceptron Multicamadas (Deep Learning)
        model = Sequential([
            Dense(64, activation='relu', input_shape=(1,)),
            Dense(32, activation='relu'),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse')
        model.fit(X, y, epochs=200, verbose=0)
        
        # Previsão para os próximos 30 dias
        ult_dia = df_daily['dias'].max()
        futuro_dias = np.array([[ult_dia + i] for i in range(1, 31)])
        previsoes = model.predict(futuro_dias).flatten()
        
        datas_futuras = [df_daily['data_compra'].max() + pd.Timedelta(days=i) for i in range(1, 31)]
        df_prev = pd.DataFrame({'Data': datas_futuras, 'Valor Previsto (R$)': previsoes})
        
        st.subheader("Estimativa de Vendas para os Próximos 30 Dias")
        fig_prev = px.line(df_prev, x='Data', y='Valor Previsto (R$)', title="Projeção IA / Deep Learning")
        st.plotly_chart(fig_prev, use_container_width=True)
    else:
        st.warning("Cadastre pelo menos 5 vendas no sistema para treinar o modelo de Deep Learning.")

elif menu == "Cadastrar Cliente":
    st.header("👤 Novo Cadastro de Cliente")
    with st.form("form_cliente"):
        nome = st.text_input("Nome / Razão Social")
        tipo_doc = st.selectbox("Tipo", ["CPF", "CNPJ"])
        documento = st.text_input("Documento (CPF/CNPJ)")
        data_nasc = st.date_input("Data Nascimento", value=date(1990, 1, 1))
        data_ord = st.date_input("Data Ordenação (Sacerdotes)", value=None)
        paroquia = st.text_input("Paróquia / Diocese")
        telefone = st.text_input("Telefone")
        endereco = st.text_area("Endereço")

        if st.form_submit_button("Salvar no Neon DB"):
            if nome and documento:
                query = """
                    INSERT INTO clientes (nome, tipo_doc, documento, data_nasc, data_ordenacao, paroquia, telefone, endereco)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                with engine.connect() as conn:
                    conn.execute(query, (nome, tipo_doc, documento, data_nasc, data_ord, paroquia, telefone, endereco))
                st.success("Cliente salvo com sucesso no Neon DB!")

elif menu == "Registrar Venda":
    st.header("🛒 Registrar Venda")
    clientes = pd.read_sql("SELECT id, nome, documento FROM clientes", engine)
    if not clientes.empty:
        dict_clientes = {f"{row['nome']} ({row['documento']})": row['id'] for _, row in clientes.iterrows()}
        cliente_sel = st.selectbox("Cliente", list(dict_clientes.keys()))
        with st.form("form_venda"):
            produto = st.text_input("Produto")
            valor = st.number_input("Valor Pago (R$)", min_value=0.0, format="%.2f")
            dt_compra = st.date_input("Data Compra", value=date.today())
            metodo = st.selectbox("Pagamento", ["Boleto", "Link Pgto", "Cartão de Crédito", "À Vista", "Parcelado"])
            status = st.selectbox("Status Envio", ["Pendente", "Postado", "Em Trânsito", "Entregue", "Atrasado"])

            if st.form_submit_button("Salvar Venda"):
                query = """
                    INSERT INTO vendas (cliente_id, produto, data_compra, valor_pago, metodo_pagamento, status_envio)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                with engine.connect() as conn:
                    conn.execute(query, (dict_clientes[cliente_sel], produto, dt_compra, valor, metodo, status))
                st.success("Venda registrada com sucesso!")

elif menu == "Atualizar Envio":
    st.header("🚚 Logística e Rastreio")
    df_pendentes = pd.read_sql('SELECT v.id, c.nome, v.produto, v.status_envio FROM vendas v JOIN clientes c ON v.cliente_id = c.id', engine)
    if not df_pendentes.empty:
        dict_vendas = {f"Pedido #{row['id']} - {row['nome']} ({row['produto']}) | Status: {row['status_envio']}": row['id'] for _, row in df_pendentes.iterrows()}
        venda_sel = st.selectbox("Selecione o Pedido", list(dict_vendas.keys()))
        novo_status = st.selectbox("Novo Status", ["Pendente", "Postado", "Em Trânsito", "Entregue", "Atrasado"])

        if st.button("Atualizar Status no Banco"):
            with engine.connect() as conn:
                conn.execute("UPDATE vendas SET status_envio = %s WHERE id = %s", (novo_status, dict_vendas[venda_sel]))
            st.success("Status de logística atualizado no Neon PostgreSQL!")

from correios_rastreio import rastrear
import streamlit as st
import pandas as pd

def consultar_status_correios(codigo_rastreio):
    """
    Busca o histórico de movimentação do pacote nos Correios.
    Retorna o último status e a data/hora da última atualização.
    """
    if not codigo_rastreio or len(codigo_rastreio.strip()) < 13:
        return "Código Inválido", "N/A"
    
    try:
        resultado = rastrear(codigo_rastreio.strip())
        if resultado and len(resultado) > 0:
            # O primeiro item do resultado é o evento mais recente
            ultimo_evento = resultado[0]
            status_atual = ultimo_evento.get('status', 'Em Trânsito')
            data_hora = f"{ultimo_evento.get('data', '')} {ultimo_evento.get('hora', '')}"
            return status_atual, data_hora
        else:
            return "Objeto não encontrado", "N/A"
    except Exception as e:
        return "Erro na consulta", "N/A"
