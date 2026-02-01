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

# ================= 🎨 极速 UI & 适配 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .stApp { background: #f2f2f7; }
    /* 顶部黑金大牌 */
    .hero-card {
        background: #1c1c1e; color: white; padding: 25px;
        border-radius: 24px; text-align: center; margin-bottom: 20px;
    }
    /* 指数卡片 */
    .index-card {
        background: white; padding: 15px; border-radius: 18px;
        text-align: center; border: 1px solid #e5e5ea; min-height: 100px;
    }
    /* 基金卡片 */
    .fund-card {
        background: white; padding: 18px; border-radius: 22px;
        margin-bottom: 12px; border: 1px solid #e5e5ea; color: #1c1c1e;
    }
    .status-tag {
        font-size: 11px; padding: 2px 8px; border-radius: 6px;
        background: #f2f2f7; color: #8e8e93; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# 60秒自动刷新
st_autorefresh(interval=60 * 1000, key="global_refresh")

# ================= 🗄️ 数据库逻辑 (确保不丢数据) =================
def init_db():
    conn = sqlite3.connect('zzl_final_v9.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    conn.commit()
    return conn

db_conn = init_db()

# ================= 🔧 性能级爬虫 (带报错拦截) =================
@st.cache_data(ttl=60)
def get_market_indices():
    indices = {"sh000001": "上证指数", "sz399006": "创业板指", "gb_ixic": "纳斯达克"}
    data = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join(indices.keys())}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1.2)
        lines = res.text.strip().split('\n')
        for i, (code, name) in enumerate(indices.items()):
            v = lines[i].split('="')[1].split(',')
            curr, last = float(v[3]), float(v[2])
            data.append({"name": name, "price": curr, "chg": (curr - last) / last * 100})
    except:
        return [{"name": "上证指数", "price": 0.0, "chg": 0.0}] * 3
    return data

@st.cache_data(ttl=3600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = (re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金-{code}", 0.0, "未知日期"

# ================= 🚪 身份验证系统 =================
if 'user_token' not in st.session_state:
    st.session_state.user_token = None
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

if not st.session_state.user_token:
    st.markdown('<div style="text-align:center; padding-top:50px;"><h1>📈 ZZL Pro</h1><p>数据云同步 · 输入 6 位识别码开启</p></div>', unsafe_allow_html=True)
    _, col_m, _ = st.columns([0.1, 0.8, 0.1])
    with col_m:
        tk = st.text_input("识别码", placeholder="例如: 888666", key="login_tk")
        c1, c2 = st.columns(2)
        if c1.button("🚀 开启系统", use_container_width=True, type="primary"):
            if tk:
                cur = db_conn.cursor()
                cur.execute('SELECT portfolio FROM users WHERE token=?', (tk,))
                res = cur.fetchone()
                st.session_state.user_token = tk
                st.session_state.portfolio = json.loads(res[0]) if res else []
                st.rerun()
        if c2.button("✨ 获取新码", use_container_width=True):
            new_tk = str(random.randint(100000, 999999))
            st.session_state.user_token = new_tk
            st.session_state.portfolio = []
            st.rerun()
    st.stop()

# ================= 📊 主流程 (登录成功后) =================

# 1. 大盘晴雨表 (解决空旷问题)
st.markdown("### 🌍 全球市场晴雨表")
m_data = get_market_indices()
cols = st.columns(3)
for idx, item in enumerate(m_data):
    color = "#ff3b30" if item['chg'] > 0 else "#34c759"
    cols[idx].markdown(f"""
        <div class="index-card">
            <div style="font-size:12px; color:#8e8e93;">{item['name']}</div>
            <div style="font-size:20px; font-weight:800; color:{color};">{item['price']:.2f}</div>
            <div style="font-size:12px; color:{color};">{item['chg']:+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# 2. 核心逻辑：判断是否休市
is_weekend = datetime.now().weekday() >= 5 # 5是周六，6是周日

# 3. 渲染资产概览和列表
if st.session_state.portfolio:
    total_m = sum(i['m'] for i in st.session_state.portfolio)
    total_profit = 0.0
    
    hero_placeholder = st.empty()
    
    st.markdown("### 📑 持仓明细")
    for idx, i in enumerate(st.session_state.portfolio):
        name, l_r, l_d = get_info(i['c'])
        # 周末逻辑：收益率为0，标注休市
        display_r = 0.0 if is_weekend else l_r # 此处可接实时估值爬虫
        total_profit += i['m'] * (display_r / 100) if not is_weekend else i['m'] * (l_r / 100)
        
        with st.container():
            c1, c2 = st.columns([0.88, 0.12])
            c1.markdown(f"💠 **{name}** ({i['c']})")
            if c2.button("✕", key=f"del_{idx}"):
                st.session_state.portfolio.pop(idx)
                cur = db_conn.cursor()
                cur.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
                db_conn.commit()
                st.rerun()
            
            status_tag = "休市(周五结)" if is_weekend else "实时预估"
            st.markdown(f"""
                <div class="fund-card" style="margin-top:-10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div>
                            <div class="status-tag">{status_tag}</div>
                            <div style="font-size:22px; font-weight:800; color:{'#ff3b30' if display_r>=0 else '#34c759'};">
                                {display_r:+.2f}%
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:10px; color:#8e8e93;">昨日结算 [{l_d}]</div>
                            <div style="font-size:18px; font-weight:700; color:{'#ff3b30' if l_r>=0 else '#34c759'};">
                                {l_r:+.2f}%
                            </div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # 渲染顶部总资产
    profit_val = total_profit if not is_weekend else sum(i['m']*(get_info(i['c'])[1]/100) for i in st.session_state.portfolio)
    hero_placeholder.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 13px; opacity: 0.8;">今日{'收益' if not is_weekend else '预估总收益'} (CNY)</div>
            <div style="font-size: 48px; font-weight: 900;">¥ {profit_val:+.2f}</div>
            <div style="font-size: 13px; opacity: 0.8;">本金合计 ¥{total_m:,.0f} | 识别码: {st.session_state.user_token}</div>
        </div>
    """, unsafe_allow_html=True)
else:
    st.info("💡 目前没有持仓数据，请在侧边栏添加。")

# ================= 🛠️ 侧边栏 =================
with st.sidebar:
    st.markdown(f"### 👤 用户: `{st.session_state.user_token}`")
    if st.button("🚪 退出"):
        st.session_state.user_token = None
        st.rerun()
    
    st.markdown("---")
    with st.form("add_fund", clear_on_submit=True):
        new_c = st.text_input("基金代码", placeholder="如: 014143")
        new_m = st.number_input("持有本金", value=10000.0, step=1000.0)
        if st.form_submit_button("确认添加持仓", use_container_width=True):
            if new_c:
                st.session_state.portfolio.append({"c": new_c, "m": new_m})
                cur = db_conn.cursor()
                cur.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
                db_conn.commit()
                st.rerun()
