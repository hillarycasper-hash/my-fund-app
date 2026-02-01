import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor

# ================= 🎨 页面基础设置 =================
st.set_page_config(page_title="涨涨乐 🚀", page_icon="🚀", layout="wide")

# ================= 🔧 核心函数 (逻辑回归老版本，仅底层提速) =================

def get_sina_stock_price(code):
    prefix = ""
    if code.startswith('6') or code.startswith('5') or code.startswith('11'): prefix = "sh"
    elif code.startswith('0') or code.startswith('3') or code.startswith('1') or code.startswith('15'): prefix = "sz"
    elif len(code) == 5: prefix = "rt_hk"
    
    if not prefix: return 0.0
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        if len(res.text) < 20: return 0.0
        parts = res.text.split('="')
        vals = parts[1].strip('";').split(',')
        
        # 100% 还原老版本解析逻辑
        if "hk" in prefix:
            curr, last = float(vals[6]), float(vals[3])
        else:
            curr, last = float(vals[3]), float(vals[2])
            
        if curr == 0: curr = last
        if last > 0: return ((curr - last) / last) * 100
    except: pass
    return 0.0

# 100% 还原老版本的保底字典
def smart_fallback_benchmark(fund_code, fund_name):
    map_dict = {
        "白银": ("161226", 1.0), "黄金": ("518800", 1.0), "豆粕": ("159985", 1.0),
        "光伏": ("515790", 0.98), "新能源": ("516160", 0.98), "医疗": ("512170", 0.98),
        "白酒": ("512690", 0.98), "半导体": ("512480", 0.98), "军工": ("512660", 0.98),
        "券商": ("512880", 0.98), "纳指": ("513100", 0.96), "标普": ("513500", 0.96),
        "300": ("510300", 0.99), "创业板": ("159915", 0.99),
        "互联网": ("HSTECH", 1.0) 
    }
    for k, v in map_dict.items():
        if k in fund_name: return v[0], v[1]
    return None, 0.95

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
    # 100% 还原老版本系数
    factor = 0.99 if ("互联网" in fund_name or "ETF" in fund_name or "联接" in fund_name) else 0.92
    holdings = get_holdings_data(fund_code)

    if holdings:
        # 并发获取价格以提速
        with ThreadPoolExecutor(max_workers=10) as executor:
            prices = list(executor.map(get_sina_stock_price, [h[0] for h in holdings]))
        
        total_chg = sum(p * h[1] for p, h in zip(prices, holdings))
        total_w = sum(h[1] for h in holdings)
        if total_w > 0: return (total_chg / total_w) * factor
    
    # 100% 还原老版本的保底计算逻辑
    bench_code, bench_factor = smart_fallback_benchmark(fund_code, fund_name)
    if bench_code:
        if bench_code == "HSTECH":
            return get_sina_stock_price("HSTECH") * 1.0
        return get_sina_stock_price(bench_code) * bench_factor
    return 0.0

@st.cache_data(ttl=3600)
def get_base_info(code):
    name, nav, date = f"基金-{code}", 0.0, ""
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(requests.get, f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
            f2 = executor.submit(requests.get, f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
            r1, r2 = f1.result(), f2.result()
        
        m1 = re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)
        if m1: name = m1.group(1)
        
        soup = BeautifulSoup(r2.text, 'html.parser')
        rows = soup.find_all("tr")
        if len(rows) >= 2:
            tds = rows[1].find_all("td")
            date, nav = tds[0].text.strip(), float(tds[3].text.strip().replace("%", ""))
    except: pass
    return name, nav, date

# ================= 🖥️ 侧边栏与主界面 =================
with st.sidebar:
    st.title("⚙️ 操作台")
    code = st.text_input("🔢 基金代码", value="013279")
    money = st.number_input("💰 持有金额", value=10000.0)
    run_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)
    if st.button("🔄 刷新缓存"): st.cache_data.clear()

st.title("🚀 涨涨乐")
st.divider()

if run_btn:
    with st.spinner('⚡ 正在极速同步...'):
        name, last_rate, last_date = get_base_info(code)
        real_rate = calculate_realtime(code, name)
        
        real_profit, last_profit = money * (real_rate / 100), money * (last_rate / 100)
        st.subheader(f"📘 {name}")
        
        k1, k2 = st.columns(2)
        k1.metric("🔥 实时估值 (今日)", f"{real_rate:+.2f}%", f"{real_profit:+.2f} 元", delta_color="inverse")
        k2.metric(f"📉 官方最终值 ({last_date})", f"{last_rate:+.2f}%", f"{last_profit:+.2f} 元", delta_color="inverse")
        
        if real_profit > 0: st.success(f"🎉 建议加鸡腿！预计收益：+{real_profit:.2f} 元")
        else: st.error(f"🍃 莫慌，要做时间的朋友。")
else:
    st.info("👈 请在左侧输入代码")
