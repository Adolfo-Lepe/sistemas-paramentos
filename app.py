import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sqlalchemy import create_engine, text
from datetime import date
from correios_rastreio import rastrear

# ==============================================================================
# 1. CONEXÃO COM O BANCO DE DADOS (NEON POSTGRESQL)
# ==============================================================================
DATABASE_URL = os.environ.get("DATABASE_URL") or st.secrets.get("DATABASE_URL")

@st.cache_resource
def get_engine():
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url)

engine = get_engine()

# ==============================================================================
# 2. FUNÇÃO DE CONSULTA DOS CORREIOS
# ==============================================================================
def consultar_status_correios(codigo_rastreio):
    """Busca o último evento registrado no site dos Correios."""
    if not codigo_rastreio or len(str(codigo_rastreio).strip()) < 13:
        return "Código Inválido", "N/A"
    
    try:
        resultado = rastrear(str(codigo_rastreio).strip())
        if resultado and len(resultado) > 0:
            ultimo_evento = resultado[0]
            status_atual = ultimo_evento.get('status', 'Em Trânsito')
            data_hora = f"{ultimo_evento.get('data', '')} {ultimo_evento.get('hora', '')}"
            return status_atual, data_hora
        else:
            return "Objeto não encontrado", "N/A"
    except Exception as e:
        return "Erro na consulta", "N/A"

# ==============================================================================
# 3. INTERFACE PRINCIPAL DO STREAMLIT
# ==============================================================================
st.set_page_config(page_title="Paramentos Litúrgicos 24/7", layout="wide")
st.title("⛪ Gestão de Paramentos Litúrgicos & Logística")

menu = st.sidebar.selectbox("Menu", [
    "Dashboard", 
    "Cadastrar Cliente", 
    "Registrar Venda", 
    "Atualizar Envio"
])

# --- ABA 1: DASHBOARD ---
if menu == "Dashboard":
    st.header("📊 Painel de Vendas e Logística")
    df_vendas = pd.read_sql('''
        SELECT v.id, c.nome AS cliente, c.paroquia, v.produto, v.data_compra, 
               v.valor_pago, v.metodo_pagamento, v.status_envio, v.codigo_rastreio
        FROM vendas v JOIN clientes c ON v.cliente_id = c.id
    ''', engine)

    if not df_vendas.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Faturamento Total", f"R$ {df_vendas['valor_pago'].sum():,.2f}")
        col2.metric("Pedidos Enviados", len(df_vendas[df_vendas['status_envio'].isin(['Postado', 'Entregue'])]))
        col3.metric("Pendentes/Atrasados", len(df_vendas[df_vendas['status_envio'].isin(['Pendente', 'Atrasado'])]))

        st.divider()
        st.dataframe(df_vendas, use_container_width=True)
    else:
        st.info("Nenhuma venda cadastrada no banco de dados.")

# --- ABA 2: CADASTRAR CLIENTE ---
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
                query = text("""
                    INSERT INTO clientes (nome, tipo_doc, documento, data_nasc, data_ordenacao, paroquia, telefone, endereco)
                    VALUES (:nome, :tipo_doc, :doc, :data_nasc, :data_ord, :paroquia, :tel, :end)
                """)
                with engine.begin() as conn:
                    conn.execute(query, {
                        "nome": nome, "tipo_doc": tipo_doc, "doc": documento,
                        "data_nasc": data_nasc, "data_ord": data_ord,
                        "paroquia": paroquia, "tel": telefone, "end": endereco
                    })
                st.success("Cliente salvo com sucesso!")

# --- ABA 3: REGISTRAR VENDA ---
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
                query = text("""
                    INSERT INTO vendas (cliente_id, produto, data_compra, valor_pago, metodo_pagamento, status_envio)
                    VALUES (:cliente_id, :produto, :data_compra, :valor_pago, :metodo_pagamento, :status_envio)
                """)
                with engine.begin() as conn:
                    conn.execute(query, {
                        "cliente_id": dict_clientes[cliente_sel], "produto": produto,
                        "data_compra": dt_compra, "valor_pago": valor,
                        "metodo_pagamento": metodo, "status_envio": status
                    })
                st.success("Venda registrada com sucesso!")

# --- ABA 4: ATUALIZAR ENVIO & RASTREAMENTO CORREIOS ---
elif menu == "Atualizar Envio":
    st.header("🚚 Logística & Rastreamento Correios")
    
    # 1. Formulário para vincular Código de Rastreio
    st.subheader("📌 Cadastrar Código de Rastreio")
    df_vendas = pd.read_sql('''
        SELECT v.id, c.nome, v.produto, v.codigo_rastreio, v.status_envio 
        FROM vendas v JOIN clientes c ON v.cliente_id = c.id
    ''', engine)

    if not df_vendas.empty:
        dict_pedidos = {
            f"Pedido #{row['id']} - {row['nome']} ({row['produto']}) | Rastreio atual: {row['codigo_rastreio'] or 'Sem Código'}": row['id'] 
            for _, row in df_vendas.iterrows()
        }
        pedido_sel = st.selectbox("Selecione o Pedido", list(dict_pedidos.keys()))
        novo_codigo = st.text_input("Código de Rastreio Correios (Ex: AA123456789BR)").upper()

        if st.button("Salvar Código de Rastreio"):
            if novo_codigo:
                query = text("UPDATE vendas SET codigo_rastreio = :cod WHERE id = :id")
                with engine.begin() as conn:
                    conn.execute(query, {"cod": novo_codigo, "id": dict_pedidos[pedido_sel]})
                st.success(f"Código {novo_codigo} salvo!")
                st.rerun()

        st.divider()

        # 2. Atualização Automática
        st.subheader("🔄 Rastreamento Automático em Lote")
        df_para_rastrear = df_vendas[
            df_vendas['codigo_rastreio'].notnull() & 
            (df_vendas['codigo_rastreio'] != '') & 
            (df_vendas['status_envio'] != 'Entregue')
        ]

        if not df_para_rastrear.empty:
            if st.button("🔍 Sincronizar Todos com os Correios Agora"):
                progresso = st.progress(0)
                total = len(df_para_rastrear)

                for idx, (_, row) in enumerate(df_para_rastrear.iterrows()):
                    cod = row['codigo_rastreio']
                    status_novo, _ = consultar_status_correios(cod)
                    
                    query = text("UPDATE vendas SET status_envio = :status WHERE id = :id")
                    with engine.begin() as conn:
                        conn.execute(query, {"status": status_novo, "id": row['id']})
                    
                    progresso.progress((idx + 1) / total)

                st.success("Status atualizados com sucesso!")
                st.rerun()

            st.dataframe(df_para_rastrear[['id', 'nome', 'produto', 'codigo_rastreio', 'status_envio']], use_container_width=True)
        else:
            st.info("Nenhum pedido pendente de rastreamento com código cadastrado.")
