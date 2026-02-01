import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh # 引入自动刷新插件

# ================= 🎨 页面基础设置 =================
st.set_page_config(page_title="涨涨乐管家 Pro 🚀", page_icon="🚀", layout="wide")

# 每 60,000 毫秒（1分钟）自动刷新一次页面
st_autorefresh(interval=60 * 1000, key="data_refresh")

# ================= 🔧 核心逻辑 (保留你的算法) =================

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
                    c = cols[1].text.strip()
                    try: w = float(cols[-3].text.strip().replace("%",""))
                    except: w = 0
                    if w > 0: holdings.append((c, w))
    except: pass
    return holdings

def calculate_realtime(fund_code, fund_name):
    factor = 0.99 if ("互联网" in fund_name or "ETF" in fund_name or "联接" in fund_name) else 0.92
    holdings = get_holdings_data(fund_code)
    if holdings:
        with ThreadPoolExecutor(max_workers=10) as executor:
            prices = list(executor.map(get_sina_stock_price, [h[0] for h in holdings]))
        total_chg = sum(p * h[1] for p, h in zip(prices, holdings))
        total_w = sum(h[1] for h in holdings)
        if total_w > 0: return (total_chg / total_w) * factor
    return 0.0

@st.cache_data(ttl=3600)
def get_base_info(code):
    name, nav, date = f"基金-{code}", 0.0, ""
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        m1 = re.search(r'name":"(.*?)"', r1.text)
        if m1: name = m1.group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("tr")[1].find_all("td")
        date, nav = tds[0].text.strip(), float(tds[3].text.strip().replace("%", ""))
    except: pass
    return name, nav, date

# ================= 💾 Session State 持仓管理 =================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

# ================= 🖥️ 侧边栏 =================
with st.sidebar:
    st.title("💼 实盘配置")
    new_code = st.text_input("🔢 基金代码", placeholder="如 013279")
    new_money = st.number_input("💰 持有金额", min_value=0.0, step=1000.0)
    
    if st.button("➕ 确认添加", use_container_width=True, type="primary"):
        if new_code:
            st.session_state.portfolio.append({"code": new_code, "money": new_money})
            st.rerun()
    
    st.divider()
    st.write("⏱️ 每 60 秒自动更新行情")
    if st.button("🗑️ 清空实盘记录"):
        st.session_state.portfolio = []
        st.rerun()

# ================= 📊 主面板 =================
st.title("🚀 涨涨乐·实盘管家")

if not st.session_state.portfolio:
    st.info("💡 您的实盘列表为空，请在左侧添加持仓。")
else:
    total_money = sum(item['money'] for item in st.session_state.portfolio)
    total_real_profit = 0.0
    total_last_profit = 0.0
    
    # 🏎️ 提速核心：并发计算
    with st.spinner('📡 正在同步一分钟前行情...'):
        display_list = []
        for item in st.session_state.portfolio:
            name, last_rate, last_date = get_base_info(item['code'])
            real_rate = calculate_realtime(item['code'], name)
            
            real_p = item['money'] * (real_rate / 100)
            last_p = item['money'] * (last_rate / 100)
            
            total_real_profit += real_p
            total_last_profit += last_p
            
            display_list.append({
                "name": name, "money": item['money'], 
                "real_r": real_rate, "real_p": real_p,
                "last_r": last_rate, "last_p": last_p, "date": last_date
            })

    # 1. 总览卡片（新增总收益率展示）
    total_real_rate = (total_real_profit / total_money * 100) if total_money > 0 else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("🔥 实时总盈亏", f"{total_real_profit:+.2f} 元", f"{total_real_rate:+.2f}%")
    c2.metric("📉 昨结总盈亏", f"{total_last_profit:+.2f} 元", f"{(total_last_profit/total_money*100):+.2f}%" if total_money > 0 else "0%")
    c3.metric("💰 持有总本金", f"{total_money:,.0f} 元")

    # 2. 明细看板
    st.divider()
    for i, data in enumerate(display_list):
        with st.expander(f"📘 {data['name']} (￥{data['money']:,})", expanded=True):
            col1, col2, col3 = st.columns([2, 2, 1])
            col1.metric("今日实时", f"{data['real_r']:+.2f}%", f"{data['real_p']:+.2f} 元", delta_color="inverse")
            col2.metric(f"昨结 ({data['date']})", f"{data['last_r']:+.2f}%", f"{data['last_p']:+.2f} 元", delta_color="inverse")
            if col3.button("移除", key=f"del_{i}"):
                st.session_state.portfolio.pop(i)
                st.rerun()

    # 3. 动态状态
    st.caption("✅ 数据已自动同步 | 实时收益按前十大持仓及相关指数动态计算")
