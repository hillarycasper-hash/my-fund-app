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
st_autorefresh(interval=60 * 1000, key="global_refresh")

st.markdown("""
<style>
    .stApp { background-color: #f5f7f9; }
    
    /* 顶部行情 */
    .market-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 5px 2px; scrollbar-width: none; margin-bottom: 10px; }
    .market-card-small { background: white; border: 1px solid #eee; border-radius: 6px; min-width: 80px; text-align: center; padding: 8px 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    
    /* 核心资产卡片 */
    .hero-box { background: linear-gradient(135deg, #2c3e50 0%, #000000 100%); color: white; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    
    /* 基金列表容器 */
    .fund-container { 
        background: white; 
        border-radius: 10px; 
        padding: 12px; 
        border: 1px solid #e0e0e0; 
        margin-bottom: 0px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.08); 
    }
    
    /* 按钮美化 */
    div[data-testid="column"] button { 
        border: 1px solid #ffcccc !important;
        background: white !important;
        color: #ff4b4b !important;
        font-size: 11px !important;
        padding: 0px 8px !important;
        min-height: 0px !important;
        height: 24px !important;
        line-height: 22px !important;
        border-radius: 12px !important;
        float: right;
    }
    div[data-testid="column"] button:hover {
        border-color: #ff4b4b !important;
        background-color: #ff4b4b !important;
        color: white !important;
    }
    
    .t-red { color: #e74c3c; font-weight: bold; }
    .t-green { color: #2ecc71; font-weight: bold; }
    .t-gray { color: #999; font-size: 12px; }
    .t-lbl { font-size: 10px; color: #bbb; }
    .stock-row { display: flex; justify-content: space-between; font-size: 12px; padding: 5px 0; border-bottom: 1px dashed #f5f5f5; align-items: center; }
</style>
""", unsafe_allow_html=True)

