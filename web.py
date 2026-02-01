import streamlit as st
import requests
import re
import sqlite3
import json
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# ================= 1. 基础配置 (完全保持 V25) =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered")
st_autorefresh(interval=60 * 1000, key="global_refresh")

# 强制 CSS：修复按钮对齐，防止代码块显示
st.markdown("""
<style>
    .stApp { background-color: #f5f7f9; }
    
    /* 顶部行情栏 */
    .market-scroll {
        display: flex; gap: 8px; overflow-x: auto; padding: 5px 2px;
        scrollbar-width: none; margin-bottom: 10px;
    }
    .market-card-small {
        background: white; border: 1px solid #eee; border-radius: 6px;
        min-width: 80px; text-align: center; padding: 8px 4px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    
    /* 核心资产卡 */
    .hero-box {
        background: linear-gradient(135deg, #2c3e50 0%, #000000 100%);
        color: white; border-radius: 12px; padding: 20px;
        text-align: center; margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    
    /* 基金卡片容器 */
    .fund-container {
        background: white; border-radius: 8px; padding: 12px;
        border: 1px solid #e0e0e0; margin-bottom: 5px; /* 稍微减小底部间距，给折叠栏腾位置 */
    }
    
    /* 删除按钮样式 */
    div[data-testid="column"] button {
        padding: 0px 8px !important;
        min-height: 0px !important;
        height: 30px !important;
        line-height: 1 !important;
        border: 1px solid #f0f0f0;
    }
    
    /* 字体颜色 */
    .t-red { color: #e74c3c; font-weight: bold; }
    .t-green { color: #2ecc71; font-weight: bold; }
    .t-gray { color: #999; font-size: 12px; }
    .t-lbl { font-size: 10px; color: #bbb; }
    
    /* 股票列表样式 */
    .stock-row {
        display: flex; justify-content: space-between; font-size: 12px; 
        padding: 4px 0; border-bottom: 1px dashed #f0f0f0;
    }
</style>
""", unsafe_allow_html=True)

# ================= 2. 数据库 (保持不变) =================
conn = sqlite3.connect('zzl_v26_stocks.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

# ================= 3. 数据获取 (新增重仓股逻辑) =================

@st.cache_data(ttl=30, show_spinner=False)
def get_indices():
    """获取全球行情"""
    codes = [
        ('gb_ixic', '纳斯达克', 1, 26),
        ('rt_hkHSI', '恒生指数', 6, 3),
        ('sh000001', '上证指数', 3, 2),
        ('fx_susdcnh', '离岸汇率', 8, 3)
    ]
    res = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])}"
        r = requests.get(url, headers=headers, timeout=2)
        lines = r.text.strip().split('\n')
        for i, cfg in enumerate(codes):
            try:
                parts = lines[i].split('="')[1].split(',')
                curr = float(parts[cfg[2]])
                last = float(parts[cfg[3]])
                if curr == 0: curr = last
                res.append({"n": cfg[1], "v": curr, "p": (curr - last) / last * 100})
            except:
                res.append({"n": cfg[1], "v": 0.0, "p": 0.0})
    except:
        return []
    return res

@st.cache_data(ttl=60, show_spinner=False)
def get_details(code):
    """获取基金详情(保持 V25 逻辑)"""
    try:
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        name = code
        gz_val = 0.0
        gz_time = ""
        
        if r_gs.status_code == 200:
            txt = r_gs.text
            if "name" in txt: name = re.search(r'name":"(.*?)"', txt).group(1)
            if "gszzl" in txt: gz_val = float(re.search(r'gszzl":"(.*?)"', txt).group(1))
            if "gztime" in txt: gz_time = re.search(r'gztime":"(.*?)"', txt).group(1)
            
        jz_val = 0.0
        jz_date = ""
        if r_jz.status_code == 200:
            tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
            if len(tds) > 3:
                jz_date = tds[0].text.strip()
                v_str = tds[3].text.strip().replace("%","")
                jz_val = float(v_str) if v_str else 0.0
                
        now = datetime.now()
        is_weekend = now.weekday() >= 5
        today_str = now.strftime("%Y-%m-%d")
        
        if is_weekend:
            used_rate = jz_val
            status_txt = f"☕ 休市 (已更新至{jz_date})"
            is_using_jz = True
        else:
            if jz_date == today_str:
                used_rate = jz_val
                status_txt = "✅ 今日净值已出"
                is_using_jz = True
            else:
                used_rate = gz_val
                status_txt = f"⚡ 交易中 (估值 {gz_time})"
                is_using_jz = False
                
        return {
            "name": name, "gz": gz_val, "jz": jz_val, "jz_date": jz_date,
            "used": used_rate, "status": status_txt, "use_jz": is_using_jz
        }
    except:
        return None

