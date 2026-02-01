import streamlit as st
import requests
import re
import sqlite3
import json
import random
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 1. 深度美化与配置 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")
st_autorefresh(interval=60 * 1000, key="global_refresh") # 1分钟自动刷新

# 隐藏默认的 ugly 菜单和加载条，使用自定义 CSS 美化
st.markdown("""
    <style>
    /* 全局背景 */
    .stApp { background-color: #f5f7f9; }
    
    /* 顶部行情卡片 */
    .market-card {
        background: white; 
        padding: 12px; 
        border-radius: 12px; 
        text-align: center; 
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: transform 0.2s;
        margin-bottom: 5px;
    }
    .market-card:hover { transform: translateY(-2px); }
    .m-name { font-size: 12px; color: #666; margin-bottom: 4px; }
    .m-price { font-size: 18px; font-weight: 800; font-family: 'DIN Alternate', sans-serif; }
    .m-change { font-size: 11px; font-weight: 600; margin-top: 2px; }
    
    /* 核心资产卡片 (黑金风格) */
    .hero-card { 
        background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%); 
        color: #e5c07b; 
        padding: 30px; 
        border-radius: 24px; 
        text-align: center; 
        margin-bottom: 25px; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.15);
    }
    
    /* 基金列表卡片 */
    .fund-row {
        background: white;
        padding: 20px;
        border-radius: 16px;
        margin-bottom: 15px;
        border-left: 5px solid #ddd;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    
    /* 涨跌颜色定义 */
    .up { color: #eb4d3d !important; }   /* 红涨 */
    .down { color: #27c25c !important; } /* 绿跌 */
    .flat { color: #888 !important; }
    </style>
    """, unsafe_allow_html=True)

# ================= 🔧 2. 核心功能 (已隐藏代码提示) =================

def init_db():
    conn = sqlite3.connect('zzl_final_v15.db', check_same_thread=False)
    conn.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    return conn

db_conn = init_db()

# 关键修改：show_spinner=False 彻底隐藏那个丑陋的 running 代码提示
@st.cache_data(ttl=30, show_spinner=False)
def get_market_dashboard():
    """获取多维市场数据：上证、创业、恒生、纳指、美元离岸"""
    # 新浪财经接口代码
    codes = [
        ('sh000001', '上证指数'),
        ('sz399006', '创业板指'),
        ('rt_hkHSI', '恒生指数'),
        ('gb_ixic',  '纳斯达克'),
        ('fx_susdcnh', '美元/人民币') 
    ]
    results = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])}"
        r = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=2)
        lines = r.text.strip().split('\n')
        
        for i, line in enumerate(lines):
            if len(line) < 20: continue
            parts = line.split('="')[1].split(',')
            name = codes[i][1]
            
            # 解析不同市场的格式
            if 'fx_' in codes[i][0]: # 汇率
                cur = float(parts[8])
                last = float(parts[3])
            elif 'gb_' in codes[i][0]: # 美股
                cur = float(parts[1])
                last = float(parts[26])
            elif 'hk' in codes[i][0]: # 港股
                cur = float(parts[6])
                last = float(parts[3])
            else: # A股
                cur = float(parts[3])
                last = float(parts[2])
                
            change = cur - last
            pct = (change / last) * 100
            results.append({"n": name, "p": cur, "c": change, "pct": pct})
    except:
        # 如果接口挂了，返回空列表，UI层会处理，不会报错
        pass
    return results

# 关键修改：show_spinner=False，用户不会看到 get_fund_full_data 这行字
@st.cache_data(ttl=60, show_spinner=False)
def get_fund_details(code):
    try:
        # 接口1：实时
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        # 接口2：历史
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        name = "未知基金"
        if "nameFormat" in r1.text:
            name = re.search(r'nameFormat":"(.*?)"', r1.text).group(1)
        elif "name" in r1.text:
            name = re.search(r'name":"(.*?)"', r1.text).group(1)
            
        # 实时估值
        r_real = 0.0
        if "gszzl" in r1.text:
            r_real = float(re.search(r'gszzl":"(.*?)"', r1.text).group(1))
            
        # 昨日数据
        l_r = 0.0
        l_d = "--"
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        if len(tds) > 3:
            l_d = tds[0].text.strip()
            l_r_str = tds[3].text.strip().replace("%","")
            l_r = float(l_r_str) if l_r_str else 0.0
            
        return {"name": name, "real": r_real, "last": l_r, "date": l_d}
    except:
        return None

# ================= 🚪 3. 登录逻辑 =================
if 'user_token' not in st.session_state: st.session_state.user_token = None
if 'portfolio' not in st.session_state: st.session_state.portfolio = []

if not st.session_state.user_token:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<h1 style='text-align:center;'>🚀 涨涨乐 Pro</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#888;'>极简 · 实时 · 纯净</p>", unsafe_allow_html=True)
        tk = st.text_input("🔑 请输入识别码", placeholder="例如: 888888")
        if st.button("立即进入", type="primary", use_container_width=True):
            if tk:
                res = db_conn.execute('SELECT portfolio FROM users WHERE token=?', (tk,)).fetchone()
                st.session_state.user_token = tk
                st.session_state.portfolio = json.loads(res[0]) if res else []
                st.rerun()
        
        if st.button("我是新用户 (生成识别码)", use_container_width=True):
            new_tk = str(random.randint(100000, 999999))
            st.session_state.user_token = new_tk
            st.session_state.portfolio = []
            st.rerun()
    st.stop()

# ================= 📊 4. 精美看板 =================

