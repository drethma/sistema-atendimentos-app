import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
import hashlib
from fpdf import FPDF

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Gestão de Atendimentos", 
    page_icon="💼", 
    layout="wide"
)

# --- ESTILIZAÇÃO ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap');
    
    html, body, h1, h2, h3, h4, h5, h6, p, li, ol, .stButton button, .stTextInput, .stSelectbox, .stTextArea {
        font-family: 'Open Sans', sans-serif !important;
    }
    
    [data-testid="stMetricValue"] {
        font-weight: 700;
        color: #4da6ff;
    }
    
    .stButton button {
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNÇÕES DE SEGURANÇA ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return True
    return False

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                 (username TEXT PRIMARY KEY, password TEXT, tipo TEXT)''')
    c.execute('SELECT count(*) FROM usuarios')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO usuarios VALUES (?, ?, ?)', ('admin', make_hashes('admin123'), 'admin'))
    
    c.execute('''CREATE TABLE IF NOT EXISTS funcoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_hora REAL)''')
    
    # Tabela com a nova coluna 'detalhes'
    c.execute('''CREATE TABLE IF NOT EXISTS atendimentos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, inicio TEXT, termino TEXT, 
                  funcao TEXT, valor_total REAL, usuario_responsavel TEXT, detalhes TEXT)''')
    conn.commit()
    conn.close()
    
    # Atualiza bancos antigos automaticamente
    atualizar_banco_legado()

def atualizar_banco_legado():
    """Verifica e cria colunas novas em bancos antigos"""
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    
    # 1. Verifica coluna usuario_responsavel
    try:
        pd.read_sql('SELECT usuario_responsavel FROM atendimentos LIMIT 1', conn)
    except:
        try: c.execute('ALTER TABLE atendimentos ADD COLUMN usuario_responsavel TEXT'); conn.commit()
        except: pass

    # 2. Verifica coluna detalhes (NOVA)
    try:
        pd.read_sql('SELECT detalhes FROM atendimentos LIMIT 1', conn)
    except:
        try: c.execute('ALTER TABLE atendimentos ADD COLUMN detalhes TEXT'); conn.commit()
        except: pass
        
    conn.close()

# --- PDF ---
class PDF(FPDF):
    def header(self):
        self.set_fill_color(77, 166, 255)
        self.rect(0, 0, 297, 25, 'F')
        self.set_font('Arial', 'B', 15)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, 'Relatório de Atendimentos', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Pagina {self.page_no()}' + ' - Sistema de Gestão', 0, 0, 'C')

def criar_pdf_relatorio(df, mes_nome, ano, metricas, usuario, filtro_funcao):
    pdf = PDF('L', 'mm', 'A4')
    pdf.add_page()
    
    # Resumo
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    subtitulo = f'Periodo: {mes_nome} / {ano} - Usuario: {usuario}'
    if filtro_funcao != 'Todas': subtitulo += f' - Funcao: {filtro_funcao}'
    pdf.cell(0, 10, subtitulo, 0, 1, 'L')
    
    pdf.set_fill_color(240, 240, 240)
    pdf.rect(10, 35, 277, 20, 'F')
    pdf.set_y(40)
    pdf.set_font('Arial', '', 11)
    texto_resumo = f"     Faturamento: R$ {metricas['valor']:,.2f}          Horas: {metricas['horas']:.1f} h          Qtd: {metricas['qtd']}"
    pdf.cell(0, 10, texto_resumo, 0, 1, 'C')
    pdf.ln(15)

    # Tabela (Com nova coluna Detalhes e larguras ajustadas)
    # Total disponível: ~277mm
    # [ID, Inicio, Termino, Funcao, Detalhes, Valor, Resp]
    col_widths = [12, 35, 35, 40, 80, 30, 45] 
    headers = ['ID', 'Inicio', 'Termino', 'Funcao', 'Detalhamento', 'Valor', 'Resp.']
    
    pdf.set_font('Arial', 'B', 9) # Fonte um pouco menor para caber tudo
    pdf.set_fill_color(200, 220, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 10, h, 1, 0, 'C', 1)
    pdf.ln()
    
    pdf.set_font('Arial', '', 8)
    fill = False
    
    for index, row in df.iterrows():
        def clean(txt):
            return str(txt).encode('latin-1', 'replace').decode('latin-1')

        pdf.set_fill_color(245, 245, 245)
        
        # Limita o tamanho do texto para não quebrar o PDF se for muito grande
        detalhe_texto = clean(row['detalhes'])
        if len(detalhe_texto) > 45: detalhe_texto = detalhe_texto[:45] + "..."

        pdf.cell(col_widths[0], 8, str(row['id']), 1, 0, 'C', fill)
        pdf.cell(col_widths[1], 8, str(row['inicio']), 1, 0, 'C', fill)
        pdf.cell(col_widths[2], 8, str(row['termino']), 1, 0, 'C', fill)
        pdf.cell(col_widths[3], 8, clean(row['funcao']), 1, 0, 'L', fill)
        pdf.cell(col_widths[4], 8, detalhe_texto, 1, 0, 'L', fill) # Nova Coluna
        pdf.cell(col_widths[5], 8, f"R$ {row['valor_total']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[6], 8, clean(row['usuario_responsavel']), 1, 0, 'L', fill)
        pdf.ln()
        fill = not fill
        
    return pdf.output(dest='S').encode('latin-1')

# --- CRUD ---
def login_user(username, password):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = ?', (username,))
    data = c.fetchall()
    conn.close()
    if data and check_hashes(password, data[0][1]):
        return data[0][2]
    return False

def criar_usuario(username, password, tipo):
    try:
        conn = sqlite3.connect('atendimentos.db')
        c = conn.cursor()
        c.execute('INSERT INTO usuarios VALUES (?, ?, ?)', (username, make_hashes(password), tipo))
        conn.commit()
        conn.close()
        return True
    except: return False

def listar_usuarios():
    conn = sqlite3.connect('atendimentos.db')
    df = pd.read_sql('SELECT username, tipo FROM usuarios', conn)
    conn.close()
    return df

def excluir_usuario(username):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('DELETE FROM usuarios WHERE username = ?', (username,))
    conn.commit()
    conn.close()

def carregar_funcoes():
    conn = sqlite3.connect('atendimentos.db')
    df = pd.read_sql('SELECT * FROM funcoes', conn)
    conn.close()
    return df

def salvar_funcao(nome, valor):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('INSERT INTO funcoes (nome, valor_hora) VALUES (?, ?)', (nome, valor))
    conn.commit()
    conn.close()

def salvar_atendimento(inicio, termino, funcao, valor_total, usuario, detalhes):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('''INSERT INTO atendimentos (inicio, termino, funcao, valor_total, usuario_responsavel, detalhes) 
                 VALUES (?, ?, ?, ?, ?, ?)''', 
              (inicio, termino, funcao, valor_total, usuario, detalhes))
    conn.commit()
    conn.close()

def carregar_atendimentos():
    conn = sqlite3.connect('atendimentos.db')
    if st.session_state.get('tipo') == 'admin':
        query = 'SELECT * FROM atendimentos'
        params = ()
    else:
        query = 'SELECT * FROM atendimentos WHERE usuario_responsavel = ?'
        params = (st.session_state.get('usuario'),)
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    if not df.empty:
        df['inicio'] = pd.to_datetime(df['inicio'])
        df['termino'] = pd.to_datetime(df['termino'])
        if 'usuario_responsavel' not in df.columns: df['usuario_responsavel'] = 'N/A'
        if 'detalhes' not in df.columns: df['detalhes'] = '' # Garante que não quebra se vazio
        df['detalhes'] = df['detalhes'].fillna('')
    return df

# Inicializa
init_db()

# --- SESSÃO ---
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'usuario': None, 'tipo': None})

# --- LOGIN ---
if not st.session_state['logado']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.title("🔐 Acesso Restrito")
        st.markdown("Bem-vindo ao sistema de **Gestão de Atendimentos**.")
        with st.form("login_form"):
            usuario = st.text_input("👤 Usuário")
            senha = st.text_input("🔑 Senha", type="password")
            if st.form_submit_button("🚀 Entrar"):
                tipo = login_user(usuario, senha)
                if tipo:
                    st.session_state.update({'logado': True, 'usuario': usuario, 'tipo': tipo})
                    st.rerun()
                else: st.error("Acesso negado.")

# --- SISTEMA ---
else:
    st.sidebar.title("Menu")
    st.sidebar.markdown(f"👤 **{st.session_state['usuario']}**")
    st.sidebar.caption(f"Acesso: {st.session_state['tipo'].upper()}")
    
    opcoes_menu = {
        "Funções": "🛠️ Cadastro Função",
        "Atendimento": "📝 Novo Atendimento",
        "Relatorios": "📊 Relatórios",
        "Admin": "⚙️ Administração"
    }
    
    lista_menu = [opcoes_menu["Funções"], opcoes_menu["Atendimento"], opcoes_menu["Relatorios"]]
    if st.session_state['tipo'] == 'admin': lista_menu.append(opcoes_menu["Admin"])
    menu = st.sidebar.radio("Navegue por aqui:", lista_menu)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Sair"):
        st.session_state.update({'logado': False, 'usuario': None, 'tipo': None})
        st.rerun()

    # TELA 01
    if menu == opcoes_menu["Funções"]:
        st.title("🛠️ Cadastro de Funções")
        with st.container(border=True):
            with st.form("form_funcao", clear_on_submit=True):
                c1, c2 = st.columns([2, 1])
                nome = c1.text_input("Nome do Cargo/Função")
                valor = c2.number_input("Valor Hora (R$)", min_value=0.0, format="%.2f")
                if st.form_submit_button("💾 Salvar"):
                    if nome and valor > 0:
                        salvar_funcao(nome, valor)
                        st.success(f"✅ '{nome}' cadastrado!")
        st.subheader("📋 Funções Ativas")
        df = carregar_funcoes()
        if not df.empty: st.dataframe(df, hide_index=True, use_container_width=True)

    # TELA 02
    elif menu == opcoes_menu["Atendimento"]:
        st.title("📝 Registrar Atendimento")
        df_func = carregar_funcoes()
        if df_func.empty:
            st.warning("⚠️ Cadastre funções primeiro.")
        else:
            with st.container(border=True):
                with st.form("form_atend", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    d_ini = c1.date_input("📅 Data Início")
                    h_ini = c1.time_input("⏰ Hora Início")
                    d_fim = c2.date_input("📅 Data Término")
                    h_fim = c2.time_input("⏰ Hora Término")
                    func = st.selectbox("💼 Selecione a Função", df_func['nome'].tolist())
                    
                    # NOVO CAMPO DE DETALHES
                    detalhes = st.text_area("📝 Detalhamento do Atendimento", placeholder="Descreva aqui o que foi realizado...")
                    
                    if st.form_submit_button("✅ Salvar Atendimento"):
                        dt_ini = datetime.combine(d_ini, h_ini)
                        dt_fim = datetime.combine(d_fim, h_fim)
                        if dt_fim <= dt_ini:
                            st.error("❌ Erro: Término deve ser depois do início.")
                        else:
                            duracao = (dt_fim - dt_ini).total_seconds() / 3600
                            val_h = df_func.loc[df_func['nome'] == func, 'valor_hora'].values[0]
                            total = duracao * val_h
                            salvar_atendimento(dt_ini, dt_fim, func, total, st.session_state['usuario'], detalhes)
                            st.success(f"✅ Salvo! Total: **R$ {total:,.2f}**")

    # TELA 03
    elif menu == opcoes_menu["Relatorios"]:
        st.title("📊 Relatórios Gerenciais")
        if st.session_state['tipo'] != 'admin': st.info(f"🔒 Dados de: **{st.session_state['usuario']}**")
        else: st.success("🔓 Modo Admin: Visualizando TUDO.")
            
        df = carregar_atendimentos()
        if not df.empty:
            anos = sorted(df['inicio'].dt.year.unique())
            meses_dict = {1:"Janeiro", 2:"Fevereiro", 3:"Marco", 4:"Abril", 5:"Maio", 6:"Junho",
                          7:"Julho", 8:"Agosto", 9:"Setembro", 10:"Outubro", 11:"Novembro", 12:"Dezembro"}
            
            with st.container(border=True):
                if st.session_state['tipo'] == 'admin':
                    c1, c2, c3, c4 = st.columns(4)
                else:
                    c1, c2, c3 = st.columns(3); c4 = None

                f_ano = c1.selectbox("📅 Ano", anos, index=len(anos)-1)
                f_mes = c2.selectbox("🗓️ Mês", range(1,13), format_func=lambda x: meses_dict[x], index=datetime.now().month-1)
                opcoes_funcoes = ['Todas'] + sorted(df['funcao'].unique().tolist())
                f_funcao = c3.selectbox("💼 Função", opcoes_funcoes)

                f_usuario = 'Todos'
                if st.session_state['tipo'] == 'admin':
                    lista_users = ['Todos'] + sorted(df['usuario_responsavel'].astype(str).unique().tolist())
                    f_usuario = c4.selectbox("👤 Usuário", lista_users)

            df_fil = df[(df['inicio'].dt.year == f_ano) & (df['inicio'].dt.month == f_mes)]
            if f_funcao != 'Todas': df_fil = df_fil[df_fil['funcao'] == f_funcao]
            if st.session_state['tipo'] == 'admin' and f_usuario != 'Todos':
                df_fil = df_fil[df_fil['usuario_responsavel'] == f_usuario]
            
            if not df_fil.empty:
                total_val = df_fil['valor_total'].sum()
                total_horas = (df_fil['termino']-df_fil['inicio']).dt.total_seconds().sum()/3600
                total_qtd = len(df_fil)
                metricas = {'valor': total_val, 'horas': total_horas, 'qtd': total_qtd}

                st.markdown(f"### 📈 Resumo: {meses_dict[f_mes]} / {f_ano}")
                k1, k2, k3 = st.columns(3)
                k1.metric("💰 Faturamento", f"R$ {total_val:,.2f}")
                k2.metric("⏱️ Horas Totais", f"{total_horas:.1f} h")
                k3.metric("📂 Atendimentos", total_qtd)
                st.divider()
                
                df_show = df_fil.copy()
                df_show['inicio'] = df_show['inicio'].dt.strftime('%d/%m/%Y %H:%M')
                df_show['termino'] = df_show['termino'].dt.strftime('%d/%m/%Y %H:%M')
                
                df_display = df_show.copy()
                df_display['valor_total'] = df_display['valor_total'].apply(lambda x: f"R$ {x:,.2f}")
                # Reordenando para incluir Detalhes
                cols = ['id', 'inicio', 'termino', 'funcao', 'detalhes', 'valor_total', 'usuario_responsavel']
                df_display = df_display[cols]
                df_display.columns = ['ID', 'Início', 'Término', 'Função', 'Detalhamento', 'Valor Total', 'Responsável']
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                
                col_d1, col_d2 = st.columns(2)
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='xlsxwriter') as writer: df_fil.to_excel(writer, index=False)
                col_d1.download_button("📥 Baixar Excel", buffer_excel.getvalue(), f"Relatorio_{meses_dict[f_mes]}.xlsx", use_container_width=True)
                
                pdf_bytes = criar_pdf_relatorio(df_show, meses_dict[f_mes], f_ano, metricas, st.session_state['usuario'], f_funcao)
                col_d2.download_button("📄 Baixar PDF", pdf_bytes, f"Relatorio_{meses_dict[f_mes]}.pdf", mime='application/pdf', use_container_width=True)
            else: st.info("Sem dados.")
        else: st.info("Sem registros.")

    # TELA ADMIN
    elif menu == opcoes_menu["Admin"]:
        st.title("⚙️ Administração")
        with st.expander("➕ Novo Usuário", expanded=True):
            with st.form("new_user"):
                u = st.text_input("Login"); p = st.text_input("Senha", type="password"); t = st.selectbox("Nível", ["comum", "admin"])
                if st.form_submit_button("Criar"):
                    if u and p: 
                        if criar_usuario(u, p, t): st.success("✅ Criado!")
                        else: st.error("❌ Erro.")
        st.subheader("👥 Usuários")
        for i, row in listar_usuarios().iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"👤 **{row['username']}**"); c2.caption(f"Tipo: {row['tipo']}")
            if row['username'] != 'admin':
                if c3.button("🗑️", key=f"del_{row['username']}"): excluir_usuario(row['username']); st.rerun()