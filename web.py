import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

# ================= 🎨 界面基础设置 =================
st.set_page_config(
    page_title="涨涨乐 Pro 🚀",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 🔧 1. 行情获取 (实时抓取，不缓存) =================
def get_sina_stock_price(code):
    prefix = ""
    if code.startswith('6') or code.startswith('5') or code.startswith('11'): prefix = "sh"
    elif code.startswith('0') or code.startswith('3') or code.startswith('1') or code.startswith('15'): prefix = "sz"
    elif len(code) == 5: prefix = "rt_hk"
    
    if not prefix: return 0.0
    try:
        url = f"https://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        if len(res.text) < 20: return 0.0
        parts = res.text.split('="')
        vals = parts[1].strip('";').split(',')
        if "hk" in prefix:
            curr, last = float(vals[6]), float(vals[3])
        else:
            curr, last = float(vals[3]), float(vals[2])
        if curr == 0: curr = last
        if last > 0: return ((curr - last) / last) * 100
    except: pass
    return 0.0

# ================= 🔧 2. 基础信息获取 (加缓存，提速核心) =================
@st.cache_data(ttl=3600) # 缓存1小时，避免重复抓取网页
def get_base_info_cached(code):
    name = f"基金-{code}"
    nav, date = 0.0, "---"
    try:
        r1 = requests.get(f"https://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        m1 = re.search(r'name":"(.*?)"', r1.text)
        if m1: name = m1.group(1)
        
        r2 = requests.get(f"https://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        soup = BeautifulSoup(r2.text, 'html.parser')
        rows = soup.find_all("tr")
        if len(rows) >= 2:
            tds = rows[1].find_all("td")
            date = tds[0].text.strip()
            nav = float(tds[3].text.strip().replace("%", ""))
    except: pass
    return name, nav, date

# ================= 🔧 3. 持仓获取 (加缓存，提速核心) =================
@st.cache_data(ttl=3600)
def get_fund_holdings_cached(fund_code):
    holdings = []
    try:
        url = f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=10"
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

# ================= 🔧 4. 实时计算逻辑 =================
def calculate_realtime(fund_code, fund_name):
    holdings = get_fund_holdings_cached(fund_code) # 使用带缓存的持仓抓取
    factor = 0.99 if any(x in fund_name for x in ["互联网", "ETF", "联接"]) else 0.92
    
    if holdings:
        total_chg = sum(get_sina_stock_price(c) * w for c, w in holdings)
        total_w = sum(w for c, w in holdings)
        if total_w > 0: return (total_chg / total_w) * factor
    
    # 保底对标逻辑
    map_dict = {"纳指": "513100", "300": "510300", "恒生科技": "HSTECH"}
    for k, v in map_dict.items():
        if k in fund_name: return get_sina_stock_price(v)
    return 0.0

# ================= 🖥️ 侧边栏 =================
with st.sidebar:
    st.title("⚙️ 操作台")
    code = st.text_input("🔢 基金代码", value="013279")
    money = st.number_input("💰 持有金额", value=10000.0, step=1000.0)
    run_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)
    st.divider()
    if st.button("🧹 清除缓存"): # 专门准备个按钮，万一数据卡了可以点一下
        st.cache_data.clear()

# ================= 📊 主面板 =================
st.title("🚀 涨涨乐 Pro")
st.divider()

if run_btn:
    with st.spinner('📡 正在秒速调取数据...'):
        # 使用缓存版本的信息获取
        name, last_rate, last_date = get_base_info_cached(code)
        real_rate = calculate_realtime(code, name)
        
        c1, c2 = st.columns(2)
        c1.metric("🔥 实时估值 (今日)", f"{real_rate:+.2f}%", f"{(money*real_rate/100):+.2f} 元", delta_color="inverse")
        c2.metric(f"📉 官方最终值 ({last_date})", f"{last_rate:+.2f}%", f"{(money*last_rate/100):+.2f} 元", delta_color="inverse")
        
        st.markdown(f"### 📘 {name}")
        st.divider()
        if real_rate > 0: st.success(f"🎉 建议加鸡腿！预计收益：+{(money*real_rate/100):.2f} 元")
        else: st.error(f"🍃 莫慌，要做时间的朋友。")
else:
    st.info("👈 输入代码后点击【开始分析】")