# 【新增】获取重仓股详情
@st.cache_data(ttl=300, show_spinner=False)
def get_fund_stocks(fund_code):
    """获取基金持仓的前10大股票实时行情"""
    try:
        # 1. 从天天基金获取持仓代码列表
        # pingzhongdata 包含季度更新的持仓 stockCodes
        url_codes = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        r = requests.get(url_codes, timeout=2)
        
        # 提取股票代码列表: var stockCodes=["600519","000858"...]
        match = re.search(r'stockCodes=\["(.*?)"\]', r.text)
        if not match: return []
        
        raw_codes = match.group(1).split('","')
        top10_codes = raw_codes[:10] # 只取前10
        
        # 2. 构造新浪行情 API 代码 (加 sh/sz 前缀)
        sina_codes = []
        for c in top10_codes:
            prefix = "sh" if c.startswith('6') else "sz"
            if c.startswith(('4','8')): prefix = "bj" # 北交所简单处理
            sina_codes.append(f"{prefix}{c}")
            
        # 3. 批量获取实时行情
        url_hq = f"http://hq.sinajs.cn/list={','.join(sina_codes)}"
        headers = {'Referer': 'https://finance.sina.com.cn'}
        r_hq = requests.get(url_hq, headers=headers, timeout=2)
        lines = r_hq.text.strip().split('\n')
        
        stock_list = []
        for line in lines:
            if '="' in line:
                parts = line.split('="')[1].split(',')
                if len(parts) > 3:
                    name = parts[0]
                    curr = float(parts[3])
                    last = float(parts[2])
                    
                    # 停牌或集合竞价修正
                    if curr == 0: curr = last
                    
                    pct = 0.0
                    if last > 0:
                        pct = (curr - last) / last * 100
                    
                    stock_list.append({"n": name, "p": pct, "v": curr})
                    
        return stock_list
    except:
        return []

# ================= 4. 页面渲染 =================

# 1. 顶部大盘
st.markdown("##### 🌍 全球行情")
idx_data = get_indices()
if idx_data:
    h = '<div class="market-scroll">'
    for d in idx_data:
        c = "t-red" if d['p'] >= 0 else "t-green"
        h += f'<div class="market-card-small"><div class="t-gray">{d["n"]}</div><div class="{c}">{d["v"]:.2f}</div><div class="{c}" style="font-size:10px;">{d["p"]:+.2f}%</div></div>'
    h += '</div>'
    st.markdown(h, unsafe_allow_html=True)
else:
    st.caption("行情加载中...")

# 2. 读取数据
if 'portfolio' not in st.session_state:
    row = conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    st.session_state.portfolio = json.loads(row[0]) if row else []

# 3. 计算逻辑
total_money = 0.0
total_profit = 0.0
final_list = []

for p in st.session_state.portfolio:
    info = get_details(p['c'])
    if info:
        total_money += p['m']
        profit = p['m'] * (info['used'] / 100)
        total_profit += profit
        final_list.append({**p, **info, 'profit_money': profit})

