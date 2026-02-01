import streamlit as st
import requests
import re
import sqlite3
import json
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# ================= 1. 基础配置 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered")
# 1分钟自动刷新，保持连接
st_autorefresh(interval=60 * 1000, key="global_refresh")

st.markdown("""
    <style>
    .stApp { background-color: #f5f7f9; }
    
    /* 顶部行情栏 (横向滚动) */
    .market-row {
        display: flex; gap: 8px; overflow-x: auto; padding: 5px 2px;
        scrollbar-width: none;
    }
    .market-row::-webkit-scrollbar { display: none; }
    
    .market-card {
        background: #fff; min-width: 90px; padding: 10px 5px; border-radius: 8px;
        text-align: center; border: 1px solid #eee; flex-shrink: 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    /* 核心资产卡 */
    .hero-card { 
        background: linear-gradient(135deg, #FF4B2B 0%, #FF416C 100%); 
        color: white; padding: 25px; border-radius: 18px; 
        text-align: center; margin: 15px 0; 
        box-shadow: 0 8px 20px rgba(255, 75, 43, 0.3);
    }
    .hero-green {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%) !important;
        box-shadow: 0 8px 20px rgba(56, 239, 125, 0.3) !important;
    }
    
    /* 基金列表卡片 */
    .fund-card {
        background: white; border-radius: 12px; padding: 15px; margin-bottom: 10px;
        border: 1px solid #f0f0f0; box-shadow: 0 2px 6px rgba(0,0,0,0.02);
    }
    
    /* 颜色定义 */
    .red { color: #e74c3c; font-weight: 800; }
    .green { color: #2ecc71; font-weight: 800; }
    .gray { color: #888; font-size: 11px; }
    .lbl { font-size: 10px; color: #bbb; display: block; margin-bottom: 2px;}
    
    /* 按钮清理 */
    button[kind="secondary"] { border: 0; background: transparent; padding: 0;}
    </style>
    """, unsafe_allow_html=True)

# ================= 2. 数据库 (单机版) =================

def init_db():
    conn = sqlite3.connect('zzl_v24_fixed.db', check_same_thread=False)
    conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
    return conn

db_conn = init_db()
current_user = 'admin' # 强制单用户，无需登录

# ================= 3. 数据引擎 (逻辑死板执行) =================

@st.cache_data(ttl=30, show_spinner=False)
def get_global_indices():
    """获取全球行情，增加Headers防止加载失败"""
    # 纳斯达克, 恒生, 上证, 离岸人民币, 黄金
    codes = [
        ('gb_ixic', '纳斯达克', 1, 26), 
        ('rt_hkHSI', '恒生指数', 6, 3),
        ('sh000001', '上证指数', 3, 2),
        ('fx_susdcnh', '离岸汇率', 8, 3)
    ]
    
    data_list = []
    try:
        # 【关键修复】加上 Referer，防止接口拒绝
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://finance.sina.com.cn/'
        }
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])}"
        r = requests.get(url, headers=headers, timeout=2)
        lines = r.text.strip().split('\n')
        
        for i, conf in enumerate(codes):
            try:
                line = lines[i]
                parts = line.split('="')[1].split(',')
                
                curr_p = float(parts[conf[2]])
                last_p = float(parts[conf[3]])
                
                # 休市/周末数据修正：如果当前价为0，强制用昨收价
                if curr_p == 0: curr_p = last_p
                
                diff = curr_p - last_p
                pct = (diff / last_p) * 100
                
                data_list.append({"name": conf[1], "price": curr_p, "pct": pct})
            except:
                # 单个失败，填兜底数据，保证不转圈
                data_list.append({"name": conf[1], "price": 0.0, "pct": 0.0})
    except:
        # 全部失败
        return []
        
    return data_list

@st.cache_data(ttl=60, show_spinner=False)
def get_fund_logic(code):
    """
    终极逻辑：
    1. 获取实时估值 (r_gs)
    2. 获取官方净值 (r_jz) 和 日期 (jz_date)
    3. 判断：
       - 如果是周末(周六/日): 强制使用 官方净值 (r_jz)。
       - 如果是工作日:
         - 如果 jz_date == 今天: 使用 官方净值 (r_jz)。
         - 否则: 使用 实时估值 (r_gs)。
    """
    try:
        # A. 抓取数据
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        name = code
        gz_rate = 0.0 # 实时估值涨幅
        
        # 解析估值
        if r_gs.status_code == 200:
            if "name" in r_gs.text: name = re.search(r'name":"(.*?)"', r_gs.text).group(1)
            if "gszzl" in r_gs.text: gz_rate = float(re.search(r'gszzl":"(.*?)"', r_gs.text).group(1))
            
        # 解析净值 (官方)
        jz_rate = 0.0
        jz_date = "1970-01-01"
        if r_jz.status_code == 200:
            tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
            if len(tds) > 3:
                jz_date = tds[0].text.strip() # 格式: 2026-02-01
                v_str = tds[3].text.strip().replace("%","")
                jz_rate = float(v_str) if v_str else 0.0
        
        # B. 核心判断逻辑 (死命令)
        now = datetime.now()
        is_weekend = now.weekday() >= 5 # 5=Sat, 6=Sun
        today_str = now.strftime("%Y-%m-%d")
        
        final_rate = 0.0
        status_tag = ""
        
        if is_weekend:
            # 周末 -> 强制用官方净值 (通常是周五的)
            final_rate = jz_rate
            status_tag = f"官方净值 ({jz_date[5:]})"
        else:
            # 交易日
            if jz_date == today_str:
                # 官方已更新 -> 用官方
                final_rate = jz_rate
                status_tag = "✅ 官方已更新"
            else:
                # 官方未更新 -> 用估值
                final_rate = gz_rate
                status_tag = "⚡ 实时估值"
        
        return {
            "n": name,
            "r": final_rate, # 这是最终用来计算钱的汇率
            "tag": status_tag
        }
    except:
        return None

