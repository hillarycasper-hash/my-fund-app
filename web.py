import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

# ================= 🎨 页面基础设置 =================
st.set_page_config(
    page_title="涨涨乐 🚀",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 🔧 核心函数 (精准修正系数) =================
def get_sina_stock_price(code):
    prefix = ""
    # 自动识别 A股/港股 前缀
    if code.startswith('6') or code.startswith('5') or code.startswith('11'): prefix = "sh"
    elif code.startswith('0') or code.startswith('3') or code.startswith('1') or code.startswith('15'): prefix = "sz"
    elif len(code) == 5: prefix = "rt_hk" # 修正港股前缀，更准确获取实时值
    
    if not prefix: return 0.0
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        if len(res.text) < 20: return 0.0
        parts = res.text.split('="')
        vals = parts[1].strip('";').split(',')
        
        # 港股与A股解析位置略有不同，做个兼容
        if "hk" in prefix:
            curr, last = float(vals[6]), float(vals[3])
        else:
            curr, last = float(vals[3]), float(vals[2])
            
        if curr == 0: curr = last
        if last > 0: return ((curr - last) / last) * 100
    except: pass
    return 0.0

def smart_fallback_benchmark(fund_code, fund_name):
    map_dict = {
        "白银": ("161226", 1.0), "黄金": ("518800", 1.0), "豆粕": ("159985", 1.0),
        "光伏": ("515790", 0.98), "新能源": ("516160", 0.98), "医疗": ("512170", 0.98),
        "白酒": ("512690", 0.98), "半导体": ("512480", 0.98), "军工": ("512660", 0.98),
        "券商": ("512880", 0.98), "纳指": ("513100", 0.96), "标普": ("513500", 0.96),
        "300": ("510300", 0.99), "创业板": ("159915", 0.99),
        "互联网": ("HSTECH", 1.0) # 新增：针对013279这类互联网基金
    }
    for k, v in map_dict.items():
        if k in fund_name: return v[0], v[1]
    return None, 0.95

def calculate_realtime(fund_code, fund_name):
    # 针对 013279 (中概互联/恒生科技) 这种指数基金，系数必须是 1.0 附近
    factor = 0.99 if ("互联网" in fund_name or "ETF" in fund_name or "联接" in fund_name) else 0.92
    
    holdings = []
    try:
        url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=10"
        res = requests.get(url, timeout=3)
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

    if holdings:
        total_chg = sum(get_sina_stock_price(c) * w for c, w in holdings)
        total_w = sum(w for c, w in holdings)
        if total_w > 0:
            return (total_chg / total_w) * factor
    
    # 如果没抓到持仓，用 Benchmark，并给 013279 加上特殊识别
    bench_code, bench_factor = smart_fallback_benchmark(fund_code, fund_name)
    if bench_code:
        # 针对 013279 特殊逻辑：恒生科技
        if bench_code == "HSTECH":
            return get_sina_stock_price("HSTECH") * 1.0
        return get_sina_stock_price(bench_code) * bench_factor
    return 0.0

def get_base_info(code):
    name = f"基金-{code}"
    nav, date = 0.0, ""
    try:
        # 1. 抓取名称
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1)
        m1 = re.search(r'name":"(.*?)"', r1.text)
        if m1: name = m1.group(1)
        
        # 2. 抓取历史净值 (100% 还原你之前的逻辑)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1)
        soup = BeautifulSoup(r2.text, 'html.parser')
        rows = soup.find_all("tr")
        if len(rows) >= 2:
            tds = rows[1].find_all("td")
            date = tds[0].text.strip()
            # 还原核心：从 tds[3] 提取涨跌幅
            nav = float(tds[3].text.strip().replace("%", ""))
    except: pass
    return name, nav, date

# ================= 🖥️ 侧边栏 =================
with st.sidebar:
    st.title("⚙️ 操作台")
    st.markdown("---")
    code = st.text_input("🔢 基金代码", value="013279")
    money = st.number_input("💰 持有金额", value=10000.0, step=1000.0)
    st.markdown("###")
    run_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)
    st.markdown("---")
    st.caption("涨涨乐 V26.2 | 自动红涨绿跌")

# ================= 📊 主面板 =================
st.title("🚀 涨涨乐")
st.markdown("#### 您的实盘资产驾驶舱")
st.divider()

if run_btn:
    with st.spinner('📡 正在同步最终值与实时估值...'):
        name, last_rate, last_date = get_base_info(code)
        real_rate = calculate_realtime(code, name)
        
        real_profit = money * (real_rate / 100)
        last_profit = money * (last_rate / 100)

        st.subheader(f"📘 {name}")
        
        with st.container():
            k1, k2 = st.columns(2)
            k1.metric(
                label="🔥 实时估值 (今日)",
                value=f"{real_rate:+.2f}%",
                delta=f"{real_profit:+.2f} 元",
                delta_color="inverse"
            )
            k2.metric(
                label=f"📉 官方最终值 ({last_date})",
                value=f"{last_rate:+.2f}%",
                delta=f"{last_profit:+.2f} 元",
                delta_color="inverse"
            )
            
        st.markdown("---")
        if real_profit > 0:
            st.success(f"🎉 这种行情，建议加鸡腿！预计收益：+{real_profit:.2f} 元")
        elif real_profit < 0:
            st.error(f"🍃 莫慌，要做时间的朋友。预计波动：{real_profit:.2f} 元")
        else:
            st.info("☁️ 风平浪静，等待开盘。")
else:
    st.info("👈 请在左侧输入代码，点击【开始分析】")
