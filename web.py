import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

# ================= 🎨 界面基础设置 =================
st.set_page_config(page_title="涨涨乐 Pro 🚀", layout="wide")

# ================= 🔧 1. 核心抓取函数 (带缓存提速) =================
@st.cache_data(ttl=3600)
def get_base_info_cached(code):
    """获取基金名称和昨收净值"""
    name, nav, date = f"基金-{code}", 0.0, "---"
    try:
        # 优先获取名称，用于快速展示
        r1 = requests.get(f"https://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        m1 = re.search(r'name":"(.*?)"', r1.text)
        if m1: name = m1.group(1)
        
        # 获取昨收详情
        r2 = requests.get(f"https://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        soup = BeautifulSoup(r2.text, 'html.parser')
        rows = soup.find_all("tr")
        if len(rows) >= 2:
            tds = rows[1].find_all("td")
            date = tds[0].text.strip()
            nav = float(tds[3].text.strip().replace("%", ""))
    except: pass
    return name, nav, date

def get_sina_stock_price(code):
    """获取股票/指数实时涨跌幅"""
    prefix = ""
    if code.startswith('6') or code.startswith('5'): prefix = "sh"
    elif code.startswith('0') or code.startswith('3') or code.startswith('1'): prefix = "sz"
    elif len(code) == 5: prefix = "rt_hk"
    if not prefix: return 0.0
    try:
        res = requests.get(f"https://hq.sinajs.cn/list={prefix}{code}", headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        vals = res.text.split('="')[1].strip('";').split(',')
        curr, last = (float(vals[6]), float(vals[3])) if "hk" in prefix else (float(vals[3]), float(vals[2]))
        return ((curr - last) / last) * 100 if last > 0 else 0.0
    except: return 0.0

@st.cache_data(ttl=3600)
def get_holdings_cached(code):
    """获取前十大持仓"""
    holdings = []
    try:
        url = f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10"
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

# ================= 🖥️ 侧边栏 =================
with st.sidebar:
    st.title("⚙️ 操作台")
    code = st.text_input("🔢 基金代码", value="013279")
    money = st.number_input("💰 持有金额", value=10000.0)
    run_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)
    if st.button("🧹 刷新数据"): st.cache_data.clear()

# ================= 📊 主面板 (布局优化版) =================
st.title("📈 涨涨乐 Pro")
st.divider()

if run_btn:
    # 步骤 A: 快速获取并显示基金名字 (用户体验最快)
    name, last_rate, last_date = get_base_info_cached(code)
    st.subheader(f"📘 {name}")  # <--- 名字现在在最上面
    
    with st.spinner('📡 正在计算实时估值...'):
        # 步骤 B: 计算实时估值
        holdings = get_holdings_cached(code)
        factor = 0.99 if any(x in name for x in ["互联网", "ETF", "联接"]) else 0.92
        
        if holdings:
            real_rate = (sum(get_sina_stock_price(c) * w for c, w in holdings) / sum(w for c, w in holdings)) * factor
        else:
            # 保底对标逻辑
            real_rate = get_sina_stock_price("HSTECH") if "互联网" in name else 0.0

        # 步骤 C: 展示数据卡片
        c1, c2 = st.columns(2)
        c1.metric("🔥 实时估值 (今日)", f"{real_rate:+.2f}%", f"{(money*real_rate/100):+.2f} 元", delta_color="inverse")
        c2.metric(f"📉 官方最终值 ({last_date})", f"{last_rate:+.2f}%", f"{(money*last_rate/100):+.2f} 元", delta_color="inverse")
        
        st.divider()
        if real_rate > 0:
            st.success(f"🎉 建议加鸡腿！今日预估收益：+{(money*real_rate/100):.2f} 元")
        else:
            st.error(f"🍃 莫慌，要做时间的朋友。今日预估波动：{(money*real_rate/100):.2f} 元")
else:
    st.info("👈 在左侧输入代码并点击【开始分析】")
