import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 交互升级 UI 注入 =================
st.set_page_config(page_title="涨涨乐 Pro", page_icon="📈", layout="wide")

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
    
    /* 资产磁贴 */
    .fund-card {
        background: white;
        padding: 18px;
        border-radius: 22px;
        margin-bottom: 15px;
        border: 1px solid #e5e5ea;
    }

    /* 标题栏容器：实现名字和按钮在一行 */
    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 1px solid #f2f2f7;
    }

    .fund-name {
        font-size: 15px;
        font-weight: 700;
        color: #1c1c1e;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 80%;
    }

    /* 左右对齐的数据盒子 */
    .flex-container { display: flex; justify-content: space-between; }
    .val-box { flex: 1; }
    .label-tag { font-size: 10px; color: #8e8e93; font-weight: 700; margin-bottom: 4px; text-transform: uppercase; }
    .num-main { font-size: 24px; font-weight: 900; letter-spacing: -0.5px; }
    .num-sub { font-size: 12px; margin-top: 2px; font-weight: 600; }

    /* 紧凑型删除按钮样式覆盖 */
    .stButton > button {
        border: none !important;
        background-color: transparent !important;
        color: #c7c7cc !important;
        padding: 0 !important;
        width: 30px !important;
        height: 30px !important;
        font-size: 18px !important;
        line-height: 1 !important;
    }
    .stButton > button:hover { color: #ff3b30 !important; background: #fff5f5 !important; border-radius: 50%; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ================= 🔧 核心逻辑 (0.92/0.99 系数 100% 保持) =================

def get_sina_stock_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0, ""
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        vals = res.text.split('="')[1].strip('";').split(',')
        curr, last = (float(vals[6]), float(vals[3])) if "hk" in prefix else (float(vals[3]), float(vals[2]))
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

# ================= 💾 数据状态 =================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

with st.sidebar:
    st.markdown("### 📥 录入资产")
    with st.form("add_fund", clear_on_submit=True):
        f_code = st.text_input("基金代码", placeholder="013279")
        f_money = st.number_input("持有本金", value=10000.0)
        if st.form_submit_button("存入库", use_container_width=True):
            if f_code: st.session_state.portfolio.append({"code": f_code, "money": f_money}); st.rerun()

# ================= 📊 主显示区 =================
if st.session_state.portfolio:
    total_m = sum(i['money'] for i in st.session_state.portfolio)
    is_weekend = datetime.now().weekday() >= 5
    mixed_total_profit = 0.0
    
    # 顶部 Hero
    hero_container = st.empty()
    
    st.markdown("### 💠 实时详情对比")
    
    for idx, i in enumerate(st.session_state.portfolio):
        name, last_r, last_d = get_base_info(i['code'])
        real_r, stock_d = calculate_realtime(i['code'], name)
        
        # 结算逻辑
        eff_r = last_r if is_weekend else (last_r if last_d == datetime.now().strftime('%Y-%m-%d') else real_r)
        mixed_total_profit += i['money'] * (eff_r / 100)
        
        # --- 🚀 核心改变：标题与删除按钮并排 ---
        with st.container():
            # 使用 columns 实现标题和删除按钮的紧凑对齐
            col_title, col_del = st.columns([0.9, 0.1])
            with col_title:
                st.markdown(f'<div class="fund-name">{name}</div>', unsafe_allow_html=True)
            with col_del:
                if st.button("✕", key=f"del_{idx}"):
                    st.session_state.portfolio.pop(idx)
                    st.rerun()
            
            # 数据对比区
            st.markdown(f"""
                <div class="fund-card" style="margin-top: -20px;">
                    <div class="flex-container">
                        <div class="val-box">
                            <div class="label-tag">实时估值 [{stock_d or '休市'}]</div>
                            <div class="num-main" style="color: {'#ff3b30' if real_r>0 else '#34c759'};">{real_r:+.2f}%</div>
                            <div class="num-sub" style="color: {'#ff3b30' if real_r>0 else '#34c759'};">¥ {i['money']*real_r/100:+.2f}</div>
                        </div>
                        <div class="val-box" style="border-left: 1px solid #f2f2f7; padding-left: 15px;">
                            <div class="label-tag">官方最终值 [{last_d}]</div>
                            <div class="num-main" style="color: {'#ff3b30' if last_r>0 else '#34c759'};">{last_r:+.2f}%</div>
                            <div class="num-sub" style="color: {'#ff3b30' if last_r>0 else '#34c759'};">¥ {i['money']*last_r/100:+.2f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # 更新顶部卡片
    hero_container.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 11px; opacity: 0.5; letter-spacing: 1px; margin-bottom: 8px;">{"周末休市 · 锁定官方结算" if is_weekend else "交易时段 · 实时监控中"}</div>
            <div style="font-size: 52px; font-weight: 900; line-height: 1;">¥ {mixed_total_profit:+.2f}</div>
            <div style="font-size: 14px; opacity: 0.7; margin-top: 8px;">本金: ¥ {total_m:,.0f} &nbsp; | &nbsp; 收益率: {(mixed_total_profit/total_m*100):+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

else:
    st.markdown('<div class="hero-card" style="background:white; color:#1c1c1e; border:1px solid #e5e5ea;"><h2>待录入资产</h2><p>点击侧边栏添加基金</p></div>', unsafe_allow_html=True)
