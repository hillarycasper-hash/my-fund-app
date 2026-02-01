import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 极致紧凑 UI 注入 =================
st.set_page_config(page_title="涨涨乐资产管家", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700;900&display=swap');
    
    html, body, [class*="css"] { font-family: 'Noto Sans SC', sans-serif !important; }
    .main { background-color: #f2f2f7; padding: 10px !important; }
    
    /* 顶部黑卡总览 */
    .hero-card {
        background: #1c1c1e;
        color: white;
        padding: 30px 20px;
        border-radius: 24px;
        box-shadow: 0 15px 30px rgba(0,0,0,0.15);
        margin-bottom: 20px;
        text-align: center;
    }
    
    /* 资产磁贴：拒绝虚化，保持清晰 */
    .fund-card {
        background: white;
        padding: 20px;
        border-radius: 20px;
        margin-bottom: 15px;
        border: 1px solid #e5e5ea;
    }
    
    .val-box { text-align: left; flex: 1; }
    .label-tag { font-size: 11px; color: #8e8e93; font-weight: 700; margin-bottom: 4px; }
    .num-main { font-size: 24px; font-weight: 900; letter-spacing: -0.5px; line-height: 1; }
    .num-sub { font-size: 12px; margin-top: 5px; font-weight: 600; }
    
    /* 紧凑按钮 */
    .stButton>button { 
        width: 100%; border-radius: 10px; height: 32px; font-size: 12px; 
        background: #f2f2f7; border: none; color: #8e8e93; 
    }
    
    /* 初始界面：功能介绍区 */
    .intro-grid {
        display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px;
    }
    .intro-item {
        background: white; padding: 15px; border-radius: 15px; text-align: center; font-size: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ================= 🔧 核心逻辑 (100% 保持 0.92/0.99 系数) =================

def get_sina_stock_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0, ""
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        vals = res.text.split('="')[1].strip('";').split(',')
        curr, last = (float(vals[6]), float(vals[3])) if "hk" in prefix else (float(vals[3]), float(vals[2]))
        # 提取股票接口里的日期
        t_date = vals[-4] if "hk" not in prefix else vals[-2]
        return ((curr - last) / last) * 100 if last > 0 else 0.0, t_date
    except: return 0.0, ""

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
    # 【系数逻辑】保留：指数类0.99，主动类0.92
    factor = 0.99 if any(x in fund_name for x in ["指数", "ETF", "联接", "互联网", "纳斯达克"]) else 0.92
    holdings = get_holdings_data(fund_code)
    if not holdings: return 0.0, ""
    with ThreadPoolExecutor(max_workers=10) as executor:
        prices = list(executor.map(get_sina_stock_price, [h[0] for h in holdings]))
    total_chg = sum(p[0] * h[1] for p, h in zip(prices, holdings))
    total_w = sum(h[1] for h in holdings)
    return (total_chg / total_w) * factor if total_w > 0 else 0.0, prices[0][1]

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

# ================= 💾 资产列表处理 =================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

with st.sidebar:
    st.markdown("### 📥 录入资产")
    with st.form("add_fund", clear_on_submit=True):
        f_code = st.text_input("基金代码", placeholder="例如: 013279")
        f_money = st.number_input("持有本金", value=10000.0, step=1000.0)
        if st.form_submit_button("确认存入资产库", use_container_width=True):
            if f_code: st.session_state.portfolio.append({"code": f_code, "money": f_money}); st.rerun()
    st.markdown("---")
    if st.button("🗑️ 清空所有数据"): st.session_state.portfolio = []; st.rerun()

# ================= 📊 主显示区 =================
if st.session_state.portfolio:
    with st.spinner('正在同步全球行情...'):
        total_m = sum(i['money'] for i in st.session_state.portfolio)
        is_weekend = datetime.now().weekday() >= 5
        mixed_total_profit = 0.0
        details = []

        for i in st.session_state.portfolio:
            name, last_r, last_d = get_base_info(i['code'])
            real_r, stock_d = calculate_realtime(i['code'], name)
            
            # 【逻辑锁定】：周末总盈亏锁定为周五最终值
            effective_r = last_r if is_weekend else (last_r if last_d == datetime.now().strftime('%Y-%m-%d') else real_r)
            mixed_total_profit += i['money'] * (effective_r / 100)
            details.append({"name": name, "money": i['money'], "real": real_r, "last": last_r, "l_date": last_d, "s_date": stock_d})

    # 1. 顶部总览
    status_label = "休市结算已锁定" if is_weekend else "交易实时追踪中"
    st.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 12px; opacity: 0.6; letter-spacing: 2px; margin-bottom: 10px;">{status_label}</div>
            <div style="font-size: 50px; font-weight: 900; margin: 5px 0;">¥ {mixed_total_profit:+.2f}</div>
            <div style="font-size: 14px; opacity: 0.8;">持仓总本金: ¥ {total_m:,.0f} &nbsp; | &nbsp; 预估总收益率: {(mixed_total_profit/total_m*100):+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

    # 2. 持仓列表
    st.markdown("### 💠 实时监控详情")
    for idx, d in enumerate(details):
        st.markdown(f"""
            <div class="fund-card">
                <div style="font-size: 16px; font-weight: 700; color: #1c1c1e; margin-bottom: 15px; border-bottom: 1px solid #f2f2f7; padding-bottom: 10px;">{d['name']}</div>
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div class="val-box">
                        <div class="label-tag">实时估值 [{d['s_date'] or '休市'}]</div>
                        <div class="num-main" style="color: {'#ff3b30' if d['real']>0 else '#34c759'};">{d['real']:+.2f}%</div>
                        <div class="num-sub" style="color: {'#ff3b30' if d['real']>0 else '#34c759'};">¥ {d['money']*d['real']/100:+.2f}</div>
                    </div>
                    <div class="val-box" style="border-left: 1px solid #f2f2f7; padding-left: 20px;">
                        <div class="label-tag">官方最终值 [{d['l_date']}]</div>
                        <div class="num-main" style="color: {'#ff3b30' if d['last']>0 else '#34c759'};">{d['last']:+.2f}%</div>
                        <div class="num-sub" style="color: {'#ff3b30' if d['last']>0 else '#34c759'};">¥ {d['money']*d['last']/100:+.2f}</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        if st.button(f"移除 {d['name'][:6]}", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx); st.rerun()

else:
    # 3. 初始进入画面：更紧凑、更有指引感
    st.markdown("""
        <div class="hero-card" style="background: white; color: #1c1c1e; border: 1px solid #e5e5ea;">
            <h1 style="font-size: 32px; font-weight: 900; margin-bottom: 10px;">待录入资产</h1>
            <p style="color: #8e8e93; font-size: 14px;">请在侧边栏添加基金代码，开始享受硅谷级数据监控</p>
        </div>
        <div class="intro-grid">
            <div class="intro-item"><b>🎯 实时拟合</b><br>基于持仓穿透计算，乘以 0.92 动态系数</div>
            <div class="intro-item"><b>⏳ 自动结算</b><br>晚间官方更新后，自动切换至最终收益</div>
            <div class="intro-item"><b>📊 偏差监控</b><br>实时 vs 最终，一眼看清估值误差</div>
            <div class="intro-item"><b>⚡ 多线程同步</b><br>秒级拉取 10 大重仓股实时报价</div>
        </div>
    """, unsafe_allow_html=True)
    st.info("👈 点击左侧侧边栏开始录入第一笔资产")
