import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import hashlib
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ================= 🎨 1. 样式穿透引擎 (解决视觉问题) =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered")

def apply_ultra_css():
    st.markdown("""
        <style>
        .stApp { background-color: #0e0e0e !important; }
        div[data-testid="stVerticalBlock"] > div { background: transparent !important; border: none !important; }
        /* 强制输入框文字为白色 */
        input {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            background-color: rgba(255, 255, 255, 0.1) !important;
            border: 1px solid #444 !important;
            border-radius: 12px !important;
        }
        /* 按钮与卡片样式 */
        .stButton > button {
            background: linear-gradient(90deg, #d4af37, #f9d976) !important;
            color: #000 !important; font-weight: 800 !important; border-radius: 12px !important;
        }
        .hero-card { 
            background: linear-gradient(135deg, #1c1c1e 0%, #3a3a3c 100%); 
            color: white; padding: 25px; border-radius: 24px; text-align: center; margin-bottom: 20px;
        }
        .fund-card { 
            background: white; padding: 15px; border-radius: 18px; margin-bottom: 10px; border: 1px solid #e5e5ea; color: #1c1c1e;
        }
        </style>
    """, unsafe_allow_html=True)

# ================= 🗄️ 2. 数据库逻辑 =================
def init_db():
    conn = sqlite3.connect('zzl_final_v7.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, portfolio TEXT)')
    conn.commit()
    return conn

db_conn = init_db()
def make_hashes(pwd): return hashlib.sha256(str.encode(pwd)).hexdigest()
def check_hashes(pwd, hashed): return make_hashes(pwd) == hashed

# ================= 🔧 3. 基金爬虫与核心逻辑 =================
@st.cache_data(ttl=600)
def get_fund_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        name = re.search(r'name":"(.*?)"', r1.text).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金{code}", 0.0, "未知"

def get_sina_price(code):
    prefix = "sh" if code.startswith(('6', '5')) else "sz" if code.startswith(('0', '3', '1')) else "rt_hk" if len(code)==5 else ""
    try:
        res = requests.get(f"http://hq.sinajs.cn/list={prefix}{code}", headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        v = res.text.split('="')[1].split(',')
        curr, last = (float(v[6]), float(v[3])) if "hk" in prefix else (float(v[3]), float(v[2]))
        return ((curr - last) / last) * 100 if last > 0 else 0.0
    except: return 0.0

def calc_realtime(code, name):
    f = 0.99 if "指数" in name or "ETF" in name else 0.92
    try:
        res = requests.get(f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10", timeout=1.5)
        match = re.search(r'content:"(.*?)"', res.text)
        if match:
            soup = BeautifulSoup(match.group(1), 'html.parser')
            rows = soup.find_all("tr")[1:]
            h_data = [(r.find_all("td")[1].text.strip(), float(r.find_all("td")[-3].text.strip().replace("%",""))) for r in rows]
            with ThreadPoolExecutor(max_workers=5) as exe:
                prices = list(exe.map(get_sina_price, [d[0] for d in h_data]))
            return (sum(p*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data)) * f
    except: pass
    return 0.0

# ================= 📺 4. 界面逻辑 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    apply_ultra_css()
    st.markdown('<div style="text-align:center; padding:40px 0;"><h1 style="font-size:80px; font-weight:900; background:linear-gradient(#fff, #d4af37); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0;">ZZL</h1><p style="color:#666;">PRO 资产管理系统</p></div>', unsafe_allow_html=True)
    
    _, col_mid, _ = st.columns([0.1, 0.8, 0.1])
    with col_mid:
        tab_login, tab_reg = st.tabs(["🔑 登录", "✨ 注册"])
        with tab_login:
            u = st.text_input("账号", key="l_u")
            p = st.text_input("密码", type="password", key="l_p")
            if st.button("进入系统", use_container_width=True):
                cur = db_conn.cursor()
                cur.execute('SELECT password, portfolio FROM users WHERE username=?', (u,))
                res = cur.fetchone()
                if res and check_hashes(p, res[0]):
                    st.session_state.logged_in, st.session_state.username = True, u
                    st.session_state.portfolio = json.loads(res[1])
                    st.rerun()
                else: st.error("账号或密码有误")
        with tab_reg:
            nu = st.text_input("设置账号", key="r_u")
            np = st.text_input("设置密码", type="password", key="r_p")
            if st.button("创建账户", use_container_width=True):
                if nu and np:
                    cur = db_conn.cursor()
                    cur.execute('SELECT username FROM users WHERE username=?', (nu,))
                    if cur.fetchone(): st.error("用户名已存在")
                    else:
                        cur.execute('INSERT INTO users VALUES (?,?,?)', (nu, make_hashes(np), "[]"))
                        db_conn.commit()
                        st.success("注册成功！请登录")
else:
    # --- 登录成功后的主看板 ---
    with st.sidebar:
        st.write(f"👤 用户: **{st.session_state.username}**")
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.rerun()
        st.markdown("---")
        with st.form("add"):
            c = st.text_input("代码")
            m = st.number_input("本金", value=10000.0)
            if st.form_submit_button("添加持仓"):
                st.session_state.portfolio.append({"c": c, "m": m})
                cur = db_conn.cursor()
                cur.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(st.session_state.portfolio), st.session_state.username))
                db_conn.commit()
                st.rerun()

    # 展示逻辑
    if st.session_state.portfolio:
        total_profit = 0.0
        total_m = sum(i['m'] for i in st.session_state.portfolio)
        is_weekend = datetime.now().weekday() >= 5
        
        # 预留总收益卡片位置
        hero = st.empty()
        
        for idx, i in enumerate(st.session_state.portfolio):
            name, l_r, l_d = get_fund_info(i['c'])
            r_r = l_r if is_weekend else calc_realtime(i['c'], name)
            profit = i['m'] * (r_r / 100)
            total_profit += profit
            
            with st.container():
                col_f, col_d = st.columns([0.85, 0.15])
                col_f.markdown(f"""
                <div class="fund-card">
                    <b>{name}</b> ({i['c']})<br>
                    <span style="color:{'#ff3b30' if r_r>0 else '#34c759'}; font-size:1.2rem; font-weight:bold;">
                        {r_r:+.2f}% (¥{profit:+.2f})
                    </span>
                </div>
                """, unsafe_allow_html=True)
                if col_d.button("✕", key=f"del_{idx}"):
                    st.session_state.portfolio.pop(idx)
                    cur = db_conn.cursor()
                    cur.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(st.session_state.portfolio), st.session_state.username))
                    db_conn.commit()
                    st.rerun()
        
        hero.markdown(f"""
            <div class="hero-card">
                <p style="margin:0; opacity:0.8;">预估总收益</p>
                <h1 style="margin:0; font-size:3rem;">¥ {total_profit:+.2f}</h1>
                <p style="margin:0; opacity:0.8;">本金: ¥{total_m:,.0f} | 收益率: {(total_profit/total_m*100):+.2f}%</p>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.info("点左侧添加持仓，数据会自动同步到云端。")
