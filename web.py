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

# ================= 🎨 极速 UI 定制 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: -apple-system, sans-serif !important; }
    .stApp { background: #f2f2f7; }
    .hero-card {
        background: #1c1c1e; color: white; padding: 25px;
        border-radius: 24px; text-align: center; margin-bottom: 20px;
    }
    .fund-card {
        background: white; padding: 15px; border-radius: 20px;
        margin-bottom: 12px; border: 1px solid #e5e5ea;
    }
    .num-main { font-size: 22px; font-weight: 800; line-height: 1.2; }
    /* 强制按钮样式 */
    .stButton > button { border-radius: 12px !important; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=90 * 1000, key="global_refresh")

# ================= 🗄️ 数据库核心 (物理存储) =================
def init_db():
    conn = sqlite3.connect('zzl_storage_v2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    conn.commit()
    return conn

db_conn = init_db()

def db_save(token, data):
    c = db_conn.cursor()
    c.execute('INSERT OR REPLACE INTO users VALUES (?, ?)', (token, json.dumps(data)))
    db_conn.commit()

def db_load(token):
    c = db_conn.cursor()
    c.execute('SELECT portfolio FROM users WHERE token=?', (token,))
    res = c.fetchone()
    return json.loads(res[0]) if res else None

# ================= 🔧 爬虫引擎 =================
@st.cache_data(ttl=600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = (re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金-{code}", 0.0, ""

def get_sina_price(code):
    prefix = "sh" if code.startswith(('6', '5')) else "sz" if code.startswith(('0', '3', '1')) else "rt_hk" if len(code)==5 else ""
    try:
        res = requests.get(f"http://hq.sinajs.cn/list={prefix}{code}", headers={'Referer': 'https://finance.sina.com.cn'}, timeout=0.8)
        v = res.text.split('="')[1].split(',')
        curr, last = (float(v[6]), float(v[3])) if "hk" in prefix else (float(v[3]), float(v[2]))
        return ((curr - last) / last) * 100 if last > 0 else 0.0, (v[-4] if "hk" not in prefix else v[-2])
    except: return 0.0, ""

def calc_realtime(code, name):
    f = 0.99 if any(x in name for x in ["指数", "ETF", "纳指", "标普"]) else 0.92
    try:
        res = requests.get(f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10", timeout=1.2)
        match = re.search(r'content:"(.*?)"', res.text)
        if match:
            soup = BeautifulSoup(match.group(1), 'html.parser')
            rows = soup.find_all("tr")[1:]
            h_data = [(r.find_all("td")[1].text.strip(), float(r.find_all("td")[-3].text.strip().replace("%",""))) for r in rows]
            with ThreadPoolExecutor(max_workers=5) as exe:
                prices = list(exe.map(get_sina_price, [d[0] for d in h_data]))
            return sum(p[0]*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data) * f, prices[0][1]
    except: pass
    return 0.0, ""

# ================= 🚪 登录/身份逻辑 =================
if 'user_token' not in st.session_state:
    st.session_state.user_token = None

if not st.session_state.user_token:
    st.markdown('<div style="text-align:center; padding-top:50px;"><h1>📈 ZZL Pro</h1><p>数据已存入云端，请输入识别码找回</p></div>', unsafe_allow_html=True)
    
    with st.container():
        input_token = st.text_input("请输入您的 6 位识别码", placeholder="初次使用请点击下方生成", key="token_input")
        c1, c2 = st.columns(2)
        if c1.button("🚀 开启看盘", use_container_width=True, type="primary"):
            if input_token:
                loaded_data = db_load(input_token)
                st.session_state.user_token = input_token
                st.session_state.portfolio = loaded_data if loaded_data else []
                st.rerun()
            else: st.warning("请输入码")
        
        if c2.button("✨ 获取新码", use_container_width=True):
            new_code = str(random.randint(100000, 999999))
            db_save(new_code, []) # 预创建
            st.success(f"您的识别码: {new_code} (请记住它！)")
            st.session_state.user_token = new_code
            st.session_state.portfolio = []
            st.rerun()
    st.stop()

# ================= 📊 主看板逻辑 =================
with st.sidebar:
    st.markdown(f"### 🆔 识别码: `{st.session_state.user_token}`")
    if st.button("🚪 退出登录"):
        st.session_state.user_token = None
        st.rerun()
    
    st.markdown("---")
    with st.form("add_form", clear_on_submit=True):
        c = st.text_input("基金代码")
        m = st.number_input("持有本金", value=10000.0)
        if st.form_submit_button("确认添加", use_container_width=True):
            if c:
                st.session_state.portfolio.append({"c": c, "m": m})
                db_save(st.session_state.user_token, st.session_state.portfolio)
                st.rerun()

# 渲染看板
if st.session_state.portfolio:
    total_m = sum(i['m'] for i in st.session_state.portfolio)
    mixed_p = 0.0
    is_weekend = datetime.now().weekday() >= 5
    
    hero_placeholder = st.empty()
    
    for idx, i in enumerate(st.session_state.portfolio):
        name, l_r, l_d = get_info(i['c'])
        r_r, s_d = calc_realtime(i['c'], name)
        eff_r = l_r if is_weekend else (l_r if l_d == datetime.now().strftime('%Y-%m-%d') else r_r)
        mixed_p += i['m'] * (eff_r / 100)
        
        with st.container():
            c1, c2 = st.columns([0.9, 0.1])
            c1.markdown(f"💠 **{name}** ({i['c']})")
            if c2.button("✕", key=f"del_{idx}"):
                st.session_state.portfolio.pop(idx)
                db_save(st.session_state.user_token, st.session_state.portfolio)
                st.rerun()
            
            st.markdown(f"""
                <div class="fund-card" style="margin-top:-10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div>
                            <div style="font-size:10px; color:#8e8e93;">估值 [{s_d or '获取中'}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if r_r>0 else '#34c759'};">{r_r:+.2f}%</div>
                            <div style="font-size:12px; color:{'#ff3b30' if r_r>0 else '#34c759'};">¥ {i['m']*r_r/100:+.2f}</div>
                        </div>
                        <div style="border-left:1px solid #f2f2f7; padding-left:15px;">
                            <div style="font-size:10px; color:#8e8e93;">昨结 [{l_d}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if l_r>0 else '#34c759'};">{l_r:+.2f}%</div>
                            <div style="font-size:12px; color:{'#ff3b30' if l_r>0 else '#34c759'};">¥ {i['m']*l_r/100:+.2f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    hero_placeholder.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 48px; font-weight: 900;">¥ {mixed_p:+.2f}</div>
            <div style="font-size: 13px; opacity: 0.8;">本金合计 ¥{total_m:,.0f} | 预估收益率 {(mixed_p/total_m*100):+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)
else:
    st.info("💡 您的资产库为空，请点击左侧添加。")