# --- 顶部：多维市场晴雨表 (修复图1问题) ---
st.markdown("### 🌏 市场概览")
indices = get_market_dashboard()

if not indices:
    st.warning("📡 数据接口连接中，请稍候...")
else:
    # 动态创建 5 列
    cols = st.columns(5)
    for i, data in enumerate(indices):
        c_cls = "up" if data['c'] > 0 else ("down" if data['c'] < 0 else "flat")
        arrow = "▲" if data['c'] > 0 else ("▼" if data['c'] < 0 else "")
        sign = "+" if data['c'] > 0 else ""
        
        with cols[i]:
            st.markdown(f"""
            <div class="market-card">
                <div class="m-name">{data['n']}</div>
                <div class="m-price {c_cls}">{data['p']:.2f}</div>
                <div class="m-change {c_cls}">
                    {arrow} {data['pct']:.2f}% <br>
                    <span style="opacity:0.7; font-size:10px;">({sign}{data['c']:.2f})</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")

# --- 中部：资产计算 ---
is_weekend = datetime.now().weekday() >= 5
total_asset = sum(float(i['m']) for i in st.session_state.portfolio)
day_profit = 0.0

# 预先计算总收益
valid_portfolio = []
for item in st.session_state.portfolio:
    d = get_fund_details(item['c'])
    if d:
        # 核心逻辑：周末用昨收，平时用实时
        rate = 0.0 if is_weekend else d['real']
        profit = item['m'] * (d['last'] / 100) if is_weekend else item['m'] * (d['real'] / 100)
        day_profit += profit
        valid_portfolio.append({**item, **d, 'profit_money': profit, 'use_rate': rate})

# 渲染黑金总资产卡片
st.markdown(f"""
<div class="hero-card">
    <div style="font-size:14px; opacity:0.8; letter-spacing:1px;">今日{'预估' if not is_weekend else '总结'}收益 (CNY)</div>
    <div style="font-size:48px; font-weight:900; margin:10px 0; color:{'#ff4d4f' if day_profit>=0 else '#27c25c'};">
        {'+' if day_profit>0 else ''}{day_profit:,.2f}
    </div>
    <div style="background:rgba(255,255,255,0.1); display:inline-block; padding:5px 15px; border-radius:15px; font-size:13px;">
        总本金: ¥{total_asset:,.0f}  |  收益率: {(day_profit/total_asset*100) if total_asset>0 else 0:+.2f}%
    </div>
</div>
""", unsafe_allow_html=True)

# --- 底部：持仓列表 (增加涨跌额显示) ---
c1, c2 = st.columns([0.8, 0.2])
c1.subheader("📑 持仓明细")
if c2.button("退出", use_container_width=True):
    st.session_state.user_token = None
    st.rerun()

if not valid_portfolio:
    st.info("💡 暂无持仓，请在左侧侧边栏添加基金。")

for p in valid_portfolio:
    # 颜色逻辑：红涨绿跌
    color_cls = "up" if (p['last'] if is_weekend else p['real']) >= 0 else "down"
    border_color = "#eb4d3d" if (p['last'] if is_weekend else p['real']) >= 0 else "#27c25c"
    
    # 动态状态标签
    status_html = f'<span style="background:#f0f0f0; padding:2px 6px; border-radius:4px; font-size:10px; color:#666;">⏳ 休市(周五结)</span>' if is_weekend else f'<span style="background:#fff0f0; padding:2px 6px; border-radius:4px; font-size:10px; color:#eb4d3d;">🔥 实时预估</span>'

    with st.container():
        # 自定义卡片布局
        col_main, col_del = st.columns([0.9, 0.1])
        with col_main:
            st.markdown(f"""
            <div class="fund-row" style="border-left-color: {border_color};">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-size:16px; font-weight:bold; color:#333;">{p['name']} <span style="font-size:12px; color:#999; font-weight:normal;">{p['c']}</span></div>
                        <div style="margin-top:6px;">
                            {status_html}
                            <span style="margin-left:10px; font-size:13px; color:#666;">本金: ¥{float(p['m']):,.0f}</span>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div class="{color_cls}" style="font-size:24px; font-weight:800;">{p['use_rate']:+.2f}%</div>
                        <div class="{color_cls}" style="font-size:14px; font-weight:600;">¥ {p['profit_money']:+.2f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        if col_del.button("✕", key=f"del_{p['c']}", help="删除此基金"):
            st.session_state.portfolio = [x for x in st.session_state.portfolio if x['c'] != p['c']]
            db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
            db_conn.commit()
            st.rerun()

# ================= 🛠️ 5. 侧边栏 (极简风格) =================
with st.sidebar:
    st.markdown("### ➕ 快速加仓")
    with st.form("add_fund"):
        code = st.text_input("基金代码", placeholder="如: 014143")
        money = st.number_input("持有金额", value=10000.0, step=1000.0)
        if st.form_submit_button("添加 / 更新", use_container_width=True):
            with st.spinner("🔍 正在校验..."): # 这里用自定义提示替代了原来的代码提示
                check = get_fund_details(code)
                if check and check['name'] != "未知基金":
                    # 存在则更新，不存在则追加
                    new_list = [x for x in st.session_state.portfolio if x['c'] != code]
                    new_list.append({"c": code, "m": money})
                    st.session_state.portfolio = new_list
                    db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(new_list)))
                    db_conn.commit()
                    st.success(f"已添加: {check['name']}")
                    st.rerun()
                else:
                    st.error("❌ 代码无效，请检查")

    st.markdown("---")
    st.info(f"当前用户: {st.session_state.user_token}")
