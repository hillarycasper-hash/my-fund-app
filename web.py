import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 极速 UI 设定 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: -apple-system, sans-serif !important; }
    .stApp { background: #f2f2f7; }
    .hero-card { background: #1c1c1e; color: white; padding: 25px 20px; border-radius: 24px; text-align: center; margin-bottom: 20px; }
    .fund-card { background: white; padding: 16px; border-radius: 20px; margin-bottom: 12px; border: 1px solid #e5e5ea; }
    .num-main { font-size: 24px; font-weight: 800; line-height: 1.2; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="global_refresh")

# ================= 🗄️ 核心：数据库持久化逻辑 (彻底解决丢失) =================

def init_db():
    conn = sqlite3.connect('funds_user.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS portfolio (code TEXT, money REAL)''')
    conn.commit()
    conn.close()

def save_fund(code, money):
    conn = sqlite3.connect('funds_user.db')
    c = conn.cursor()
    c.execute("INSERT INTO portfolio VALUES (?, ?)", (code, money))
    conn.commit()
    conn.close()

def delete_fund(code):
    conn = sqlite3.connect('funds_user.db')
    c = conn.cursor()
    c.execute("DELETE FROM portfolio WHERE code=?", (code,))
    conn.commit()
    conn.close()

def clear_all():
    conn = sqlite3.connect('funds_user.db')
    c = conn.cursor()
    c.execute("DELETE FROM portfolio")
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect('funds_user.db')
    df = pd.read_sql_query("SELECT * FROM portfolio", conn)
    conn.close()
    return df.to_dict('records')

init_db()

# ================= 🔧 爬虫逻辑 (保持高可靠性) =================

@st.cache_data(ttl=600)
def get_sina_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0, ""
    try:
        res = requests.get(f"http://hq.sinajs.cn/list={prefix}{code}", headers={'Referer': 'https://finance.sina.com.cn'}, timeout=0.8)
        v = res.text.split('="')[1].strip('";').split(',')
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
            return (sum(p[0]*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data)) * f, prices[0][1]
    except: pass
    return 0.0, ""

@st.cache_data(ttl=3600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = re.search(r'nameFormat":"(.*?)"', r1.text).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金{code}", 0.0, ""

# ================= 📊 界面 =================

with st.sidebar:
    st.markdown("### 📥 持仓管理")
    with st.form("add_fund_form", clear_on_submit=True):
        c = st.text_input("基金代码", placeholder="013279")
        m = st.number_input("持有本金", value=1000.0)
        if st.form_submit_button("确认添加", use_container_width=True):
            if c:
                save_fund(c, m) # 写入物理数据库
                st.rerun()

    if st.button("🗑️ 清空所有本地记录", use_container_width=True):
        clear_all()
        st.rerun()

# 核心：从物理数据库读取
current_data = load_data()

if current_data:
    is_weekend = datetime.now().weekday() >= 5
    total_m = sum(i['money'] for i in current_data)
    mixed_p = 0.0
    hero_placeholder = st.empty()
    
    for idx, i in enumerate(current_data):
        name, l_r, l_d = get_info(i['code'])
        r_r, s_d = calc_realtime(i['code'], name)
        eff_r = l_r if is_weekend else (l_r if l_d == datetime.now().strftime('%Y-%m-%d') else r_r)
        mixed_p += i['money'] * (eff_r / 100)
        
        with st.container():
            c1, c2 = st.columns([0.88, 0.12])
            c1.markdown(f'<div style="font-size:15px; font-weight:700;">💠 {name}</div>', unsafe_allow_html=True)
            if c2.button("✕", key=f"del_{i['code']}"):
                delete_fund(i['code']) # 从数据库删除
                st.rerun()
            
            st.markdown(f"""
                <div class="fund-card" style="margin-top:-10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div style="flex:1;">
                            <div style="font-size:10px; color:#8e8e93;">实时估值 [{s_d or '获取中'}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if r_r>0 else '#34c759'};">{r_r:+.2f}%</div>
                            <div style="font-size:12px; font-weight:700; color:{'#ff3b30' if r_r>0 else '#34c759'};">¥ {i['money']*r_r/100:+.2f}</div>
                        </div>
                        <div style="flex:1; border-left:1px solid #f2f2f7; padding-left:12px;">
                            <div style="font-size:10px; color:#8e8e93;">官方昨结 [{l_d}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if l_r>0 else '#34c759'};">{l_r:+.2f}%</div>
                            <div style="font-size:12px; font-weight:700; color:{'#ff3b30' if l_r>0 else '#34c759'};">¥ {i['money']*l_r/100:+.2f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    hero_placeholder.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 52px; font-weight: 900; line-height:1;">¥ {mixed_p:+.2f}</div>
            <div style="font-size: 14px; opacity: 0.8; margin-top:10px;">本金合计 ¥{total_m:,.0f} | 预估收益率 {(mixed_p/total_m*100):+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<div class="hero-card" style="background:white; color:#1c1c1e; border:1px solid #e5e5ea;"><h2>数据已就绪</h2><p>请点击左侧侧边栏添加基金</p></div>', unsafe_allow_html=True)
