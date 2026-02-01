import streamlit as st
import requests
import re
import sqlite3
import json
import textwrap
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# ================= 1. 核心配置 =================
# 【修复点】：layout只能是 "centered" 或 "wide"，之前写 "mobile" 导致了崩溃
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered") 
st_autorefresh(interval=60 * 1000, key="global_refresh")

# CSS 样式：优化了删除按钮，使其看起来像跟在名字后面
st.markdown("""
    <style>
    .stApp { background-color: #f5f7f9; }
    
    /* 大盘卡片 */
    .market-box {
        background: #fff; border-radius: 8px; padding: 10px; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 8px;
    }
    
    /* 核心收益卡 */
    .hero-card { 
        background: linear-gradient(135deg, #1e1e2f 0%, #252540 100%); 
        color: white; padding: 20px; border-radius: 16px; 
        text-align: center; margin-bottom: 15px; 
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
    
    /* 基金卡片 */
    .fund-card {
        background: white; border-radius: 12px; padding: 12px;
        border: 1px solid #eee; margin-top: -10px; /* 紧贴标题 */
    }
    
    /* 颜色类 */
    .red { color: #e74c3c; font-weight: bold; }
    .green { color: #2ecc71; font-weight: bold; }
    .gray { color: #999; }
    
    /* 调整自带按钮样式，使其更小 */
    div.stButton > button {
        padding: 0.2rem 0.5rem; font-size: 0.8rem; border: none; background: transparent; color: #999;
    }
    div.stButton > button:hover {
        color: #e74c3c; background: #fee;
    }
    </style>
    """, unsafe_allow_html=True)

# ================= 2. 数据引擎 (增加休市回退逻辑) =================

def init_db():
    conn = sqlite3.connect('zzl_final_v21.db', check_same_thread=False)
    conn.execute('CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, portfolio TEXT)')
    return conn

db_conn = init_db()

@st.cache_data(ttl=30, show_spinner=False)
def get_market_data():
    """获取大盘数据，解决休市显示0的问题"""
    # 格式：(代码, 名称, 索引位:当前价, 索引位:昨收)
    # 离岸人民币(fx_susdcnh) 结构特殊，单独处理
    codes = [
        ('sh000001', '上证指数', 3, 2),
        ('sz399006', '创业板指', 3, 2),
        ('gb_ixic',  '纳斯达克', 1, 26), 
        ('rt_hkHSI', '恒生指数', 6, 3)
    ]
    
    res = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])},fx_susdcnh"
        r = requests.get(url, headers=headers, timeout=2)
        lines = r.text.strip().split('\n')
        
        # 1. 处理常规指数
        for i, code_info in enumerate(codes):
            line = lines[i]
            parts = line.split('="')[1].split(',')
            if len(parts) < 5: continue
            
            c_idx, l_idx = code_info[2], code_info[3]
            current_price = float(parts[c_idx])
            last_close = float(parts[l_idx])
            
            # 【核心修复】：如果当前价为0（休市/集合竞价），强制使用昨收价，显示涨跌为0
            if current_price == 0:
                current_price = last_close
            
            change_pct = ((current_price - last_close) / last_close) * 100
            res.append({
                "name": code_info[1],
                "price": current_price,
                "pct": change_pct
            })
            
        # 2. 单独处理汇率 (fx_susdcnh) - 它的位置在最后
        line_fx = lines[-1]
        parts_fx = line_fx.split('="')[1].split(',')
        cur_fx = float(parts_fx[8])
        last_fx = float(parts_fx[3])
        # 汇率一般不会为0，但也做个防守
        if cur_fx == 0: cur_fx = last_fx
        
        res.append({
            "name": "离岸人民币",
            "price": cur_fx,
            "pct": ((cur_fx - last_fx) / last_fx) * 100
        })
        
        return res
    except:
        return []

@st.cache_data(ttl=60, show_spinner=False)
def get_fund_realtime(code):
    """获取基金数据：优先判断是否已更新净值"""
    try:
        # 1. 估值接口
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        # 2. 净值接口
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        # 解析名称
        name = code
        if r_gs.status_code == 200 and "name" in r_gs.text:
            name = re.search(r'name":"(.*?)"', r_gs.text).group(1)
        
        # 解析估值
        gz_rate = 0.0
        if r_gs.status_code == 200 and "gszzl" in r_gs.text:
            gz_rate = float(re.search(r'gszzl":"(.*?)"', r_gs.text).group(1))

        # 解析净值
        jz_rate = 0.0
        jz_date = ""
        if r_jz.status_code == 200:
            tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
            if len(tds) > 3:
                jz_date = tds[0].text.strip() # 格式 2023-10-27
                val_str = tds[3].text.strip().replace("%","")
                jz_rate = float(val_str) if val_str else 0.0

        # 【核心逻辑】：判断今天是否已经更新了净值
        today_str = datetime.now().strftime('%Y-%m-%d')
        is_updated = (jz_date == today_str)
        
        # 最终使用的涨跌幅：如果已更新净值，用净值；否则用估值
        final_rate = jz_rate if is_updated else gz_rate
        used_type = "净值更新" if is_updated else "实时估值"
        
        return {
            "name": name,
            "rate": final_rate, # 最终涨跌幅
            "gz": gz_rate,      # 仅作展示用
            "jz": jz_rate,      # 仅作展示用
            "type": used_type,  # 状态标记
            "date": jz_date
        }
    except:
        return None

# ================= 3. 页面逻辑 =================

if 'user_token' not in st.session_state: st.session_state.user_token = None
if 'portfolio' not in st.session_state: st.session_state.portfolio = []

