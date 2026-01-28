import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
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
    
    # Tabela Usuários
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                 (username TEXT PRIMARY KEY, password TEXT, tipo TEXT)''')
    c.execute('SELECT count(*) FROM usuarios')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO usuarios VALUES (?, ?, ?)', ('admin', make_hashes('admin123'), 'admin'))
    
    # Tabela Funções
    c.execute('''CREATE TABLE IF NOT EXISTS funcoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_hora REAL)''')
    
    # Tabela Atendimentos (Completa)
    c.execute('''CREATE TABLE IF NOT EXISTS atendimentos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, inicio TEXT, termino TEXT, 
                  funcao TEXT, valor_total REAL, usuario_responsavel TEXT, detalhes TEXT,
                  paciente TEXT, periodo TEXT)''')
    conn.commit()
    conn.close()
    
    # Garante migração de versões antigas
    atualizar_banco_legado()

def atualizar_banco_legado():
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    colunas_novas = {'usuario_responsavel': 'TEXT', 'detalhes': 'TEXT', 'paciente': 'TEXT', 'periodo': 'TEXT'}
    for col, tipo in colunas_novas.items():
        try: pd.read_sql(f'SELECT {col} FROM atendimentos LIMIT 1', conn)
        except: 
            try: c.execute(f'ALTER TABLE atendimentos ADD COLUMN {col} {tipo}'); conn.commit()
            except: pass
    conn.close()

# --- LÓGICA DE PERÍODO ---
def calcular_periodo(hora_inicio):
    h = hora_inicio.hour
    if 0 <= h < 6: return "Madrugada"
    elif 6 <= h < 12: return "Manhã"
    elif 12 <= h < 18: return "Tarde"
    else: return "Noite"

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
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def criar_pdf_relatorio(df, mes_nome, ano, metricas, usuario, filtro_funcao):
    pdf = PDF('L', 'mm', 'A4')
    pdf.add_page()
    
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, f'Periodo: {mes_nome}/{ano} - Resp: {usuario}', 0, 1, 'L')
    
    pdf.set_fill_color(240, 240, 240)
    pdf.rect(10, 35, 277, 20, 'F')
    pdf.set_y(40)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 10, f"Faturamento: R$ {metricas['valor']:,.2f}   Horas: {metricas['horas']:.1f} h   Qtd: {metricas['qtd']}", 0, 1, 'C')
    pdf.ln(15)
    
    col_widths = [10, 28, 28, 40, 22, 30, 50, 25, 35] 
    headers = ['ID', 'Inicio', 'Termino', 'Paciente', 'Periodo', 'Funcao', 'Detalhes', 'Valor', 'Resp.']
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(200, 220, 255)
    for i, h in enumerate(headers): pdf.cell(col_widths[i], 10, h, 1, 0, 'C', 1)
    pdf.ln()
    
    pdf.set_font('Arial', '', 7)
    fill = False
    
    for index, row in df.iterrows():
        def clean(txt): return str(txt).encode('latin-1', 'replace').decode('latin-1')
        pdf.set_fill_color(245, 245, 245)
        
        det = str(row['detalhes']) if row['detalhes'] is not None else ""
        det_clean = clean(det)
        if len(det_clean) > 30: det_clean = det_clean[:30] + "..."
        
        str_inicio = row['inicio'].strftime('%d/%m %H:%M')
        str_termino = row['termino'].strftime('%d/%m %H:%M')

        pdf.cell(col_widths[0], 8, str(row['id']), 1, 0, 'C', fill)
        pdf.cell(col_widths[1], 8, str_inicio, 1, 0, 'C', fill)
        pdf.cell(col_widths[2], 8, str_termino, 1, 0, 'C', fill)
        pdf.cell(col_widths[3], 8, clean(row['paciente'])[:22], 1, 0, 'L', fill)
        pdf.cell(col_widths[4], 8, clean(row['periodo']), 1, 0, 'C', fill)
        pdf.cell(col_widths[5], 8, clean(row['funcao'])[:20], 1, 0, 'L', fill)
        pdf.cell(col_widths[6], 8, det_clean, 1, 0, 'L', fill)
        pdf.cell(col_widths[7], 8, f"{row['valor_total']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[8], 8, clean(row['usuario_responsavel']), 1, 0, 'L', fill)
        pdf.ln()
        fill = not fill
        
    return pdf.output(dest='S').encode('latin-1')

# --- CRUD BANCO DE DADOS ---
def login_user(username, password):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = ?', (username,))
    data = c.fetchall()
    conn.close()
    if data and check_hashes(password, data[0][1]): return data[0][2]
    return False

def criar_usuario(username, password, tipo):
    try:
        conn = sqlite3.connect('atendimentos.db')
        c = conn.cursor()
        c.execute('INSERT INTO usuarios VALUES (?, ?, ?)', (username, make_hashes(password), tipo))
        conn.commit(); conn.close()
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
    conn.commit(); conn.close()

def carregar_funcoes():
    conn = sqlite3.connect('atendimentos.db')
    df = pd.read_sql('SELECT * FROM funcoes', conn)
    conn.close()
    return df

def salvar_funcao(nome, valor):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('INSERT INTO funcoes (nome, valor_hora) VALUES (?, ?)', (nome, valor))
    conn.commit(); conn.close()

def atualizar_funcao_db(id_func, nome, valor):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('UPDATE funcoes SET nome=?, valor_hora=? WHERE id=?', (nome, valor, id_func))
    conn.commit(); conn.close()

def excluir_funcao_db(id_func):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('DELETE FROM funcoes WHERE id=?', (id_func,))
    conn.commit(); conn.close()

def salvar_atendimento(inicio, termino, funcao, valor_total, usuario, detalhes, paciente, periodo):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('''INSERT INTO atendimentos (inicio, termino, funcao, valor_total, usuario_responsavel, detalhes, paciente, periodo) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (inicio, termino, funcao, valor_total, usuario, detalhes, paciente, periodo))
    conn.commit(); conn.close()

