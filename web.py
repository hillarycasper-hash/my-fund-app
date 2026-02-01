import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 顶层 UI 定制 =================
st.set_page_config(page_title="涨涨乐 Pro", page_icon="🚀", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #fcfcfc; }
    .total-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 24px;
        box-shadow: 0 12px 24px rgba(0,0,0,0.15);
        margin-bottom: 2rem;
        text-align: center;
    }
    .data-row { background: #ffffff; padding: 1.2rem; border-radius: 16px; border: 1px solid #f1f5f9; margin-bottom: 1rem; }
    .metric-block { flex: 1; text-align: center; }
    .metric-label { font-size: 0.85rem; color: #64748b; margin-bottom: 0.3rem; font-weight: 500; }
    .metric-value { font-size: 1.6rem; font-weight: 800; }
    .fund-title { font-size: 1.1rem; font-weight: 700; color: #1e293b; margin-bottom: 1rem; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ================= 🔧 核心逻辑 (算法与系数 100% 保留) =================

def get_sina_stock_price(code):
    prefix = ""
    if code.startswith('6') or code.startswith('5') or code.startswith('11'): prefix = "sh"
    elif code.startswith('0') or code.startswith('3') or code.startswith('1') or code.startswith('15'): prefix = "sz"
    elif len(code) == 5: prefix = "rt_hk"
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
        url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=10"
        res = requests.get(url, timeout=2)
        match = re.search(r'content:"(.*?)"', res.text)
        if match:
            soup = BeautifulSoup(match.group(1), 'html.parser')
            for row in soup.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    c = cols[1].text.strip(), float(cols[-3].text.strip().replace("%",""))
                    if c[1] > 0: holdings.append(c)
    except: pass
    return holdings

def calculate_realtime(fund_code, fund_name):
    factor = 0.99 if any(x in fund_name for x in ["指数", "ETF", "联接", "互联网"]) else 0.92
    holdings = get_holdings_data(fund_code)
    if holdings:
        with ThreadPoolExecutor(max_workers=10) as executor:
            prices = list(executor.map(get_sina_stock_price, [h[0] for h in holdings]))
        total_chg = sum(p * h[1] for p, h in zip(prices, holdings))
        total_w = sum(h[1] for h in holdings)
        return (total_chg / total_w) * factor if total_w > 0 else 0.0
    return 0.0

@st.cache_data(ttl=3600)
def get_base_info(code):
    name, nav, date = f"基金-{code}", 0.0, ""
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        m1 = re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)
        if m1: name = m1.group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("tr")[1].find_all("td")
        date, nav = tds[0].text.strip(), float(tds[3].text.strip().replace("%", ""))
    except: pass
    return name, nav, date

# ================= 💾 数据处理 =================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

with st.sidebar:
    st.markdown("### 📥 持仓录入")
    with st.form("add_fund", clear_on_submit=True):
        f_code = st.text_input("基金代码")
        f_money = st.number_input("持有本金", value=100.0, step=100.0)
        if st.form_submit_button("确认添加", use_container_width=True):
            if f_code:
                st.session_state.portfolio.append({"code": f_code, "money": f_money})
                st.rerun()
    st.markdown("---")
    if st.button("🗑️ 清空实盘"):
        st.session_state.portfolio = []
        st.rerun()

# ================= 📊 主面板 =================

if st.session_state.portfolio:
    with st.spinner('📡 正在智能结算资产...'):
        total_m = sum(i['money'] for i in st.session_state.portfolio)
        results = []
        mixed_total_profit = 0.0 # 混合盈亏总计
        
        # 获取今天日期字符串 (用于判断是否更新)
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        for i in st.session_state.portfolio:
            name, last_r, last_d = get_base_info(i['code'])
            real_r = calculate_realtime(i['code'], name)
            
            # 【核心逻辑切换】
            # 如果官方最终值的日期是今天(或最新一期)，则采用最终值盈亏；否则用实时估值
            if last_d == today_str:
                current_profit = i['money'] * (last_r / 100)
                is_settled = True
            else:
                current_profit = i['money'] * (real_r / 100)
                is_settled = False
            
            mixed_total_profit += current_profit
            results.append({
                "name": name, "money": i['money'], 
                "real_r": real_r, "last_r": last_r, 
                "date": last_d, "settled": is_settled
            })
        
    # 顶部资产条 (显示混合结算后的总收益)
    st.markdown(f"""
        <div class="total-card">
            <p style="opacity: 0.7; margin-bottom: 0.5rem;">当前账户总收益 (已自动切换结算模式)</p>
            <h1 style="color: white; margin: 0; font-size: 3rem;">¥ {mixed_total_profit:+.2f}</h1>
            <p style="margin-top: 0.5rem; opacity: 0.8;">今日总本金: ¥ {total_m:,.0f} &nbsp; | &nbsp; 整体盈亏率: {(mixed_total_profit/total_m*100):+.2f}%</p>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("### 💠 资产详情对比")
    for idx, res in enumerate(results):
        with st.container():
            # 在标题旁标注是否已按官方结算
            settled_tag = "✅ 已按最终值结算" if res['settled'] else "⏳ 实时估值中"
            st.markdown(f"<div class='fund-title'>📘 {res['name']} <span style='font-size:0.8rem; font-weight:normal; color:#64748b;'>[{settled_tag}]</span></div>", unsafe_allow_html=True)
            
            c1, c2, c3 = st.columns([10, 10, 3])
            
            # 实时列
            real_color = "#ef4444" if res['real_r'] > 0 else "#22c55e"
            c1.markdown(f"""
                <div class="metric-block" style="border-right: 1px solid #f1f5f9; {'opacity:0.5' if res['settled'] else ''}">
                    <div class="metric-label">🔥 实时估值</div>
                    <div class="metric-value" style="color: {real_color};">{res['real_r']:+.2f}%</div>
                </div>
            """, unsafe_allow_html=True)
            
            # 最终值列
            last_color = "#ef4444" if res['last_r'] > 0 else "#22c55e"
            c2.markdown(f"""
                <div class="metric-block" style="{'background:#f8fafc; border-radius:8px;' if res['settled'] else ''}">
                    <div class="metric-label">📉 官方最终值 ({res['date']})</div>
                    <div class="metric-value" style="color: {last_color};">{res['last_r']:+.2f}%</div>
                </div>
            """, unsafe_allow_html=True)
            
            if c3.button("🗑️", key=f"del_{idx}"):
                st.session_state.portfolio.pop(idx)
                st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)
else:
    st.info("💡 请在左侧侧边栏添加基金开始监控。")
