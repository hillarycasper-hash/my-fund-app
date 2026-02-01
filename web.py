import streamlit as st
import requests
import re
import sqlite3
import json
import textwrap
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# ================= 1. 基础配置 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered") # 手机最佳布局
st_autorefresh(interval=60 * 1000, key="global_refresh")

st.markdown("""
    <style>
    .stApp { background-color: #f5f7f9; }
    
    /* 顶部行情栏 (横向排列) */
    .market-row {
        display: flex; gap: 5px; overflow-x: auto; padding-bottom: 5px;
        scrollbar-width: none; /* 隐藏滚动条 */
    }
    .market-card {
        background: #fff; min-width: 85px; padding: 10px 5px; border-radius: 8px;
        text-align: center; border: 1px solid #eee; flex: 1;
    }
    
    /* 核心资产卡 */
    .hero-card { 
        background: linear-gradient(135deg, #2b32b2 0%, #1488cc 100%); 
        color: white; padding: 25px; border-radius: 18px; 
        text-align: center; margin: 15px 0; 
        box-shadow: 0 8px 20px rgba(0,0,0,0.15);
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
    
    /* 按钮样式重置 */
    button[kind="secondary"] { border: 0; background: transparent; padding: 0;}
    </style>
    """, unsafe_allow_html=True)

# ================= 2. 数据库 (默认单用户) =================

def init_db():
    conn = sqlite3.connect('zzl_auto_login.db', check_same_thread=False)
    # 只需要存一个名为 'admin' 的默认用户
    conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
    return conn

db_conn = init_db()

# ================= 3. 数据引擎 (强制周五行情) =================

@st.cache_data(ttl=60, show_spinner=False)
def get_global_indices():
    """获取全球行情，周末强制显示最后收盘价"""
    # 纳斯达克, 恒生, 上证, 离岸人民币
    codes = [
        ('gb_ixic', '纳斯达克', 1, 26), 
        ('rt_hkHSI', '恒生指数', 6, 3),
        ('sh000001', '上证指数', 3, 2),
        ('fx_susdcnh', '美元/CNY', 8, 3) 
    ]
    
    data_list = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])}"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
        lines = r.text.strip().split('\n')
        
        for i, conf in enumerate(codes):
            try:
                line = lines[i]
                parts = line.split('="')[1].split(',')
                
                # 获取价格
                curr_p = float(parts[conf[2]])
                last_p = float(parts[conf[3]])
                
                # 【核心逻辑】：如果当前价是0 (周末常见)，直接用昨收价代替展示
                if curr_p == 0: 
                    curr_p = last_p
                
                # 计算涨跌
                diff = curr_p - last_p
                pct = (diff / last_p) * 100
                
                data_list.append({
                    "name": conf[1],
                    "price": curr_p,
                    "pct": pct
                })
            except:
                # 某种数据挂了，填默认值防止报错
                data_list.append({"name": conf[1], "price": 0.0, "pct": 0.0})
    except:
        return []
        
    return data_list

@st.cache_data(ttl=60, show_spinner=False)
def get_fund_info(code):
    try:
        # 1. 估值接口
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        # 2. 净值接口
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        name = code
        gz_rate = 0.0
        if r_gs.status_code == 200:
            if "name" in r_gs.text: name = re.search(r'name":"(.*?)"', r_gs.text).group(1)
            if "gszzl" in r_gs.text: gz_rate = float(re.search(r'gszzl":"(.*?)"', r_gs.text).group(1))
            
        jz_rate = 0.0
        jz_date = ""
        if r_jz.status_code == 200:
            tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
            if len(tds) > 3:
                jz_date = tds[0].text.strip()
                v = tds[3].text.strip().replace("%","")
                jz_rate = float(v) if v else 0.0
                
        # 决策：是否已更新到今天
        today = datetime.now().strftime("%Y-%m-%d")
        updated = (jz_date == today)
        
        # 最终采用率
        final_rate = jz_rate if updated else gz_rate
        
        return {
            "n": name, 
            "r": final_rate, 
            "tag": "今日净值" if updated else "实时估值",
            "d": jz_date
        }
    except:
        return None

# ================= 4. 自动登录逻辑 =================
# 彻底移除登录界面，默认使用 'admin' 账户
current_user = 'admin'

