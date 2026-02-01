import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh
from streamlit_js_eval import streamlit_js_eval

# ================= 🎨 极速 UI & 适配 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }
    .stApp { background: #f2f2f7; }
    .hero-card { background: #1c1c1e; color: white; padding: 25px 20px; border-radius: 24px; text-align: center; margin-bottom: 20px; }
    .fund-card { background: white; padding: 15px; border-radius: 20px; margin-bottom: 12px; border: 1px solid #e5e5ea; }
    .stButton > button { border: none !important; background: #f2f2f7 !important; color: #8e8e93 !important; border-radius: 50% !important; width: 26px !important; height: 26px !important; padding: 0 !important; font-size: 14px !important; }
    .data-grid { display: flex; justify-content: space-between; gap: 10px; }
    .data-slot { flex: 1; }
    .label-tag { font-size: 10px; color: #8e8e93; font-weight: 700; margin-bottom: 2px; }
    .num-main { font-size: 22px; font-weight: 800; line-height: 1.2; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=90 * 1000, key="global_refresh")

# ================= 💾 核心：数据持久化逻辑 =================

# 1. 从浏览器读取数据
if 'portfolio' not in st.session_state:
    saved_data = streamlit_js_eval(js_expressions="localStorage.getItem('my_portfolio')", key="load_lp")
    if saved_data:
        st.session_state.portfolio = json.loads(saved_data)
    else:
        st.session_state.portfolio = []

# 2. 保存数据到浏览器的函数
def save_to_local():
    data_str = json.dumps(st.session_state.portfolio)
    streamlit_js_eval(js_expressions=f"localStorage.setItem('my_portfolio', '{data_str}')", key="save_lp")

# ================= 🔧 爬虫逻辑 =================

@st.cache_data(ttl=3600)
def get_sina_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0, ""
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=0.8)
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
            chg = sum(p[0]*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data)
            return chg * f, prices[0][1]
    except: pass
    return 0.0, ""

@st.cache_data(ttl=3600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = (re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金-{code}", 0.0, ""

# ================= 📊 主流程 =================

with st.sidebar:
    st.markdown("### 📥 快捷录入")
    with st.form("add", clear_on_submit=True):
        c = st.text_input("代码", placeholder="013279")
        m = st.number_input("本金", value=10000.0)
        if st.form_submit_button("添加", use_container_width=True):
            if c: 
                st.session_state.portfolio.append({"c": c, "m": m})
                save_to_local() # 添加后立即保存
                st.rerun()
    if st.button("🗑️ 清空所有数据"):
        st.session_state.portfolio = []
        save_to_local() # 清空后同步保存
        st.rerun()

if st.session_state.portfolio:
    is_weekend = datetime.now().weekday() >= 5
    total_m = sum(i['m'] for i in st.session_state.portfolio)
    mixed_p = 0.0
    hero_placeholder = st.empty()
    
    for idx, i in enumerate(st.session_state.portfolio):
        name, l_r, l_d = get_info(i['c'])
        r_r, s_d = calc_realtime(i['c'], name)
        eff_r = l_r if is_weekend else (l_r if l_d == datetime.now().strftime('%Y-%m-%d') else r_r)
        mixed_p += i['m'] * (eff_r / 100)
        
        with st.container():
            c1, c2 = st.columns([0.9, 0.1])
            c1.markdown(f'<div style="font-size:14px; font-weight:700;">💠 {name}</div>', unsafe_allow_html=True)
            if c2.button("✕", key=f"d_{idx}"):
                st.session_state.portfolio.pop(idx)
                save_to_local() # 删除后同步保存
                st.rerun()
            
            st.markdown(f"""
                <div class="fund-card" style="margin-top:-10px;">
                    <div class="data-grid">
                        <div class="data-slot">
                            <div class="label-tag">估值 [{s_d or '休市'}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if r_r>0 else '#34c759'};">{r_r:+.2f}%</div>
                            <div style="font-size:11px; color:{'#ff3b30' if r_r>0 else '#34c759'};">¥ {i['m']*r_r/100:+.2f}</div>
                        </div>
                        <div class="data-slot" style="border-left:1px solid #f2f2f7; padding-left:10px;">
                            <div class="label-tag">昨结 [{l_d}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if l_r>0 else '#34c759'};">{l_r:+.2f}%</div>
                            <div style="font-size:11px; color:{'#ff3b30' if l_r>0 else '#34c759'};">¥ {i['m']*l_r/100:+.2f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    hero_placeholder.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 48px; font-weight: 900;">¥ {mixed_p:+.2f}</div>
            <div style="font-size: 13px; opacity: 0.7;">本金 ¥{total_m:,.0f} | 收益率 {(mixed_p/total_m*100):+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<div class="hero-card" style="background:white; color:#1c1c1e; border:1px solid #e5e5ea;"><h3>无持仓数据</h3><p>请点击左上角侧边栏添加</p></div>', unsafe_allow_html=True)