# --- 登录页 ---
if not st.session_state.user_token:
    st.markdown("<br><h2 style='text-align:center;'>🚀 涨涨乐 Pro</h2>", unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    tk = c1.text_input("识别码", label_visibility="collapsed", placeholder="输入识别码")
    if c2.button("GO", type="primary", use_container_width=True):
        if tk:
            res = db_conn.execute('SELECT portfolio FROM users WHERE token=?', (tk,)).fetchone()
            st.session_state.user_token = tk
            st.session_state.portfolio = json.loads(res[0]) if res else []
            st.rerun()
    st.stop()

# --- 顶部大盘 (修复一直转圈问题) ---
indices = get_market_data()
if indices:
    cols = st.columns(len(indices))
    for i, data in enumerate(indices):
        c_cls = "red" if data['pct'] >= 0 else "green"
        with cols[i]:
            # 使用 textwrap 确保无缩进
            html = f"""
            <div class="market-box">
                <div class="gray" style="font-size:10px;">{data['name']}</div>
                <div class="{c_cls}" style="font-size:14px;">{data['price']:.2f}</div>
                <div class="{c_cls}" style="font-size:10px;">{data['pct']:+.2f}%</div>
            </div>
            """
            st.markdown(textwrap.dedent(html), unsafe_allow_html=True)
else:
    st.info("🍵 正在休市或数据同步中 (显示上个交易日数据)")

# --- 计算总资产 ---
total_asset = sum(float(x['m']) for x in st.session_state.portfolio)
total_profit = 0.0
display_list = []

for p in st.session_state.portfolio:
    info = get_fund_realtime(p['c'])
    if info:
        # 按照“最终收益率”计算收益金额
        profit_amt = p['m'] * (info['rate'] / 100)
        total_profit += profit_amt
        display_list.append({**p, **info, 'profit_amt': profit_amt})

# --- 黑金收益卡 ---
bg_color = "#ff4b4b" if total_profit >= 0 else "#2ecc71"
st.markdown(f"""
<div class="hero-card">
    <div style="font-size:14px; opacity:0.8;">今日总盈亏 (CNY)</div>
    <div style="font-size:36px; font-weight:bold; margin:5px 0; color:{'#ffaaaa' if total_profit>=0 else '#aaffaa'};">
        {total_profit:+.2f}
    </div>
    <div style="font-size:12px; opacity:0.6;">
        总本金: {total_asset:,.0f} | 收益率: {(total_profit/total_asset*100) if total_asset>0 else 0:+.2f}%
    </div>
</div>
""", unsafe_allow_html=True)

# --- 持仓列表 (修复删除按钮位置) ---
st.markdown("### 📑 持仓明细")

if not display_list:
    st.info("👈 侧边栏添加你的第一个基金")

for item in display_list:
    # 1. 标题行：左边名字，右边删除按钮 (紧挨着)
    # 使用 columns 来布局按钮
    col_title, col_del = st.columns([0.85, 0.15])
    
    with col_title:
        st.markdown(f"**{item['name']}** <span style='color:#ccc; font-size:12px'>{item['c']}</span>", unsafe_allow_html=True)
    
    with col_del:
        # 按钮在这里，紧跟名字行的右侧
        if st.button("🗑", key=f"del_{item['c']}"):
            st.session_state.portfolio = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(st.session_state.portfolio)))
            db_conn.commit()
            st.rerun()

    # 2. 数据卡片 (纯展示，无交互)
    color_cls = "red" if item['rate'] >= 0 else "green"
    bg_light = "#fff5f5" if item['rate'] >= 0 else "#f0fff4"
    
    card_html = f"""
    <div class="fund-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            
            <div style="text-align:left;">
                <div style="font-size:10px; color:#999; margin-bottom:2px;">{item['type']}</div>
                <div class="{color_cls}" style="font-size:20px; font-weight:900;">{item['rate']:+.2f}%</div>
            </div>
            
            <div style="text-align:right;">
                <div style="font-size:10px; color:#999; margin-bottom:2px;">盈亏金额</div>
                <div style="background:{bg_light}; color:{color_cls}; padding:4px 8px; border-radius:4px; font-weight:bold; font-size:14px;">
                    ¥ {item['profit_amt']:+.2f}
                </div>
            </div>
            
        </div>
        <div style="border-top:1px dashed #eee; margin-top:8px; padding-top:6px; display:flex; justify-content:space-between; font-size:11px; color:#bbb;">
            <span>持仓: ¥{item['m']:.0f}</span>
            <span>更新: {item['date']}</span>
        </div>
    </div>
    <div style="height:10px;"></div> """
    st.markdown(textwrap.dedent(card_html), unsafe_allow_html=True)

# --- 侧边栏 ---
with st.sidebar:
    st.caption(f"当前用户: {st.session_state.user_token}")
    with st.form("add_fund"):
        c = st.text_input("基金代码", placeholder="例如 000001")
        m = st.number_input("持有金额", value=10000.0, step=1000.0)
        if st.form_submit_button("添加 / 更新"):
            # 简单验证一下代码是否有效
            if get_fund_realtime(c):
                # 存在则更新，不存在则追加
                new_p = [x for x in st.session_state.portfolio if x['c'] != c]
                new_p.append({"c": c, "m": m})
                st.session_state.portfolio = new_p
                db_conn.execute('INSERT OR REPLACE INTO users VALUES (?,?)', (st.session_state.user_token, json.dumps(new_p)))
                db_conn.commit()
                st.success("成功")
                st.rerun()
            else:
                st.error("代码无效或网络超时")
    
    if st.button("退出登录"):
        st.session_state.user_token = None
        st.rerun()
