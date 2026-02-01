import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 UI 深度重构 (CSS 注入) =================
st.set_page_config(page_title="涨涨乐 Pro", page_icon="🚀", layout="wide")

# 注入全新 UI 样式
st.markdown("""
    <style>
    /* 1. 移除默认间距，增加呼吸感 */
    .block-container { padding-top: 1.5rem !important; }
    
    /* 2. 顶部资产条美化 */
    .header-box {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        color: white;
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
        text-align: center;
    }
    
    /* 3. 卡片容器美化 */
    div.stExpander {
        border: 1px solid #e2e8f0 !important;
        border-radius: 16px !important;
        background-color: white !important;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05) !important;
        overflow: hidden;
    }
    
    /* 4. 标题字体美化 */
    h1, h2, h3 { color: #0f172a !important; font-family: 'Inter', sans-serif; }
    
    /* 5. 隐藏 Streamlit 默认页脚 */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    
    /* 6. 特殊 Metric 样式 */
    [data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

# 自动刷新 (60秒)
st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ================= 🔧 核心逻辑 (100% 保留你的原始算法) =================

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

# ================= 🖥️ 侧边栏 (轻量化) =================
with st.sidebar:
    st.markdown("### 📥 快速录入")
    with st.form("add_form", clear_on_submit=True):
        f_code = st.text_input("代码", placeholder="如 013279")
        f_money = st.number_input("金额", value=100.0, step=100.0)
        submitted = st.form_submit_button("添加至实盘", use_container_width=True)
        if submitted and f_code:
            st.session_state.portfolio.append({"code": f_code, "money": f_money})
            st.rerun()
    
    st.markdown("---")
    if st.button("🧹 一键清空所有持仓", use_container_width=True):
        st.session_state.portfolio = []
        st.rerun()

# ================= 📊 主显示区 =================

# 1. 顶部全屏资产条
if st.session_state.portfolio:
    with st.spinner('同步实时行情...'):
        total_m = sum(i['money'] for i in st.session_state.portfolio)
        results = []
        for i in st.session_state.portfolio:
            name, last_r, last_d = get_base_info(i['code'])
            real_r = calculate_realtime(i['code'], name)
            results.append({"name": name, "money": i['money'], "real_r": real_r, "last_r": last_r, "date": last_d, "code": i['code']})
        
        total_real_p = sum(r['money'] * r['real_r'] / 100 for r in results)
        total_last_p = sum(r['money'] * r['last_r'] / 100 for r in results)
        total_real_rate = (total_real_p / total_m * 100) if total_m > 0 else 0

    st.markdown(f"""
        <div class="header-box">
            <p style="font-size: 1rem; opacity: 0.8; margin-bottom: 0;">实时估值总盈亏 (今日)</p>
            <h1 style="color: white; font-size: 3.5rem; margin-top: 0;">¥ {total_real_p:+.2f}</h1>
            <p style="font-size: 1.2rem;">总持有: ¥ {total_m:,.0f} &nbsp; | &nbsp; 今日总收益率: {total_real_rate:+.2f}%</p>
        </div>
    """, unsafe_allow_html=True)

    # 2. 网格化卡片 (每行 3 个)
    st.markdown("### 💠 持仓实时详情")
    cols = st.columns(3)
    for index, res in enumerate(results):
        with cols[index % 3]:
            # 使用简单的卡片包装
            with st.expander(f"**{res['name']}**", expanded=True):
                st.metric("今日估值", f"{res['real_r']:+.2f}%", f"¥ {res['money']*res['real_r']/100:+.2f}", delta_color="inverse")
                st.markdown(f"<p style='font-size:0.8rem; color:gray'>昨结: {res['last_r']:+.2f}% ({res['date']})</p>", unsafe_allow_html=True)
                if st.button(f"删除", key=f"del_{index}", use_container_width=True):
                    st.session_state.portfolio.pop(index)
                    st.rerun()
else:
    st.markdown("""
        <div class="header-box" style="background: #f1f5f9; color: #64748b;">
            <h1 style="color: #64748b;">🚀 涨涨乐·实盘管家</h1>
            <p>请在左侧输入基金代码，开启实时资产追踪</p>
        </div>
    """, unsafe_allow_html=True)
    st.info("💡 **提示**：你可以一次性添加多只基金，每分钟系统将自动刷新最新估值。")

st.markdown(f"<div style='text-align:center; padding: 2rem; color: #94a3b8;'>行情每 60 秒自动更新一次</div>", unsafe_allow_html=True)
