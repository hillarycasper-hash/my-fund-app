import streamlit as st
import requests
import re
import sqlite3
import json
import random
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 1. 移动端专属 CSS 优化 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")
st_autorefresh(interval=60 * 1000, key="global_refresh")

st.markdown("""
    <style>
    .stApp { background-color: #f5f7f9; }
    
    /* --- 顶部横向滚动容器 (解决竖排问题) --- */
    .scroll-container {
        display: flex;
        overflow-x: auto;
        white-space: nowrap;
        padding: 10px 5px;
        gap: 12px;
        -webkit-overflow-scrolling: touch; /* 顺滑滚动 */
        scrollbar-width: none; /* 隐藏滚动条 */
    }
    .scroll-container::-webkit-scrollbar { display: none; }
    
    .market-item {
        background: white;
        min-width: 110px; /* 固定宽度，保证横排 */
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        border: 1px solid #eee;
    }
    
    /* --- 核心资产卡片 --- */
    .hero-card { 
        background: linear-gradient(135deg, #2b2e4a 0%, #1f1f1f 100%); 
        color: #e5c07b; 
        padding: 25px 20px; 
        border-radius: 20px; 
        text-align: center; 
        margin-bottom: 20px; 
        box-shadow: 0 8px 20px rgba(0,0,0,0.15);
    }
    
    /* --- 基金卡片 (双数据并存) --- */
    .fund-card-new {
        background: white;
        border-radius: 16px;
        padding: 15px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        border: 1px solid #f0f0f0;
    }
    
    /* 辅助样式 */
    .up { color: #e74c3c !important; }
    .down { color: #2ecc71 !important; }
    .label { font-size: 10px; color: #999; display: block; margin-bottom: 2px;}
    .val-big { font-size: 18px; font-weight: 800; }
    .val-small { font-size: 14px; font-weight: 600; }
    .money-tag { background: #fff5f5; color: #e74c3c; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# ================= 🔧 2. 数据引擎 =================

def init_db():
    conn = sqlite3.connect('zzl_mobile_v16.db', check_same_thread=False)
    conn.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    return conn

db_conn = init_db()

@st.cache_data(ttl=30, show_spinner=False)
def get_market_scroll_data():
    """获取大盘数据，返回HTML字符串供横向渲染"""
    codes = [
        ('sh000001', '上证指数'),
        ('sz399006', '创业板指'),
        ('rt_hkHSI', '恒生指数'),
        ('gb_ixic',  '纳斯达克'),
        ('fx_susdcnh', '美元离岸') 
    ]
    html_items = ""
    try:
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])}"
        r = requests.get(url, headers={'Referer': 'sina.com'}, timeout=2)
        lines = r.text.strip().split('\n')
        
        for i, line in enumerate(lines):
            if len(line) < 20: continue
            parts = line.split('="')[1].split(',')
            # 解析不同市场
            if 'fx_' in codes[i][0]: cur, last = float(parts[8]), float(parts[3])
            elif 'gb_' in codes[i][0]: cur, last = float(parts[1]), float(parts[26])
            elif 'hk' in codes[i][0]: cur, last = float(parts[6]), float(parts[3])
            else: cur, last = float(parts[3]), float(parts[2])
            
            change = cur - last
            pct = (change / last) * 100
            color = "up" if change >= 0 else "down"
            arrow = "▲" if change >= 0 else "▼"
            
            # 拼接HTML Item
            html_items += f"""
            <div class="market-item">
                <div style="font-size:11px; color:#666; margin-bottom:4px;">{codes[i][1]}</div>
                <div class="{color}" style="font-size:16px; font-weight:800; font-family:sans-serif;">{cur:.2f}</div>
                <div class="{color}" style="font-size:10px; font-weight:600;">{arrow} {pct:.2f}%</div>
            </div>
            """
    except: pass
    return html_items

@st.cache_data(ttl=60, show_spinner=False)
def get_fund_both_data(code):
    """同时获取实时和昨日数据，不进行掩盖"""
    try:
        # 接口1：实时估值
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        # 接口2：确权净值
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        name = "读取中..."
        if "name" in r_gs.text:
            name = re.search(r'name":"(.*?)"', r_gs.text).group(1)
        
        # 1. 抓取实时估值 (Real-time)
        gz_rate = 0.0
        if "gszzl" in r_gs.text:
            gz_rate = float(re.search(r'gszzl":"(.*?)"', r_gs.text).group(1))
        
        # 2. 抓取昨日净值 (Final Close)
        jz_rate = 0.0
        jz_date = "--"
        tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
        if len(tds) > 3:
            jz_date = tds[0].text.strip()
            val_str = tds[3].text.strip().replace("%","")
            jz_rate = float(val_str) if val_str else 0.0
            
        return {"n": name, "gz": gz_rate, "jz": jz_rate, "d": jz_date}
    except:
        return None

# ================= 🚪 3. 登录与主程序 =================
if 'user_token' not in st.session_state: st.session_state.user_token = None
if 'portfolio' not in st.session_state: st.session_state.portfolio = []

if not st.session_state.user_token:
    st.markdown("<br><h2 style='text-align:center;'>🚀 涨涨乐 Pro</h2>", unsafe_allow_html=True)
    tk = st.text_input("🔑 识别码", placeholder="输入 6 位识别码")
    if st.button("进入系统", type="primary", use_container_width=True):
        if tk:
            res = db_conn.execute('SELECT portfolio FROM users WHERE token=?', (tk,)).fetchone()
            st.session_state.user_token = tk
            st.session_state.portfolio = json.loads(res[0]) if res else []
            st.rerun()
    if st.button("新用户生成", use_container_width=True):
        st.session_state.user_token = str(random.randint(100000, 999999))
        st.session_state.portfolio = []
        st.rerun()
    st.stop()

# ================= 📱 4. 移动端看板逻辑 =================

# [解决图1]：横向滚动行情栏
st.markdown("##### 🌏 全球行情 (左右滑动)")
market_html = get_market_scroll_data()
if market_html:
    st.markdown(f'<div class="scroll-container">{market_html}</div>', unsafe_allow_html=True)
else:
    st.info("⌛️ 正在初始化行情数据...")

# 资产计算
total_asset = sum(float(i['m']) for i in st.session_state.portfolio)
total_profit_gz = 0.0 # 估值总收益
valid_list = []

for p in st.session_state.portfolio:
    d = get_fund_both_data(p['c'])
    if d:
        p_money = p['m'] * (d['gz'] / 100)
        total_profit_gz += p_money
        valid_list.append({**p, **d, 'p_money': p_money})

# 顶部总资产卡片 (显示估值收益)
st.markdown(f"""
<div class="hero-card">
    <div style="font-size:13px; opacity:0.7;">今日预估总收益 (CNY)</div>
    <div style="font-size:42px; font-weight:900; margin:8px 0; color:{'#ff6b6b' if total_profit_gz>=0 else '#2ecc71'};">
        {'+' if total_profit_gz>0 else ''}{total_profit_gz:,.2f}
    </div>
    <div style="font-size:12px; opacity:0.8;">
        总本金: ¥{total_asset:,.0f} | 综合收益率: {(total_profit_gz/total_asset*100) if total_asset>0 else 0:+.2f}%
    </div>
</div>
""", unsafe_allow_html=True)

# [解决图2]：双数据展示列表
st.markdown(f"##### 📑 持仓明细 ({len(valid_list)})")

if not valid_list:
    st.info("👇 点击左上角 `>` 箭头打开侧边栏添加基金")

for item in valid_list:
    # 颜色判断
    c_gz = "up" if item['gz'] >= 0 else "down"
    c_jz = "up" if item['jz'] >= 0 else "down"
    
    with st.container():
        c1, c2 = st.columns([0.85, 0.15])
        with c1:
            st.markdown(f"""
            <div class="fund-card-new">
                <div style="font-size:15px; font-weight:bold; margin-bottom:8px;">
                    {item['n']} <span style="font-size:12px; color:#aaa; font-weight:normal;">{item['c']}</span>
                </div>
                
                <div style="display:flex; justify-content: space-between; align-items: flex-end;">
                    
                    <div style="text-align:left;">
                        <span class="label">🔥 实时估值</span>
                        <div class="val-big {c_gz}">{item['gz']:+.2f}%</div>
                        <span class="money-tag" style="color:{'#e74c3c' if item['p_money']>=0 else '#2ecc71'}; background:{'#fff5f5' if item['p_money']>=0 else '#f0fff4'};">
                            ¥ {item['p_money']:+.2f}
                        </span>
                    </div>
                    
                    <div style="width:1px; height:30px; background:#eee; margin:0 10px;"></div>

                    <div style="text-align:right;">
                        <span class="label">🏁 昨日 ({item['d'][5:]})</span>
                        <div class="val-small {c_jz}">{item['jz']:+.2f}%</div>
                        <div style="font-size:11px; color:#999;">本金: {int(item['m'])}</div>
                    </div>
                    
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        if c2.button("🗑", key=f"del_{item['c']}", help="删除"):
            st.session_state.portfolio = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
            db_conn.commit()
            st.rerun()

# ================= 🛠️ 5. 侧边栏 =================
with st.sidebar:
    st.write(f"👤 用户: **{st.session_state.user_token}**")
    if st.button("🚪 退出登录"):
        st.session_state.user_token = None
        st.rerun()
    st.markdown("---")
    with st.form("add"):
        c = st.text_input("代码", placeholder="如 014143")
        m = st.number_input("金额", value=10000.0)
        if st.form_submit_button("➕ 添加"):
            with st.spinner("验证中..."):
                chk = get_fund_both_data(c)
                if chk:
                    # 更新或添加
                    new_p = [x for x in st.session_state.portfolio if x['c'] != c]
                    new_p.append({"c": c, "m": m})
                    st.session_state.portfolio = new_p
                    db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(new_p)))
                    db_conn.commit()
                    st.success("已添加")
                    st.rerun()
                else:
                    st.error("无效代码")
