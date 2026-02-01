import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 硅谷流体 UI 注入 =================
st.set_page_config(page_title="涨涨乐资产管家", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700;900&display=swap');
    
    html, body, [class*="css"] { font-family: 'Noto Sans SC', sans-serif !important; }
    
    /* 动态微光背景：解决“宽泛”感 */
    .stApp {
        background: radial-gradient(circle at 0% 0%, #f0f2f5 0%, #ffffff 50%, #f8f9fa 100%);
    }

    /* 顶部黑卡：苹果磁吸感 */
    .hero-card {
        background: linear-gradient(135deg, #1c1c1e 0%, #2c2c2e 100%);
        color: white;
        padding: 35px 25px;
        border-radius: 28px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        margin-bottom: 25px;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.05);
    }
    
    /* 基金卡片：极简悬浮 */
    .fund-card {
        background: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(10px);
        padding: 20px;
        border-radius: 24px;
        margin-bottom: 15px;
        border: 1px solid rgba(255, 255, 255, 0.5);
        box-shadow: 0 10px 20px rgba(0,0,0,0.03);
    }

    /* 名字与删除按钮的顺滑排列 */
    .fund-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
    }

    .fund-name { font-size: 16px; font-weight: 700; color: #1c1c1e; }

    /* 左右数据槽位 */
    .data-grid { display: flex; justify-content: space-between; gap: 15px; }
    .data-slot { flex: 1; }
    .label-tag { font-size: 10px; color: #8e8e93; font-weight: 700; margin-bottom: 4px; }
    .num-main { font-size: 26px; font-weight: 900; letter-spacing: -0.5px; }

    /* 优化侧边栏 */
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #f2f2f7; }

    /* 重写按钮样式：让删除按钮变成右上角的小圆点 */
    .stButton > button {
        border: none !important;
        background: #f2f2f7 !important;
        color: #8e8e93 !important;
        border-radius: 50% !important;
        width: 28px !important;
        height: 28px !important;
        padding: 0 !important;
        font-size: 14px !important;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        background: #ff3b30 !important;
        color: white !important;
        transform: rotate(90deg);
    }

    /* 引导磁贴 */
    .guide-box {
        background: white;
        padding: 20px;
        border-radius: 20px;
        text-align: center;
        border: 1px solid #f2f2f7;
        box-shadow: 0 4px 12px rgba(0,0,0,0.02);
    }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="global_refresh")

# ================= 🔧 核心逻辑 (逻辑严密性保持) =================

def get_sina_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0, ""
    try:
        url = f"http://hq.sinajs.cn/list={prefix}{code}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        vals = res.text.split('="')[1].strip('";').split(',')
        curr, last = (float(vals[6]), float(vals[3])) if "hk" in prefix else (float(vals[3]), float(vals[2]))
        return ((curr - last) / last) * 100 if last > 0 else 0.0, (vals[-4] if "hk" not in prefix else vals[-2])
    except: return 0.0, ""

def calc_realtime(code, name):
    factor = 0.99 if any(x in name for x in ["指数", "ETF", "纳指", "标普"]) else 0.92
    try:
        res = requests.get(f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10", timeout=2)
        match = re.search(r'content:"(.*?)"', res.text)
        if match:
            soup = BeautifulSoup(match.group(1), 'html.parser')
            h_data = [(r.find_all("td")[1].text.strip(), float(r.find_all("td")[-3].text.strip().replace("%",""))) for r in soup.find_all("tr")[1:]]
            with ThreadPoolExecutor(max_workers=10) as exe:
                prices = list(exe.map(get_sina_price, [d[0] for d in h_data]))
            chg = sum(p[0]*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data)
            return chg * factor, prices[0][1]
    except: pass
    return 0.0, ""

@st.cache_data(ttl=3600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        name = (re.search(r'name":"(.*?)"', r1.text)).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金-{code}", 0.0, ""

# ================= 📊 界面布局 =================

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

with st.sidebar:
    st.markdown("### 📥 资产录入")
    with st.form("add", clear_on_submit=True):
        c = st.text_input("基金代码", placeholder="如: 000001")
        m = st.number_input("持有金额", value=10000.0)
        if st.form_submit_button("确认录入", use_container_width=True):
            if c: st.session_state.portfolio.append({"c": c, "m": m}); st.rerun()
    if st.button("🗑️ 清空全部"): st.session_state.portfolio = []; st.rerun()

# 主展示区
if st.session_state.portfolio:
    is_weekend = datetime.now().weekday() >= 5
    total_m = sum(i['m'] for i in st.session_state.portfolio)
    mixed_p = 0.0
    fund_details = []

    for i in st.session_state.portfolio:
        name, l_r, l_d = get_info(i['c'])
        r_r, s_d = calc_realtime(i['c'], name)
        eff_r = l_r if is_weekend else (l_r if l_d == datetime.now().strftime('%Y-%m-%d') else r_r)
        mixed_p += i['m'] * (eff_r / 100)
        fund_details.append({"n": name, "m": i['m'], "r": r_r, "l": l_r, "ld": l_d, "sd": s_d})

    # 1. 顶部 Hero
    st.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 11px; opacity: 0.5; letter-spacing: 2px;">{"休市结算已锁定" if is_weekend else "行情实时监控中"}</div>
            <div style="font-size: 56px; font-weight: 900; margin: 10px 0;">¥ {mixed_p:+.2f}</div>
            <div style="font-size: 14px; opacity: 0.8;">本金合计: ¥ {total_m:,.0f} &nbsp; | &nbsp; 预估收益率: {(mixed_p/total_m*100):+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

    # 2. 列表
    for idx, d in enumerate(fund_details):
        with st.container():
            # 利用 columns 将标题和删除按钮放在同一行，并实现“右上角”感
            c1, c2 = st.columns([0.92, 0.08])
            with c1: st.markdown(f'<div class="fund-name">💠 {d["n"]}</div>', unsafe_allow_html=True)
            with c2: 
                if st.button("✕", key=f"d_{idx}"):
                    st.session_state.portfolio.pop(idx); st.rerun()
            
            st.markdown(f"""
                <div class="fund-card" style="margin-top: -15px;">
                    <div class="data-grid">
                        <div class="data-slot">
                            <div class="label-tag">实时估值 [{d['sd'] or '休市'}]</div>
                            <div class="num-main" style="color: {'#ff3b30' if d['r']>0 else '#34c759'};">{d['r']:+.2f}%</div>
                            <div style="font-size:12px; font-weight:700; color:{'#ff3b30' if d['r']>0 else '#34c759'};">¥ {d['m']*d['r']/100:+.2f}</div>
                        </div>
                        <div class="data-slot" style="border-left: 1px solid #f2f2f7; padding-left: 15px;">
                            <div class="label-tag">官方最终值 [{d['ld']}]</div>
                            <div class="num-main" style="color: {'#ff3b30' if d['l']>0 else '#34c759'};">{d['l']:+.2f}%</div>
                            <div style="font-size:12px; font-weight:700; color:{'#ff3b30' if d['l']>0 else '#34c759'};">¥ {d['m']*d['l']/100:+.2f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

else:
    # 3. 初始进入：饱满的引导界面
    st.markdown("""
        <div class="hero-card" style="background: white; color: #1c1c1e; border: 1px solid #e5e5ea;">
            <div style="font-size: 40px; font-weight: 900; margin-bottom: 5px;">0.00</div>
            <p style="color: #8e8e93; font-size: 14px;">等待录入首笔资产以开启实时监控</p>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 10px;">
            <div class="guide-box">
                <div style="font-size: 24px;">🚀</div>
                <div style="font-weight: 700; margin: 8px 0;">秒级同步</div>
                <div style="font-size: 11px; color: #8e8e93;">穿透前十大重仓股<br>实时计算涨跌偏差</div>
            </div>
            <div class="guide-box">
                <div style="font-size: 24px;">🛡️</div>
                <div style="font-weight: 700; margin: 8px 0;">结算锁定</div>
                <div style="font-size: 11px; color: #8e8e93;">周末及收盘后<br>自动锚定官方最终净值</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.info("👈 请点击左侧侧边栏录入您的基金代码。")
