import streamlit as st
import requests
import re
import sqlite3
import json
import random
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 布局适配 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")
st_autorefresh(interval=60 * 1000, key="global_refresh") # 60秒自动刷新

st.markdown("""
    <style>
    .stApp { background: #f2f2f7; }
    .hero-card { background: #1c1c1e; color: white; padding: 25px; border-radius: 24px; text-align: center; margin-bottom: 20px; }
    .fund-card { background: white; padding: 18px; border-radius: 20px; margin-bottom: 12px; border: 1px solid #e5e5ea; }
    .num-bold { font-size: 24px; font-weight: 800; }
    .money-tag { font-size: 16px; font-weight: 600; margin-top: 5px; }
    .status-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: #eee; color: #8e8e93; }
    </style>
    """, unsafe_allow_html=True)

# ================= 🔧 增强版抓取引擎 =================
def init_db():
    conn = sqlite3.connect('zzl_pro_v12.db', check_same_thread=False)
    conn.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    return conn

db_conn = init_db()

@st.cache_data(ttl=60)
def get_fund_full_data(code):
    """同时从两个接口拿数据，确保 014143 这种代码不会漏掉"""
    try:
        # 接口1：获取名称和估值
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=2)
        name = re.search(r'nameFormat":"(.*?)"', r1.text).group(1) if "nameFormat" in r1.text else re.search(r'name":"(.*?)"', r1.text).group(1)
        
        # 接口2：获取昨日结算涨幅
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=2)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        l_r = float(tds[3].text.strip().replace("%",""))
        l_d = tds[0].text.strip()
        
        # 实时涨幅（如果是周末，接口1可能不准，这里做二次校验）
        r_r = float(re.search(r'gszzl":"(.*?)"', r1.text).group(1)) if "gszzl" in r1.text else 0.0
        
        return {"name": name, "last_r": l_r, "last_d": l_d, "real_r": r_r}
    except:
        return None

@st.cache_data(ttl=60)
def get_indices():
    indices = {"sh000001": "上证指数", "sz399006": "创业板指", "gb_ixic": "纳斯达克"}
    data = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join(indices.keys())}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1.5)
        lines = res.text.strip().split('\n')
        for i, (code, n) in enumerate(indices.items()):
            v = lines[i].split('="')[1].split(',')
            curr, last = float(v[3]), float(v[2])
            data.append({"name": n, "price": curr, "chg": (curr - last) / last * 100})
    except: pass
    return data

# ================= 🚪 登录系统 =================
if 'user_token' not in st.session_state: st.session_state.user_token = None

if not st.session_state.user_token:
    st.markdown("<h1 style='text-align:center;'>📈 ZZL Pro</h1>", unsafe_allow_html=True)
    tk = st.text_input("识别码", placeholder="输入码进入")
    if st.button("开启系统", use_container_width=True, type="primary"):
        res = db_conn.execute('SELECT portfolio FROM users WHERE token=?', (tk,)).fetchone()
        st.session_state.user_token = tk
        st.session_state.portfolio = json.loads(res[0]) if res else []
        st.rerun()
    if st.button("生成新码", use_container_width=True):
        new_tk = str(random.randint(100000, 999999))
        st.session_state.user_token = new_tk
        st.session_state.portfolio = []
        st.rerun()
    st.stop()

# ================= 📊 看板内容 =================
# 1. 顶部晴雨表
m_data = get_indices()
if m_data:
    cols = st.columns(3)
    for idx, item in enumerate(m_data):
        c = "#ff3b30" if item['chg'] > 0 else "#34c759"
        cols[idx].markdown(f"<div class='index-card'><div style='font-size:12px;color:#8e8e93;'>{item['name']}</div><div style='font-size:20px;font-weight:800;color:{c};'>{item['price']:.2f}</div><div style='font-size:12px;color:{c};'>{item['chg']:+.2f}%</div></div>", unsafe_allow_html=True)

# 2. 核心计算逻辑
is_weekend = datetime.now().weekday() >= 5
total_m = sum(float(i['m']) for i in st.session_state.portfolio)
total_p = 0.0
hero_placeholder = st.empty()

if not st.session_state.portfolio:
    st.info("💡 您的资产库为空，请点击侧边栏添加。")
else:
    for idx, i in enumerate(st.session_state.portfolio):
        data = get_fund_full_data(i['c'])
        if not data: continue
        
        # 周末逻辑：涨幅显示0，收益金额按周五算
        display_r = 0.0 if is_weekend else data['real_r']
        profit_money = i['m'] * (data['last_r'] / 100) if is_weekend else i['m'] * (data['real_r'] / 100)
        total_p += profit_money
        
        status = "休市(周五结)" if is_weekend else "实时预估"
        main_c = "#ff3b30" if (data['last_r'] if is_weekend else display_r) >= 0 else "#34c759"

        with st.container():
            c1, c2 = st.columns([0.9, 0.1])
            c1.markdown(f"💠 **{data['name']}** ({i['c']})")
            if c2.button("✕", key=f"del_{idx}"):
                st.session_state.portfolio.pop(idx)
                db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
                db_conn.commit()
                st.rerun()
            
            st.markdown(f"""
                <div class="fund-card" style="margin-top:-10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div>
                            <span class="status-tag">{status}</span>
                            <div class="num-bold" style="color:{main_c};">{display_r:+.2f}%</div>
                            <div class="money-tag" style="color:{main_c};">涨跌额: ¥ {profit_money:+.2f}</div>
                        </div>
                        <div style="text-align:right; border-left:1px solid #eee; padding-left:15px;">
                            <div style="font-size:10px; color:#8e8e93;">昨日结算 [{data['last_d']}]</div>
                            <div style="font-size:18px; font-weight:700; color:{'#ff3b30' if data['last_r']>=0 else '#34c759'};">
                                {data['last_r']:+.2f}%
                            </div>
                            <div style="font-size:12px; color:#8e8e93; margin-top:5px;">持仓: ¥ {float(i['m']):,.0f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

# 3. 总损益卡片
hero_placeholder.markdown(f"""
    <div class="hero-card">
        <div style="font-size: 13px; opacity: 0.8;">今日{'预估' if not is_weekend else '周五总结'}损益 (CNY)</div>
        <div style="font-size: 52px; font-weight: 900;">¥ {total_p:+.2f}</div>
        <div style="font-size: 14px; opacity: 0.9;">本金: ¥{total_m:,.0f} | 收益率: {(total_p/total_m*100) if total_m>0 else 0:+.2f}%</div>
    </div>
""", unsafe_allow_html=True)

# ================= 🛠️ 侧边栏 =================
with st.sidebar:
    st.markdown(f"🆔 用户: `{st.session_state.user_token}`")
    if st.button("退出登录"):
        st.session_state.user_token = None
        st.rerun()
    st.markdown("---")
    with st.form("add"):
        f_c = st.text_input("基金代码")
        f_m = st.number_input("持有本金", value=10000.0)
        if st.form_submit_button("验证并添加", use_container_width=True):
            with st.spinner('同步中...'):
                check = get_fund_full_data(f_c)
                if check:
                    st.session_state.portfolio.append({"c": f_c, "m": f_m})
                    db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
                    db_conn.commit()
                    st.rerun()
                else:
                    st.error("⚠️ 代码无效或系统繁忙，请重试！")