# ================= 4. 初始化用户数据 =================
if 'portfolio' not in st.session_state:
    res = db_conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    st.session_state.portfolio = json.loads(res[0]) if res else []

# ================= 5. 页面渲染 =================

# --- A. 全球行情 (强制显示) ---
st.markdown("##### 🌍 全球行情")
indices = get_global_indices()

if indices:
    html_str = '<div class="market-row">'
    for item in indices:
        c_cls = "red" if item['pct'] >= 0 else "green"
        # 纯 HTML 渲染，防止格式问题
        html_str += f"""
        <div class="market-card">
            <div class="gray">{item['name']}</div>
            <div class="{c_cls}" style="font-size:16px;">{item['price']:.2f}</div>
            <div class="{c_cls}" style="font-size:11px;">{item['pct']:+.2f}%</div>
        </div>
        """
    html_str += '</div>'
    st.markdown(html_str, unsafe_allow_html=True)
else:
    # 兜底显示，不留白
    st.info("数据同步中... (请检查网络)")

# --- B. 计算持仓 (严格对齐总数) ---
total_principal = sum(float(x['m']) for x in st.session_state.portfolio)
total_profit = 0.0
display_items = []

for p in st.session_state.portfolio:
    data = get_fund_logic(p['c'])
    if data:
        # 盈亏 = 本金 * (最终选定的汇率 / 100)
        # 这里的 data['r'] 已经经过了上面严格的逻辑筛选
        item_profit = p['m'] * (data['r'] / 100)
        total_profit += item_profit
        display_items.append({**p, **data, 'profit_money': item_profit})

# --- C. 资产总卡 (Hero Card) ---
hero_cls = "hero-card" if total_profit >= 0 else "hero-card hero-green" # 跌了变绿卡

st.markdown(f"""
<div class="{hero_cls}">
    <div style="font-size:13px; opacity:0.9">总盈亏 (CNY)</div>
    <div style="font-size:42px; font-weight:bold; margin:5px 0;">{total_profit:+.2f}</div>
    <div style="font-size:12px; opacity:0.8">
        总本金: {total_principal:,.0f} | 综合收益率: {(total_profit/total_principal*100) if total_principal>0 else 0:+.2f}%
    </div>
</div>
""", unsafe_allow_html=True)

# --- D. 持仓列表 ---
st.markdown("##### 📑 持仓明细")

if not display_items:
    st.info("👋 暂无数据，请在侧边栏添加")

for item in display_items:
    c_cls = "red" if item['r'] >= 0 else "green"
    bg_p = "#fff5f5" if item['profit_money'] >= 0 else "#f0fff0"
    
    # 卡片 HTML (无缩进)
    card_html = f"""
    <div class="fund-card">
        <div style="font-weight:bold; font-size:15px; color:#333; margin-bottom:8px;">
            {item['n']} <span style="font-size:12px; color:#aaa; font-weight:normal;">{item['c']}</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:flex-end;">
            <div>
                <span class="lbl">{item['tag']}</span>
                <div class="{c_cls}" style="font-size:20px;">{item['r']:+.2f}%</div>
            </div>
            <div style="text-align:right;">
                <span class="lbl">盈亏金额</span>
                <div style="background:{bg_p}; padding:2px 8px; border-radius:4px; font-weight:bold; color:#333; font-size:14px;">
                    ¥ {item['profit_money']:+.2f}
                </div>
            </div>
        </div>
    </div>
    """
    
    # 布局：删除按钮在名字旁边
    col1, col2 = st.columns([0.88, 0.12])
    with col1:
        st.markdown(card_html, unsafe_allow_html=True)
    with col2:
        st.markdown("<br>", unsafe_allow_html=True) # 垂直占位
        if st.button("🗑", key=f"del_{item['c']}"):
            new_port = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            st.session_state.portfolio = new_port
            db_conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_port), current_user))
            db_conn.commit()
            st.rerun()

# --- E. 侧边栏 ---
with st.sidebar:
    st.markdown("### ➕ 加仓")
    with st.form("add"):
        code = st.text_input("代码", placeholder="014143")
        money = st.number_input("本金", value=10000.0)
        if st.form_submit_button("确定"):
            check = get_fund_logic(code) # 复用逻辑检查代码有效性
            if check:
                p_list = [x for x in st.session_state.portfolio if x['c'] != code]
                p_list.append({"c": code, "m": money})
                st.session_state.portfolio = p_list
                db_conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(p_list), current_user))
                db_conn.commit()
                st.success("OK")
                st.rerun()
            else:
                st.error("代码无效")
