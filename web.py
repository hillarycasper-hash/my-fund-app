import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import json
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 极速 UI (黑金 + 苹果风) =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: -apple-system, sans-serif !important; }
    .stApp { background: #0e0e0e; } /* 换成更有质感的深色底 */
    .hero-card {
        background: linear-gradient(135deg, #1c1c1e 0%, #3a3a3c 100%);
        color: white; padding: 30px 20px; border-radius: 24px;
        text-align: center; margin-bottom: 20px; border: 1px solid #333;
    }
    .fund-card {
        background: white; padding: 15px; border-radius: 20px;
        margin-bottom: 12px; border: 1px solid #e5e5ea; color: #1c1c1e;
    }
    .num-main { font-size: 22px; font-weight: 800; line-height: 1.2; }
    .stTextInput input { border-radius: 12px !important; background: #222 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=90 * 1000, key="global_refresh")

# ================= 🗄️ 数据库引擎 (数据永不丢失的核心) =================
def init_db():
    conn = sqlite3.connect('zzl_token_v1.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    conn.commit()
    return conn

db_conn = init_db()

def save_data(token, portfolio):
    c = db_conn.cursor()
    c.execute('INSERT OR REPLACE INTO users VALUES (?, ?)', (token, json.dumps(portfolio)))
    db_conn.commit()

def load_data(token):
    c = db_conn.cursor()
    c.execute('SELECT portfolio FROM users WHERE token=?', (token,))
    res = c.fetchone()
    return json.loads(res[0]) if res else None

# ================= 🔧 性能级爬虫 (保持原样) =================
@st.cache_data(ttl=3600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = (re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金-{code}", 0.0, ""

# (此处省略你代码中的 get_sina_price 和 calc_realtime 逻辑以节省篇幅，建议保留原样)
# ... [保留你原有的爬虫逻辑函数] ...

# ================= 🚪 身份验证流程 =================

if 'token' not in st.session_state:
    st.session_state.token = None

if not st.session_state.token:
    # 登录页
    st.markdown('<div style="text-align:center; padding-top:100px;"><h1 style="color:white; font-size:60px;">📈 ZZL</h1><p style="color:#888;">输入 6 位识别码开启资产看板</p></div>', unsafe_allow_html=True)
    
    _, col_m, _ = st.columns([0.1, 0.8, 0.1])
    with col_m:
        tk = st.text_input("识别码", placeholder="例如: 888666", label_visibility="collapsed")
        c1, c2 = st.columns(2)
        if c1.button("🚀 进入系统", use_container_width=True, type="primary"):
            if tk:
                data = load_data(tk)
                st.session_state.token = tk
                st.session_state.portfolio = data if data else []
                st.rerun()
        if c2.button("✨ 生成新码", use_container_width=True):
            new_tk = str(random.randint(100000, 999999))
            st.info(f"您的新识别码是: {new_tk} (请务必截图保存！)")
            st.session_state.token = new_tk
            st.session_state.portfolio = []
            save_data(new_tk, [])
            st.rerun()
    st.stop()

# ================= 📊 主流程 (登录后) =================

with st.sidebar:
    st.markdown(f"### 🆔 识别码: `{st.session_state.token}`")
    if st.button("🚪 退出登录"):
        st.session_state.token = None
        st.rerun()
    st.markdown("---")
    with st.form("add", clear_on_submit=True):
        c = st.text_input("代码", placeholder="013279")
        m = st.number_input("本金", value=10000.0)
        if st.form_submit_button("添加", use_container_width=True):
            if c:
                st.session_state.portfolio.append({"c": c, "m": m})
                save_data(st.session_state.token, st.session_state.portfolio) # 保存到数据库
                st.rerun()

# [这里接你原有的渲染逻辑，显示 hero-card 和循环生成 fund-card]
# 记得在删除按钮逻辑中也加入 save_data 同步数据库