# 4. 核心资产卡
bg_cls = "#ff4b4b" if total_profit >= 0 else "#2ecc71"
st.markdown(f"""
<div class="hero-box" style="background:{bg_cls}">
    <div style="opacity:0.9; font-size:14px;">总盈亏 (CNY)</div>
    <div style="font-size:40px; font-weight:bold; margin:5px 0;">{total_profit:+.2f}</div>
    <div style="font-size:12px; opacity:0.8;">持仓本金: {total_money:,.0f}</div>
</div>
""", unsafe_allow_html=True)

# 5. 基金列表 (V25布局 + 重仓股扩展)
st.markdown("##### 📑 基金明细")

if not final_list:
    st.info("请在左侧添加基金")

for item in final_list:
    # 标题行
    c1, c2 = st.columns([0.85, 0.15])
    with c1:
        st.markdown(f"**{item['name']}** <span style='color:#ccc; font-size:12px'>{item['c']}</span>", unsafe_allow_html=True)
    with c2:
        if st.button("🗑", key=f"del_{item['c']}"):
            new_p = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            st.session_state.portfolio = new_p
            conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_p), current_user))
            conn.commit()
            st.rerun()

    # 卡片颜色逻辑
    color_gz = "#999"
    color_jz = "#999"
    wt_gz = "normal"
    wt_jz = "normal"
    
    if item['use_jz']:
        color_jz = "#e74c3c" if item['jz'] >= 0 else "#2ecc71"
        wt_jz = "bold"
    else:
        color_gz = "#e74c3c" if item['gz'] >= 0 else "#2ecc71"
        wt_gz = "bold"
    
    profit_color = "#e74c3c" if item['profit_money'] >= 0 else "#2ecc71"

    # 卡片 HTML
    card = f"""
    <div class="fund-container">
        <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px dashed #eee; padding-bottom:5px;">
            <div style="font-size:12px; color:#666;">{item['status']}</div>
            <div style="font-size:14px; font-weight:bold; color:{profit_color}">¥ {item['profit_money']:+.2f}</div>
        </div>
        <div style="display:flex; justify-content:space-between; text-align:center;">
            <div style="flex:1;">
                <div class="t-lbl">实时估值</div>
                <div style="color:{color_gz}; font-weight:{wt_gz}; font-size:16px;">{item['gz']:+.2f}%</div>
            </div>
            <div style="width:1px; background:#eee;"></div>
            <div style="flex:1;">
                <div class="t-lbl">官方净值 ({item['jz_date'][5:]})</div>
                <div style="color:{color_jz}; font-weight:{wt_jz}; font-size:16px;">{item['jz']:+.2f}%</div>
            </div>
        </div>
    </div>
    """
    st.markdown(card, unsafe_allow_html=True)
    
    # 【新增】重仓股折叠区
    with st.expander("📊 查看前十重仓股 (实时涨跌)"):
        stocks = get_fund_stocks(item['c'])
        if stocks:
            for s in stocks:
                s_color = "t-red" if s['p'] >= 0 else "t-green"
                # 每一行股票的HTML
                row_html = f"""
                <div class="stock-row">
                    <span style="flex:2; color:#333;">{s['n']}</span>
                    <span style="flex:1; text-align:right;" class="{s_color}">{s['v']:.2f}</span>
                    <span style="flex:1; text-align:right;" class="{s_color}">{s['p']:+.2f}%</span>
                </div>
                """
                st.markdown(row_html, unsafe_allow_html=True)
        else:
            st.caption("暂无持仓数据或非股票型基金")

# 6. 侧边栏
with st.sidebar:
    st.header("➕ 添加")
    with st.form("add"):
        code = st.text_input("代码", placeholder="例如 000001")
        money = st.number_input("本金", value=10000.0)
        if st.form_submit_button("确认"):
            res = get_details(code)
            if res:
                ls = [x for x in st.session_state.portfolio if x['c'] != code]
                ls.append({"c": code, "m": money})
                st.session_state.portfolio = ls
                conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(ls), current_user))
                conn.commit()
                st.success(f"已添加 {res['name']}")
                st.rerun()
            else:
                st.error("代码错误")