# ================= 2. 数据库 =================
# 保持你原来的数据库文件名
conn = sqlite3.connect('zzl_v33_final.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

# ================= 3. 数据获取逻辑 =================

@st.cache_data(ttl=30, show_spinner=False)
def get_indices():
    codes = [('gb_ixic', '纳斯达克', 1, 26), ('rt_hkHSI', '恒生指数', 6, 3), ('sh000001', '上证指数', 3, 2), ('fx_susdcnh', '离岸汇率', 8, 3)]
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
    try:
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        name = code; gz_val = 0.0; gz_time = ""
        
        if r_gs.status_code == 200:
            txt = r_gs.text
            if "name" in txt: name = re.search(r'name":"(.*?)"', txt).group(1)
            if "gszzl" in txt: gz_val = float(re.search(r'gszzl":"(.*?)"', txt).group(1))
            if "gztime" in txt: gz_time = re.search(r'gztime":"(.*?)"', txt).group(1)
            
        jz_val = 0.0; jz_date = ""
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
            used_rate = jz_val; status_txt = f"☕ 休市 ({jz_date})"; is_using_jz = True
        else:
            if jz_date == today_str: used_rate = jz_val; status_txt = "✅ 今日已更新"; is_using_jz = True
            else: used_rate = gz_val; status_txt = f"⚡ 交易中 ({gz_time})"; is_using_jz = False
                
        return {"name": name, "gz": gz_val, "jz": jz_val, "jz_date": jz_date, "used": used_rate, "status": status_txt, "use_jz": is_using_jz}
    except: return None

# 🔥🔥【V37 核心修复】强力穿透逻辑 🔥🔥
@st.cache_data(ttl=300, show_spinner=False)
def get_fund_stocks(fund_code, recursion_depth=0):
    # 限制递归深度，防止死循环
    if recursion_depth > 4: return [] 

    # --- 1. 内部函数：去东财查原始持仓 ---
    def fetch_raw(target):
        stocks = []
        try:
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}
            # 这里的接口比较全，能查到ETF持仓
            url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={target}&deviceid=Wap&plat=Wap&product=EFund&version=6.4.4"
            r = requests.get(url, headers=headers, timeout=2)
            data = r.json()
            if data and 'Datas' in data and data['Datas']:
                for item in data['Datas'][:10]:
                    raw = item['GPDM']
                    # 识别是否为ETF (159/51/56/58开头)
                    is_etf = raw.startswith(('159', '51', '56', '58'))
                    prefix = "sh" if raw.startswith(('6','5')) else ("bj" if raw.startswith(('4','8')) else "sz")
                    stocks.append({"c": f"{prefix}{raw}", "n": item['GPJC'], "raw": raw, "is_etf": is_etf})
        except: pass
        return stocks

    # --- 2. 尝试获取当前代码的持仓 ---
    stock_list = fetch_raw(fund_code)
    
    # --- 3. 策略判断：是否需要穿透？ ---
    # 3.1 检查持仓里有没有 ETF (如果有，直接穿透该ETF)
    etf_target = None
    for s in stock_list:
        if s['is_etf']:
            etf_target = s['raw']
            break 
            
    if etf_target:
        # 🚀 路径A：持仓里有ETF，直接递归查这个ETF
        return get_fund_stocks(etf_target, recursion_depth + 1)
    
    # 3.2 如果没有ETF，且没有股票 (空持仓)，可能是C类或联接基金
    if not stock_list:
        parent_target = None
        
        # 🚀 路径B：查 pingzhongdata 找 fS_code (母基金)
        try:
            r_map = requests.get(f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js", timeout=1.5)
            match = re.search(r'fS_code\s*=\s*["\'](\d+)["\']', r_map.text)
            if match:
                found = match.group(1)
                if found != fund_code:
                    parent_target = found
        except: pass

        if parent_target:
             return get_fund_stocks(parent_target, recursion_depth + 1)

        # 🚀 路径C：如果路径B失败（比如C类没有js文件），尝试“代码减1”找A类
        # 针对 023145 (C) -> 023144 (A) 的情况
        if fund_code.isdigit():
            try:
                code_num = int(fund_code)
                candidate = f"{code_num-1:06d}"
                if candidate != fund_code:
                    # 递归去查兄弟代码
                    return get_fund_stocks(candidate, recursion_depth + 1)
            except: pass

    # --- 4. 如果到了这里，说明找到了真正的股票 ---
    real_stocks = [x for x in stock_list if not x['is_etf']]
    if not real_stocks: return []

    # --- 5. 查新浪实时行情 ---
    try:
        sina_codes = [x['c'] for x in real_stocks]
        url_hq = f"http://hq.sinajs.cn/list={','.join(sina_codes)}"
        r_hq = requests.get(url_hq, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=2)
        lines = r_hq.text.strip().split('\n')
        final_res = []
        code_map = {x['c']: x['n'] for x in real_stocks}
        for line in lines:
            if '="' in line:
                key = line.split('="')[0].split('hq_str_')[-1]
                val = line.split('="')[1]
                parts = val.split(',')
                if len(parts) > 3:
                    curr = float(parts[3])
                    last = float(parts[2])
                    if curr == 0: curr = last
                    pct = (curr - last) / last * 100 if last > 0 else 0.0
                    name = parts[0] if parts[0] else code_map.get(key, "--")
                    final_res.append({"n": name, "v": curr, "p": pct})
        return final_res
    except: return []

# ================= 4. 页面渲染 =================

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

if 'portfolio' not in st.session_state:
    row = conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    st.session_state.portfolio = json.loads(row[0]) if row else []

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

bg_cls = "#ff4b4b" if total_profit >= 0 else "#2ecc71"
st.markdown(f"""
<div class="hero-box" style="background:{bg_cls}">
    <div style="opacity:0.9; font-size:14px;">总盈亏 (CNY)</div>
    <div style="font-size:40px; font-weight:bold; margin:5px 0;">{total_profit:+.2f}</div>
    <div style="font-size:12px; opacity:0.8;">持仓本金: {total_money:,.0f}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("##### 📑 基金明细")
if not final_list:
    st.info("请在左侧添加基金")

for item in final_list:
    c1, c2 = st.columns([0.8, 0.2])
    with c1:
        st.markdown(f"**{item['name']}** <span style='color:#ccc; font-size:12px'>{item['c']}</span>", unsafe_allow_html=True)
    with c2:
        if st.button("删除", key=f"del_{item['c']}"):
            new_p = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            st.session_state.portfolio = new_p
            conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_p), current_user))
            conn.commit()
            st.rerun()

    color_gz = "#999"; color_jz = "#999"; wt_gz = "normal"; wt_jz = "normal"
    if item['use_jz']:
        color_jz = "#e74c3c" if item['jz'] >= 0 else "#2ecc71"; wt_jz = "bold"
    else:
        color_gz = "#e74c3c" if item['gz'] >= 0 else "#2ecc71"; wt_gz = "bold"
    
    profit_color = "#e74c3c" if item['profit_money'] >= 0 else "#2ecc71"

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
    
    with st.expander("📊 前十持仓 (穿透版)"):
        stocks = get_fund_stocks(item['c'])
        if stocks:
            for s in stocks:
                s_color = "t-red" if s['p'] >= 0 else "t-green"
                row_html = f"""<div class="stock-row"><span style="flex:2; color:#333; font-weight:500;">{s['n']}</span><span style="flex:1; text-align:right; font-family:monospace;" class="{s_color}">{s['v']:.2f}</span><span style="flex:1; text-align:right; font-family:monospace;" class="{s_color}">{s['p']:+.2f}%</span></div>"""
                st.markdown(row_html, unsafe_allow_html=True)
        else:
            st.caption("暂无数据 (可能是新发基金或数据未披露)")
    
    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("➕ 添加")
    with st.form("add"):
        code = st.text_input("代码", placeholder="例如 014143")
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
            else: st.error("代码错误")
