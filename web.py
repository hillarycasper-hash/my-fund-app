import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 UI 注入与美化 =================
st.set_page_config(page_title="涨涨乐管家 Pro", page_icon="📈", layout="wide")

# 注入自定义 CSS
st.markdown("""
    <style>
    /* 全局背景与字体 */
    .main { background-color: #f8f9fa; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700 !important; }
    
    /* 卡片美化 */
    div[data-testid="stExpander"] {
        border: none !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
        background-color: white !important;
        border-radius: 12px !important;
        margin-bottom: 1rem !important;
    }
    
    /* 侧边栏美化 */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #eee;
    }
    
    /* 标题样式 */
    .total-header {
        font-family: "Microsoft YaHei", sans-serif;
        color: #1e293b;
        font-weight: 800;
        padding-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# 自动刷新 (60秒)
st_autorefresh(interval=60 * 1000, key="data_refresh")

# ================= 🔧 核心逻辑 (逻辑原封不动) =================

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

# ================= 💾 会话状态 =================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

# ================= 🖥️ 侧边栏 =================
with st.sidebar:
    st.markdown("### 💠 账户配置")
    with st.container():
        new_code = st.text_input("🔢 基金代码", placeholder="输入代码", help="例如 013279")
        new_money = st.number_input("💰 持有本金", min_value=0.0, step=1000.0)
        
        if st.button("✨ 立即加入实盘", use_container_width=True, type="primary"):
            if new_code:
                st.session_state.portfolio.append({"code": new_code, "money": new_money})
                st.rerun()
    
    st.markdown("---")
    st.markdown("#### ⚙️ 辅助操作")
    if st.button("🔄 强制重载数据", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.button("🗑️ 清空所有记录", use_container_width=True):
        st.session_state.portfolio = []
        st.rerun()
    
    st.caption("📈 系统每 60 秒自动对齐行情")

# ================= 📊 主看板 =================
st.markdown("<h1 class='total-header'>🚀 涨涨乐 · 实盘管家 Pro</h1>", unsafe_allow_html=True)

if not st.session_state.portfolio:
    st.info("💡 **欢迎使用！** 请在左侧侧边栏录入您的基金代码和持有本金，开始实时资产监控。")
else:
    total_money = sum(item['money'] for item in st.session_state.portfolio)
    total_real_profit = 0.0
    total_last_profit = 0.0
    
    with st.spinner('📡 极速同步全球行情中...'):
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

    # 💎 核心统计卡片
    total_real_rate = (total_real_profit / total_money * 100) if total_money > 0 else 0
    
    st.markdown("### 📋 实时盈亏概览")
    m1, m2, m3 = st.columns(3)
    
    with st.container():
        m1.metric("🔥 今日实时净值", f"{total_real_profit:+.2f} 元", f"{total_real_rate:+.2f}%", delta_color="inverse")
        m2.metric("📉 昨日结算净值", f"{total_last_profit:+.2f} 元", f"{(total_last_profit/total_money*100):+.2f}%" if total_money > 0 else "0%", delta_color="inverse")
        m3.metric("💰 投资总本金", f"{total_money:,.0f} 元", "资产总额")

    # 📑 持仓详情看板
    st.markdown("---")
    st.markdown("### 📑 持仓明细详情")
    
    for i, data in enumerate(display_list):
        # 使用 Expander 作为卡片，利用 CSS 样式美化
        with st.expander(f"📦 {data['name']} · ￥{data['money']:,}", expanded=True):
            col1, col2, col3 = st.columns([2, 2, 1])
            col1.metric("今日预估", f"{data['real_r']:+.2f}%", f"{data['real_p']:+.2f} 元", delta_color="inverse")
            col2.metric(f"昨结 ({data['date']})", f"{data['last_r']:+.2f}%", f"{data['last_p']:+.2f} 元", delta_color="inverse")
            # 删除按钮美化
            if col3.button("🗑️ 移除", key=f"del_{i}", use_container_width=True):
                st.session_state.portfolio.pop(i)
                st.rerun()

    # 💡 情感化 UI 提醒
    st.markdown("---")
    if total_real_profit > 0:
        st.balloons()
        st.success(f"🎊 **今日大吉！** 您的账户实时增长了 **{total_real_profit:.2f}** 元。行情虽好，也要保持平常心。")
    elif total_real_profit < 0:
        st.warning(f"🍃 **行情波动：** 账户当前回撤 **{abs(total_real_profit):.2f}** 元。坚持长线，等待回升。")
    else:
        st.info("☁️ **震荡调整：** 账户收益持平。市场正在蓄势。")

    st.markdown(f"<div style='text-align: center; color: #94a3b8; font-size: 0.8rem; padding: 2rem;'>数据实时更新于 1 分钟前 | 请以官方收盘净值为准</div>", unsafe_allow_html=True)