def atualizar_atendimento_db(id_atend, inicio, termino, funcao, valor_total, detalhes, paciente, periodo):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('''UPDATE atendimentos 
                 SET inicio=?, termino=?, funcao=?, valor_total=?, detalhes=?, paciente=?, periodo=?
                 WHERE id=?''', 
              (inicio, termino, funcao, valor_total, detalhes, paciente, periodo, id_atend))
    conn.commit(); conn.close()

def excluir_atendimento_db(id_atend):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('DELETE FROM atendimentos WHERE id=?', (id_atend,))
    conn.commit(); conn.close()

def carregar_atendimentos():
    conn = sqlite3.connect('atendimentos.db')
    try:
        if st.session_state.get('tipo') == 'admin':
            query = 'SELECT * FROM atendimentos'
            df = pd.read_sql(query, conn)
        else:
            query = 'SELECT * FROM atendimentos WHERE usuario_responsavel = ?'
            df = pd.read_sql(query, conn, params=(st.session_state.get('usuario'),))
    except Exception as e:
        df = pd.DataFrame()
    finally:
        conn.close()
    
    if not df.empty:
        df['inicio'] = pd.to_datetime(df['inicio'])
        df['termino'] = pd.to_datetime(df['termino'])
        for col in ['usuario_responsavel', 'detalhes', 'paciente', 'periodo']:
            if col not in df.columns: df[col] = ''
            df[col] = df[col].fillna('')
            
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
        "Gerenciar": "✏️ Gerenciar (Editar/Excluir)",
        "Relatorios": "📊 Relatórios",
        "Admin": "⚙️ Administração"
    }
    
    lista_menu = [opcoes_menu["Funções"], opcoes_menu["Atendimento"], opcoes_menu["Gerenciar"], opcoes_menu["Relatorios"]]
    if st.session_state['tipo'] == 'admin': lista_menu.append(opcoes_menu["Admin"])
    menu = st.sidebar.radio("Navegue por aqui:", lista_menu)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Sair"):
        st.session_state.update({'logado': False, 'usuario': None, 'tipo': None})
        st.rerun()

    # TELA 01: FUNÇÕES
    if menu == opcoes_menu["Funções"]:
        st.title("🛠️ Cadastro de Funções")
        
        tab1, tab2 = st.tabs(["Cadastrar Nova", "Editar/Excluir Existente"])
        
        with tab1:
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

        with tab2:
            st.markdown("Selecione uma função para alterar o nome, valor ou excluir.")
            df_funcs = carregar_funcoes()
            if df_funcs.empty:
                st.info("Nenhuma função cadastrada para editar.")
            else:
                opcoes_funcs = df_funcs.apply(lambda x: f"ID {x['id']} | {x['nome']} (R$ {x['valor_hora']:.2f})", axis=1)
                func_sel_str = st.selectbox("Selecione a Função:", opcoes_funcs)
                id_func_sel = int(func_sel_str.split(" | ")[0].replace("ID ", ""))
                
                row_f = df_funcs[df_funcs['id'] == id_func_sel].iloc[0]
                
                with st.container(border=True):
                    with st.form("edit_funcao_form"):
                        ce1, ce2 = st.columns([2, 1])
                        novo_nome_f = ce1.text_input("Nome", value=row_f['nome'])
                        novo_valor_f = ce2.number_input("Valor Hora", value=row_f['valor_hora'], format="%.2f")
                        
                        col_save_f, col_del_f = st.columns(2)
                        btn_save_f = col_save_f.form_submit_button("💾 Atualizar Dados")
                        delete_check = col_del_f.checkbox("🗑️ Confirmar Exclusão")
                        btn_del_f = col_del_f.form_submit_button("Excluir Função")

                        if btn_save_f:
                            atualizar_funcao_db(id_func_sel, novo_nome_f, novo_valor_f)
                            st.success("Função atualizada!")
                            st.rerun()
                        
                        if btn_del_f:
                            if delete_check:
                                excluir_funcao_db(id_func_sel)
                                st.warning("Função excluída!")
                                st.rerun()
                            else:
                                st.error("Marque a caixa para confirmar exclusão.")

    # TELA 02: ATENDIMENTO
    elif menu == opcoes_menu["Atendimento"]:
        st.title("📝 Registrar Atendimento")
        df_func = carregar_funcoes()
        if df_func.empty:
            st.warning("⚠️ Cadastre funções primeiro.")
        else:
            with st.container(border=True):
                c1, c2 = st.columns(2)
                d_ini = c1.date_input("📅 Data Início")
                h_ini = c1.time_input("⏰ Hora Início", step=60)
                
                d_fim = c2.date_input("📅 Data Término")
                h_fim = c2.time_input("⏰ Hora Término", step=60)
                
                periodo_auto = calcular_periodo(h_ini)
                st.info(f"🕐 **Período Detectado:** {periodo_auto}")

                nome_paciente = st.text_input("👤 Nome Completo do Paciente")
                func = st.selectbox("💼 Selecione a Função", df_func['nome'].tolist())
                detalhes = st.text_area("📝 Detalhamento", placeholder="Descreva...")
                
                if st.button("✅ Salvar Atendimento"):
                    dt_ini = datetime.combine(d_ini, h_ini)
                    dt_fim = datetime.combine(d_fim, h_fim)
                    if not nome_paciente: st.error("❌ Nome do paciente obrigatório.")
                    elif dt_fim <= dt_ini: st.error("❌ Erro: Término deve ser depois do início.")
                    else:
                        duracao = (dt_fim - dt_ini).total_seconds() / 3600
                        val_h = df_func.loc[df_func['nome'] == func, 'valor_hora'].values[0]
                        total = duracao * val_h
                        salvar_atendimento(dt_ini, dt_fim, func, total, st.session_state['usuario'], detalhes, nome_paciente, periodo_auto)
                        st.success(f"✅ Salvo! Total: **R$ {total:,.2f}**")

    # TELA 03: GERENCIAR
    elif menu == opcoes_menu["Gerenciar"]:
        st.title("✏️ Gerenciar Registros")
        
        df = carregar_atendimentos()
        df_func = carregar_funcoes()
        
        if df.empty:
            st.info("Nenhum registro encontrado para editar.")
        else:
            st.markdown("### 1. Selecione o Registro")
            col_f1, col_f2 = st.columns(2)
            anos = sorted(df['inicio'].dt.year.unique())
            f_ano_edit = col_f1.selectbox("Filtrar Ano", anos, index=len(anos)-1, key="edit_ano")
            f_mes_edit = col_f2.selectbox("Filtrar Mês", range(1,13), index=datetime.now().month-1, key="edit_mes")
            
            df_edit_fil = df[(df['inicio'].dt.year == f_ano_edit) & (df['inicio'].dt.month == f_mes_edit)]
            
            if df_edit_fil.empty:
                st.warning("Nenhum registro neste mês.")
            else:
                opcoes_edit = df_edit_fil.apply(lambda x: f"ID {x['id']} | {x['inicio'].strftime('%d/%m')} | {x['paciente']} | {x['funcao']}", axis=1)
                registro_selecionado_str = st.selectbox("Escolha o atendimento para editar:", options=opcoes_edit)
                id_selecionado = int(registro_selecionado_str.split(" | ")[0].replace("ID ", ""))
                row = df[df['id'] == id_selecionado].iloc[0]
                
                st.divider()
                # AQUI ESTAVA O PROBLEMA: Substituído por st.warning nativo
                st.warning(f"📝 **Editando Registro ID: {id_selecionado}** — Paciente: **{row['paciente']}**")
                st.markdown("<br>", unsafe_allow_html=True)

                with st.form("form_edicao"):
                    c1, c2 = st.columns(2)
                    novo_d_ini = c1.date_input("Data Início", value=row['inicio'].date())
                    novo_h_ini = c1.time_input("Hora Início", value=row['inicio'].time(), step=60)
                    
                    novo_d_fim = c2.date_input("Data Término", value=row['termino'].date())
                    novo_h_fim = c2.time_input("Hora Término", value=row['termino'].time(), step=60)
                    
                    novo_paciente = st.text_input("Paciente", value=row['paciente'])
                    
                    lista_funcoes = df_func['nome'].tolist()
                    try: index_funcao = lista_funcoes.index(row['funcao'])
                    except: index_funcao = 0
                    nova_funcao = st.selectbox("Função", lista_funcoes, index=index_funcao)
                    novos_detalhes = st.text_area("Detalhes", value=row['detalhes'])
                    
                    btn_save = st.form_submit_button("💾 Salvar Alterações")
                
                if btn_save:
                    dt_ini = datetime.combine(novo_d_ini, novo_h_ini)
                    dt_fim = datetime.combine(novo_d_fim, novo_h_fim)
                    if dt_fim <= dt_ini: st.error("Erro: Data fim menor que início.")
                    else:
                        duracao = (dt_fim - dt_ini).total_seconds() / 3600
                        val_h = df_func.loc[df_func['nome'] == nova_funcao, 'valor_hora'].values[0]
                        novo_total = duracao * val_h
                        novo_periodo = calcular_periodo(novo_h_ini)
                        atualizar_atendimento_db(id_selecionado, dt_ini, dt_fim, nova_funcao, novo_total, novos_detalhes, novo_paciente, novo_periodo)
                        st.success("Registro atualizado com sucesso!")
                        st.rerun()

                st.markdown("---")
                with st.expander("🗑️ Área de Perigo (Excluir Registro)"):
                    st.warning(f"Tem certeza que deseja excluir ID {id_selecionado}?")
                    if st.button("Sim, Excluir Permanentemente", key="btn_excluir"):
                        excluir_atendimento_db(id_selecionado)
                        st.error("Registro excluído.")
                        st.rerun()

    # TELA 04: RELATÓRIOS
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
                if st.session_state['tipo'] == 'admin': c1, c2, c3, c4 = st.columns(4)
                else: c1, c2, c3 = st.columns(3); c4 = None
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
                df_show['inicio'] = df_show['inicio'].dt.strftime('%d/%m %H:%M')
                df_show['termino'] = df_show['termino'].dt.strftime('%d/%m %H:%M')
                
                df_display = df_show.copy()
                df_display['valor_total'] = df_display['valor_total'].apply(lambda x: f"R$ {x:,.2f}")
                cols = ['id', 'inicio', 'termino', 'paciente', 'periodo', 'funcao', 'detalhes', 'valor_total', 'usuario_responsavel']
                df_display = df_display[cols]
                df_display.columns = ['ID', 'Início', 'Término', 'Paciente', 'Período', 'Função', 'Detalhes', 'Valor', 'Resp.']
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                col_d1, col_d2 = st.columns(2)
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='xlsxwriter') as writer: df_fil.to_excel(writer, index=False)
                col_d1.download_button("📥 Baixar Excel", buffer_excel.getvalue(), f"Relatorio_{meses_dict[f_mes]}.xlsx", use_container_width=True)
                
                pdf_bytes = criar_pdf_relatorio(df_fil, meses_dict[f_mes], f_ano, metricas, st.session_state['usuario'], f_funcao)
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