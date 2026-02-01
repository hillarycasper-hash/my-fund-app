import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import json
import random
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 布局与自动刷新 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

# 每60秒全自动静默刷新
st_autorefresh(interval=60 * 1000, key="global_refresh")

st.markdown("""
    <style>
    .stApp { background: #f2f2f7; }
    .hero-card { background: #1c1c1e; color: white; padding: 25px; border-radius: 24px; text-align: center; margin-bottom: 20px; }
    .index-card { background: white; padding: 15px; border-radius: 18px; text-align: center; border: 1px solid #e5e5ea; }
    .fund-card { background: white; padding: 18px; border-radius: 22px; margin-bottom: 12px; border: 1px solid #e5e5ea; }
    .status-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: #f2f2f7; color: #8e8e93; margin-right: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# ================= 🔧 数据验证与抓取引擎 =================
def init_db():
    conn = sqlite3.connect('zzl_ultimate_v11.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    conn.commit()
    return conn

db_conn = init_db()

@st.cache_data(ttl=60)
def validate_and_get_fund(code):
    """拦截错误代码：如果找不到基金名称，判定为无效代码"""
    try:
        # 尝试从天天基金接口获取名称
        r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        if "jsonpgz" not in r.text: return None # 代码不存在
        
        name = re.search(r'nameFormat":"(.*?)"', r.text).group(1)
        r_r = float(re.search(r'gszzl":"(.*?)"', r.text).group(1)) # 实时估值
        
        # 获取昨日结算数据
        r_hist = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        tds = BeautifulSoup(r_hist.text, 'html.parser').find_all("td")
        l_r = float(tds[3].text.strip().replace("%",""))
        l_d = tds[0].text.strip()
        
        return {"name": name, "last_r": l_r, "last_d": l_d, "real_r": r_r}
    except:
        return None

@st.cache_data(ttl=60)
def get_market_indices():
    indices = {"sh000001": "上证指数", "sz399006": "创业板指", "gb_ixic": "纳斯达克"}
    data = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join(indices.keys())}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1.5)
        lines = res.text.strip().split('\n')
        for i, (code, name) in enumerate(indices.items()):
            v = lines[i].split('="')[1].split(',')
            curr, last = float(v[3]), float(v[2])
            data.append({"name": name, "price": curr, "chg": (curr - last) / last * 100})
    except:
        return []
    return data

# ================= 🚪 登录拦截 (杜绝 AttributeError) =================
if 'user_token' not in st.session_state: st.session_state.user_token = None
if 'portfolio' not in st.session_state: st.session_state.portfolio = []

if not st.session_state.user_token:
    st.markdown('<h1 style="text-align:center; padding-top:50px;">📈 ZZL Pro</h1>', unsafe_allow_html=True)
    _, col_m, _ = st.columns([0.2, 0.6, 0.2])
    with col_m:
        tk = st.text_input("识别码登录", placeholder="输入 6 位识别码")
        if st.button("进入系统", use_container_width=True, type="primary"):
            if tk:
                cur = db_conn.cursor()
                cur.execute('SELECT portfolio FROM users WHERE token=?', (tk,))
                res = cur.fetchone()
                st.session_state.user_token = tk
                st.session_state.portfolio = json.loads(res[0]) if res else []
                st.rerun()
        if st.button("生成新码", use_container_width=True):
            new_tk = str(random.randint(100000, 999999))
            st.session_state.user_token = new_tk
            st.session_state.portfolio = []
            st.rerun()
    st.stop()

# ================= 📊 主界面逻辑 =================

# 1. 顶部晴雨表
indices = get_market_indices()
if indices:
    st.markdown("### 🌍 全球市场晴雨表")
    cols = st.columns(3)
    for idx, item in enumerate(indices):
        color = "#ff3b30" if item['chg'] > 0 else "#34c759"
        cols[idx].markdown(f"""
            <div class="index-card">
                <div style="font-size:12px; color:#8e8e93;">{item['name']}</div>
                <div style="font-size:20px; font-weight:800; color:{color};">{item['price']:.2f}</div>
                <div style="font-size:12px; color:{color};">{item['chg']:+.2f}%</div>
            </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# 2. 持仓计算
is_weekend = datetime.now().weekday() >= 5
total_m = sum(float(i['m']) for i in st.session_state.portfolio)
total_p = 0.0

hero_placeholder = st.empty()

if not st.session_state.portfolio:
    st.info("💡 您的资产库为空，请在侧边栏添加。")
else:
    st.markdown("### 📑 持仓明细")
    for idx, i in enumerate(st.session_state.portfolio):
        data = validate_and_get_fund(i['c'])
        if not data: continue # 跳过无效数据
        
        # 周末显示周五总结，交易日显示实时
        display_r = 0.0 if is_weekend else data['real_r']
        display_p = i['m'] * (data['last_r'] / 100) if is_weekend else i['m'] * (data['real_r'] / 100)
        total_p += display_p
        
        status_tag = "休市(周五结)" if is_weekend else "实时估值"
        color = "#ff3b30" if (data['last_r'] if is_weekend else display_r) >= 0 else "#34c759"

        with st.container():
            c1, c2 = st.columns([0.9, 0.1])
            c1.markdown(f"💠 **{data['name']}** ({i['c']})")
            if c2.button("✕", key=f"del_{idx}"):
                st.session_state.portfolio.pop(idx)
                db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
                db_conn.commit()
                st.rerun()
            
            # 显示涨跌幅和涨跌金额
            st.markdown(f"""
                <div class="fund-card" style="margin-top:-10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span class="status-tag">{status_tag}</span>
                            <div style="font-size:24px; font-weight:800; color:{color};">{display_r:+.2f}%</div>
                            <div style="font-size:14px; font-weight:bold; color:{color};">涨跌: ¥ {display_p:+.2f}</div>
                        </div>
                        <div style="text-align:right; border-left:1px solid #eee; padding-left:20px;">
                            <div style="font-size:10px; color:#8e8e93;">昨日结算 [{data['last_d']}]</div>
                            <div style="font-size:18px; font-weight:700; color:{'#ff3b30' if data['last_r']>=0 else '#34c759'};">
                                {data['last_r']:+.2f}%
                            </div>
                            <div style="font-size:12px; color:#8e8e93;">市值: ¥ {float(i['m']):,.2f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

# 3. 渲染 Hero Card
hero_placeholder.markdown(f"""
    <div class="hero-card">
        <div style="font-size: 13px; opacity: 0.8;">今日{'预估' if not is_weekend else '累计'}损益 (CNY)</div>
        <div style="font-size: 52px; font-weight: 900;">¥ {total_p:+.2f}</div>
        <div style="font-size: 14px; opacity: 0.9;">
            本金: ¥{total_m:,.0f} | 收益率: {(total_p/total_m*100) if total_m>0 else 0:+.2f}%
        </div>
    </div>
""", unsafe_allow_html=True)

# ================= 🛠️ 侧边栏 (带代码拦截提醒) =================
with st.sidebar:
    st.markdown(f"### 🆔 账户: `{st.session_state.user_token}`")
    if st.button("退出登录"):
        st.session_state.user_token = None
        st.rerun()
    
    st.markdown("---")
    st.markdown("➕ **添加新持仓**")
    with st.form("add_fund", clear_on_submit=True):
        f_code = st.text_input("基金代码", placeholder="输入 6 位代码")
        f_money = st.number_input("本金 (元)", value=10000.0, step=1000.0)
        submit = st.form_submit_button("验证并添加", use_container_width=True)
        
        if submit:
            if not f_code:
                st.error("请输入代码！")
            else:
                with st.spinner('正在验证代码...'):
                    check = validate_and_get_fund(f_code)
                    if check:
                        st.session_state.portfolio.append({"c": f_code, "m": f_money})
                        db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
                        db_conn.commit()
                        st.success(f"已添加: {check['name']}")
                        st.rerun()
                    else:
                        st.error("❌ 错误：市面上找不到该基金，请检查代码是否正确。")
