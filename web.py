import streamlit as st
import requests
import sqlite3
import hashlib
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ================= 🎨 页面设定 =================
st.set_page_config(page_title="涨涨乐Pro-会员版", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .stApp { background: #f2f2f7; }
    .hero-card { background: linear-gradient(135deg, #1c1c1e 0%, #3a3a3c 100%); color: white; padding: 25px; border-radius: 24px; text-align: center; margin-bottom: 20px; }
    .fund-card { background: white; padding: 15px; border-radius: 20px; margin-bottom: 12px; border: 1px solid #e5e5ea; }
    .login-box { background: white; padding: 30px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# ================= 🗄️ 数据库逻辑 (用户信息与持仓) =================

def init_db():
    conn = sqlite3.connect('users_v3.db', check_same_thread=False)
    c = conn.cursor()
    # 用户表：用户名、哈希密码、持仓JSON
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT, portfolio TEXT)''')
    conn.commit()
    return conn

db_conn = init_db()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# ================= 🔐 登录系统状态管理 =================

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

def login_user(username, password):
    c = db_conn.cursor()
    c.execute('SELECT password FROM users WHERE username =?', (username,))
    data = c.fetchone()
    if data and check_hashes(password, data[0]):
        st.session_state.logged_in = True
        st.session_state.username = username
        return True
    return False

def register_user(username, password):
    c = db_conn.cursor()
    try:
        c.execute('INSERT INTO users(username, password, portfolio) VALUES (?,?,?)', 
                  (username, make_hashes(password), "[]"))
        db_conn.commit()
        return True
    except:
        return False

def update_db_portfolio():
    c = db_conn.cursor()
    p_json = json.dumps(st.session_state.portfolio)
    c.execute('UPDATE users SET portfolio = ? WHERE username = ?', (p_json, st.session_state.username))
    db_conn.commit()

def load_user_portfolio():
    c = db_conn.cursor()
    c.execute('SELECT portfolio FROM users WHERE username = ?', (st.session_state.username,))
    data = c.fetchone()
    return json.loads(data[0]) if data else []

# ================= 🔧 爬虫逻辑 (精简) =================

@st.cache_data(ttl=600)
def get_info(code):
    try:
        r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1).text
        name = re.search(r'name":"(.*?)"', r).group(1)
        return name
    except: return f"基金{code}"

# ================= 📺 界面逻辑 =================

if not st.session_state.logged_in:
    # --- 登录/注册界面 ---
    st.markdown('<div style="text-align:center; margin-top:50px;"><h1>📈 涨涨乐 Pro</h1><p>数据永久保存 · 随时随地查看</p></div>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔑 登录", "📝 注册账号"])
    
    with tab1:
        with st.form("login_form"):
            user = st.text_input("用户名")
            pwd = st.text_input("密码", type="password")
            if st.form_submit_button("立即登录", use_container_width=True):
                if login_user(user, pwd):
                    st.session_state.portfolio = load_user_portfolio()
                    st.rerun()
                else:
                    st.error("用户名或密码错误")
                    
    with tab2:
        with st.form("reg_form"):
            new_user = st.text_input("设置用户名")
            new_pwd = st.text_input("设置密码", type="password")
            if st.form_submit_button("注册并登录", use_container_width=True):
                if register_user(new_user, new_pwd):
                    st.success("注册成功！请切换到登录标签")
                else:
                    st.error("用户名已存在")

else:
    # --- 已登录：主程序界面 ---
    with st.sidebar:
        st.write(f"👤 您好, **{st.session_state.username}**")
        if st.button("🚪 退出登录"):
            st.session_state.logged_in = False
            st.rerun()
        
        st.markdown("---")
        with st.form("add_fund", clear_on_submit=True):
            c = st.text_input("基金代码")
            m = st.number_input("持有本金", value=1000.0)
            if st.form_submit_button("确认添加", use_container_width=True):
                if c:
                    st.session_state.portfolio.append({"c": c, "m": m})
                    update_db_portfolio() # 同步到数据库
                    st.rerun()

    # 显示资产卡片
    if st.session_state.portfolio:
        total_m = sum(float(i['m']) for i in st.session_state.portfolio)
        st.markdown(f'<div class="hero-card"><h3>当前账户总资产</h3><h1>¥ {total_m:,.2f}</h1></div>', unsafe_allow_html=True)
        
        for idx, i in enumerate(st.session_state.portfolio):
            name = get_info(i['c'])
            with st.container():
                col1, col2 = st.columns([0.85, 0.15])
                col1.markdown(f'<div class="fund-card"><b>{name}</b> ({i["c"]})<br>持有本金: ¥{i["m"]}</div>', unsafe_allow_html=True)
                if col2.button("🗑️", key=f"del_{idx}"):
                    st.session_state.portfolio.pop(idx)
                    update_db_portfolio()
                    st.rerun()
    else:
        st.info("您的账户暂无持仓，请在左侧侧边栏添加。")
