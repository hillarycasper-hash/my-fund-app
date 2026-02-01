import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 硅谷极简 UI 注入 =================
st.set_page_config(page_title="涨涨乐 Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif !important; }
    .main { background-color: #f5f5f7; }
    
    /* 苹果风总览大卡片 */
    .hero-card {
        background: rgba(28, 28, 30, 0.95);
        backdrop-filter: blur(20px);
        color: white;
        padding: 40px 20px;
        border-radius: 32px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        margin-bottom: 30px;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    /* 磁贴卡片设计 */
    .fund-card {
        background: white;
        padding: 24px;
        border-radius: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.02);
        transition: all 0.3s ease;
        border: 1px solid #f2f2f7;
    }
    .fund-card:hover { transform: translateY(-5px); box-shadow: 0 12px 24px rgba(0,0,0,0.05); }
    
    /* 字体大小微调 */
    .val-main { font-size: 32px; font-weight: 800; letter-spacing: -1px; }
    .label-sub { font-size: 13px; color: #8e8e93; font-weight: 600; text-transform: uppercase; }
    
    /* 隐藏 Streamlit 组件痕迹 */
    div[data-testid="stExpander"] { border: none !important; background: transparent !important; }
    .stButton>button { border-radius: 12px; border: none; background: #f2f2f7; color: #1d1d1f; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ================= 🔧 核心逻辑 (逻辑保持，仅修正周末判断) =================

def get_sina_stock_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        vals = res.text.split('="')[1].strip('";').split(',')
        curr, last = (float(vals[6]), float(vals[3])) if "hk" in prefix else (float(vals[3]), float(vals[2]))
        return ((curr - last) / last) * 100 if last > 0 else 0.0
    except: return 0.0

@st.cache_data(ttl=3600)
def get_holdings_data(fund_code):
    holdings = []
    try:
        res = requests.get(f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=10", timeout=2)
        match = re.search(r'content:"(.*?)"', res.text)
        if match:
            soup = BeautifulSoup(match.group(1), 'html.parser')
            for row in soup.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    c, w = cols[1].text.strip(), float(cols[-3].text.strip().replace("%",""))
                    if w > 0: holdings.append((c, w))
    except: pass
    return holdings

def calculate_realtime(fund_code, fund_name):
    factor = 0.99 if any(x in fund_name for x in ["指数", "ETF", "联接", "互联网"]) else 0.92
    holdings = get_holdings_data(fund_code)
    if not holdings: return 0.0
    with ThreadPoolExecutor(max_workers=10) as executor:
        prices = list(executor.map(get_sina_stock_price, [h[0] for h in holdings]))
    total_chg = sum(p * h[1] for p, h in zip(prices, holdings))
    total_w = sum(h[1] for h in holdings)
    return (total_chg / total_w) * factor if total_w > 0 else 0.0

@st.cache_data(ttl=3600)
def get_base_info(code):
    name, date, nav = f"基金-{code}", "", 0.0
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        m1 = re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)
        if m1: name = m1.group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("tr")[1].find_all("td")
        date, nav = tds[0].text.strip(), float(tds[3].text.strip().replace("%", ""))
    except: pass
    return name, nav, date

# ================= 💾 处理显示逻辑 =================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

with st.sidebar:
    st.markdown("### 📥 持仓管理")
    with st.form("add_fund", clear_on_submit=True):
        f_code = st.text_input("基金代码", placeholder="代码")
        f_money = st.number_input("持有本金", value=10000.0)
        if st.form_submit_button("添加持仓", use_container_width=True):
            if f_code: st.session_state.portfolio.append({"code": f_code, "money": f_money}); st.rerun()
    if st.button("🗑️ 清空所有"): st.session_state.portfolio = []; st.rerun()

# ================= 📊 主显示区 =================
if st.session_state.portfolio:
    with st.spinner('Synchronizing Portfolio...'):
        total_m = sum(i['money'] for i in st.session_state.portfolio)
        mixed_total_profit = 0.0
        details = []
        
        # 判断今天是否为周末 (5=Saturday, 6=Sunday)
        is_weekend = datetime.now().weekday() >= 5
        
        for i in st.session_state.portfolio:
            name, last_r, last_d = get_base_info(i['code'])
            real_r = calculate_realtime(i['code'], name)
            
            # 【周末结算逻辑】：如果是周末，收益率强制锁定为官方最终值
            effective_rate = last_r if is_weekend else (real_r if last_d != datetime.now().strftime('%Y-%m-%d') else last_r)
            current_profit = i['money'] * (effective_rate / 100)
            mixed_total_profit += current_profit
            
            details.append({"name": name, "money": i['money'], "real": real_r, "last": last_r, "date": last_d, "locked": is_weekend})

    # 1. 顶部 Hero Card
    status_text = "休市结算已锁定" if is_weekend else "实时估值运行中"
    st.markdown(f"""
        <div class="hero-card">
            <p style="font-size: 14px; opacity: 0.6; letter-spacing: 2px;">{status_text}</p>
            <div style="font-size: 64px; font-weight: 800; margin: 10px 0;">¥ {mixed_total_profit:+.2f}</div>
            <p style="font-size: 18px; opacity: 0.8;">Total Principle: ¥ {total_m:,.0f} &nbsp; • &nbsp; Yield: {(mixed_total_profit/total_m*100):+.2f}%</p>
        </div>
    """, unsafe_allow_html=True)

    # 2. 持仓列表设计
    st.markdown("### 💠 Portfolio Details")
    for idx, d in enumerate(details):
        st.markdown(f"""
            <div class="fund-card">
                <div style="font-size: 18px; font-weight: 700; color: #1d1d1f; margin-bottom: 15px;">{d['name']}</div>
                <div style="display: flex; justify-content: space-between;">
                    <div style="flex: 1;">
                        <div class="label-sub">Real-time Est.</div>
                        <div class="val-main" style="color: {'#ff3b30' if d['real']>0 else '#34c759'}; opacity: {0.3 if d['locked'] else 1};">
                            {d['real']:+.2f}%
                        </div>
                    </div>
                    <div style="flex: 1; border-left: 1px solid #f2f2f7; padding-left: 20px;">
                        <div class="label-sub">Official Final ({d['date']})</div>
                        <div class="val-main" style="color: {'#ff3b30' if d['last']>0 else '#34c759'};">
                            {d['last']:+.2f}%
                        </div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        if st.button(f"Remove {d['name'][:4]}...", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx); st.rerun()

else:
    st.markdown('<div class="hero-card" style="background:#fff; color:#1d1d1f;"><h1>Hello.</h1><p>Add your first fund to start.</p></div>', unsafe_allow_html=True)
