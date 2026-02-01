import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 硅谷极简 UI 注入 =================
st.set_page_config(page_title="涨涨乐 Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif !important; }
    .main { background-color: #f5f5f7; }
    
    /* 顶部 Hero 区域 */
    .hero-card {
        background: #1c1c1e;
        color: white;
        padding: 40px 24px;
        border-radius: 32px;
        text-align: center;
        box-shadow: 0 20px 40px rgba(0,0,0,0.12);
        margin-bottom: 30px;
    }

    /* 苹果风毛玻璃卡片 */
    .fund-tile {
        background: white;
        padding: 24px;
        border-radius: 24px;
        margin-bottom: 20px;
        border: 1px solid #e5e5ea;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }

    .label-caps { 
        font-size: 11px; 
        color: #8e8e93; 
        font-weight: 700; 
        text-transform: uppercase; 
        letter-spacing: 0.5px;
        margin-bottom: 6px;
    }
    
    .val-large { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }
    .val-sub { font-size: 15px; font-weight: 500; margin-top: 2px; }
    
    /* 状态标签 */
    .status-tag {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 100px;
        font-size: 11px;
        font-weight: 700;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ================= 🔧 核心逻辑 (100% 保持原始系数与算法) =================

def get_sina_stock_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        # 获取股票最后交易时间 (新浪接口 vals[-3] 或 vals[-4] 附近)
        vals = res.text.split('="')[1].strip('";').split(',')
        curr, last = (float(vals[6]), float(vals[3])) if "hk" in prefix else (float(vals[3]), float(vals[2]))
        trade_date = vals[-4] if "hk" not in prefix else vals[-2]
        return ((curr - last) / last) * 100 if last > 0 else 0.0, trade_date
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

def calculate_realtime_v2(fund_code, fund_name):
    # 系数保持不变
    factor = 0.99 if any(x in fund_name for x in ["指数", "ETF", "联接", "互联网"]) else 0.92
    holdings = get_holdings_data(fund_code)
    if not holdings: return 0.0, ""
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_sina_stock_price, [h[0] for h in holdings]))
    
    total_chg = sum(r[0] * h[1] for r, h in zip(results, holdings))
    total_w = sum(h[1] for h in holdings)
    trade_date = results[0][1] if results else "" # 取其中一只股票的交易日期作为参考
    return (total_chg / total_w) * factor if total_w > 0 else 0.0, trade_date

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

# ================= 💾 处理流程 =================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

with st.sidebar:
    st.markdown("### 📥 持仓管理")
    with st.form("add_fund", clear_on_submit=True):
        f_code = st.text_input("代码", placeholder="输入代码")
        f_money = st.number_input("金额", value=10000.0)
        if st.form_submit_button("确认添加", use_container_width=True):
            if f_code: st.session_state.portfolio.append({"code": f_code, "money": f_money}); st.rerun()
    if st.button("🗑️ 清空实盘"): st.session_state.portfolio = []; st.rerun()

# ================= 📊 主显示区 =================
if st.session_state.portfolio:
    with st.spinner('Synchronizing Data...'):
        total_m = sum(i['money'] for i in st.session_state.portfolio)
        is_weekend = datetime.now().weekday() >= 5
        mixed_profit = 0.0
        details = []

        for item in st.session_state.portfolio:
            name, last_r, last_d = get_base_info(item['code'])
            real_r, stock_d = calculate_realtime_v2(item['code'], name)
            
            # 【结算核心逻辑】
            # 周末直接锁定最终值；工作日若官方没更新则看估值
            if is_weekend:
                active_rate = last_r
                status = "OFF-MARKET SETTLED"
            elif last_d == datetime.now().strftime('%Y-%m-%d'):
                active_rate = last_r
                status = "OFFICIAL SETTLED"
            else:
                active_rate = real_r
                status = "LIVE ESTIMATING"

            mixed_profit += item['money'] * (active_rate / 100)
            details.append({"name": name, "money": item['money'], "real": real_r, "last": last_r, "l_date": last_d, "s_date": stock_d, "status": status})

    # 1. 顶部总览卡片
    bg_color = "#1c1c1e" if not is_weekend else "#2c2c2e"
    st.markdown(f"""
        <div class="hero-card" style="background: {bg_color}">
            <div class="status-tag" style="background: rgba(255,255,255,0.15); color: white;">
                {status_text := "周末市场休市 · 收益已锁定" if is_weekend else "交易时段 · 实时动态监控"}
            </div>
            <div style="font-size: 60px; font-weight: 700; margin: 10px 0;">¥ {mixed_profit:+.2f}</div>
            <p style="opacity: 0.6; font-size: 15px;">总资产本金: ¥ {total_m:,.0f} &nbsp; • &nbsp; 总收益率: {(mixed_profit/total_m*100):+.2f}%</p>
        </div>
    """, unsafe_allow_html=True)

    # 2. 基金详情卡片
    st.markdown("### 💠 持仓明细对比")
    for idx, d in enumerate(details):
        st.markdown(f"""
            <div class="fund-tile">
                <div style="font-weight: 700; font-size: 18px; margin-bottom: 20px;">{d['name']}</div>
                <div style="display: flex; gap: 40px;">
                    <div style="flex: 1;">
                        <div class="label-caps">实时估值 [{d['s_date'] or '休市'}]</div>
                        <div class="val-large" style="color: {'#ff3b30' if d['real']>0 else '#34c759'}; opacity: {0.4 if is_weekend else 1};">
                            {d['real']:+.2f}%
                        </div>
                        <div class="val-sub" style="color: {'#ff3b30' if d['real']>0 else '#34c759'}; opacity: {0.4 if is_weekend else 1};">¥ {d['money']*d['real']/100:+.2f}</div>
                    </div>
                    <div style="flex: 1; border-left: 1px solid #f2f2f7; padding-left: 40px;">
                        <div class="label-caps">官方最终值 [{d['l_date']}]</div>
                        <div class="val-large" style="color: {'#ff3b30' if d['last']>0 else '#34c759'};">{d['last']:+.2f}%</div>
                        <div class="val-sub" style="color: {'#ff3b30' if d['last']>0 else '#34c759'};">¥ {d['money']*d['last']/100:+.2f}</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        if st.button(f"移除 {d['name'][:4]}", key=f"del_{idx}"):
            st.session_state.portfolio.pop(idx); st.rerun()

else:
    st.info("💡 请在左侧侧边栏录入基金代码，开启硅谷级资产监控。")