# 初始化数据
if 'portfolio' not in st.session_state:
    res = db_conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    if res:
        st.session_state.portfolio = json.loads(res[0])
    else:
        st.session_state.portfolio = []
        db_conn.execute('INSERT INTO users VALUES (?,?)', (current_user, json.dumps([])))
        db_conn.commit()

# ================= 5. 界面渲染 =================

# 1. 全球行情 (强制显示)
st.markdown("##### 🌍 全球行情")
indices = get_global_indices()

if not indices:
    st.warning("数据连接中...")
else:
    # 纯 HTML 拼接，无缩进风险
    html_str = '<div class="market-row">'
    for item in indices:
        c_cls = "red" if item['pct'] >= 0 else "green"
        html_str += f"""
        <div class="market-card">
            <div class="gray">{item['name']}</div>
            <div class="{c_cls}" style="font-size:16px;">{item['price']:.2f}</div>
            <div class="{c_cls}" style="font-size:11px;">{item['pct']:+.2f}%</div>
        </div>
        """
    html_str += '</div>'
    st.markdown(html_str, unsafe_allow_html=True)

# 2. 核心计算
total_money = sum(float(x['m']) for x in st.session_state.portfolio)
total_profit = 0.0
valid_data = []

for p in st.session_state.portfolio:
    info = get_fund_info(p['c'])
    if info:
        profit = p['m'] * (info['r'] / 100)
        total_profit += profit
        valid_data.append({**p, **info, 'profit': profit})

# 3. 资产总卡
st.markdown(f"""
<div class="hero-card">
    <div style="font-size:13px; opacity:0.8">今日收益 (CNY)</div>
    <div style="font-size:42px; font-weight:bold; margin:10px 0;">{total_profit:+.2f}</div>
    <div style="font-size:12px; opacity:0.7">
        总本金: {total_money:,.0f} | 收益率: {(total_profit/total_money*100) if total_money>0 else 0:+.2f}%
    </div>
</div>
""", unsafe_allow_html=True)

# 4. 持仓列表 (修正版)
st.markdown("##### 📑 持仓管理")

if not valid_data:
    st.info("👋 暂无数据，请在左侧添加")

for item in valid_data:
    # 样式逻辑
    c_cls = "red" if item['r'] >= 0 else "green"
    bg_p = "#fff5f5" if item['profit'] >= 0 else "#f0fff0"
    
    # 构造卡片 HTML (去除了所有可能引起歧义的缩进)
    card_html = f"""
    <div class="fund-card">
        <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
            <div style="font-weight:bold; font-size:15px; color:#333;">
                {item['n']} <span style="font-size:12px; color:#aaa; font-weight:normal;">{item['c']}</span>
            </div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:flex-end;">
            <div>
                <span class="lbl">{item['tag']}</span>
                <div class="{c_cls}" style="font-size:20px;">{item['r']:+.2f}%</div>
            </div>
            <div style="text-align:right;">
                <span class="lbl">盈亏金额</span>
                <div style="background:{bg_p}; padding:2px 8px; border-radius:4px; font-weight:bold; color:#333; font-size:14px;">
                    ¥ {item['profit']:+.2f}
                </div>
            </div>
        </div>
    </div>
    """
    
    # 渲染：卡片占大头，删除按钮在右侧
    col1, col2 = st.columns([0.88, 0.12])
    with col1:
        st.markdown(card_html, unsafe_allow_html=True)
    with col2:
        st.markdown("<br>", unsafe_allow_html=True) # 占位符，垂直居中
        if st.button("🗑", key=f"d_{item['c']}"):
            new_port = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            st.session_state.portfolio = new_port
            db_conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_port), current_user))
            db_conn.commit()
            st.rerun()

# 5. 侧边栏 (极简添加)
with st.sidebar:
    st.markdown("### ➕ 加仓")
    with st.form("add"):
        code = st.text_input("代码", placeholder="014143")
        money = st.number_input("本金", value=10000.0)
        if st.form_submit_button("确定"):
            check = get_fund_info(code)
            if check:
                p_list = [x for x in st.session_state.portfolio if x['c'] != code]
                p_list.append({"c": code, "m": money})
                st.session_state.portfolio = p_list
                db_conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(p_list), current_user))
                db_conn.commit()
                st.success("OK")
                st.rerun()
            else:
                st.error("代码错误")
