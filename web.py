import streamlit as st
import requests
import re
import sqlite3
import json
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# ================= 1. 基础配置 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered")
st_autorefresh(interval=30 * 1000, key="global_refresh") # 30秒刷新

st.markdown("""
<style>
    .stApp { background-color: #f5f7f9; }
    .market-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 5px 2px; scrollbar-width: none; margin-bottom: 10px; }
    .market-card-small { background: white; border: 1px solid #eee; border-radius: 6px; min-width: 80px; text-align: center; padding: 8px 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .hero-box { background: linear-gradient(135deg, #2c3e50 0%, #000000 100%); color: white; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    .fund-container { background: white; border-radius: 10px; padding: 12px; border: 1px solid #e0e0e0; margin-bottom: 0px; box-shadow: 0 2px 5px rgba(0,0,0,0.08); }
    div[data-testid="column"] button { border: 1px solid #ffcccc !important; background: white !important; color: #ff4b4b !important; font-size: 11px !important; padding: 0px 8px !important; min-height: 0px !important; height: 24px !important; line-height: 22px !important; border-radius: 12px !important; float: right; }
    div[data-testid="column"] button:hover { border-color: #ff4b4b !important; background-color: #ff4b4b !important; color: white !important; }
    .t-red { color: #e74c3c; font-weight: bold; }
    .t-green { color: #2ecc71; font-weight: bold; }
    .t-gray { color: #999; font-size: 12px; }
    .t-lbl { font-size: 10px; color: #bbb; }
    .stock-row { display: flex; justify-content: space-between; font-size: 12px; padding: 5px 0; border-bottom: 1px dashed #f5f5f5; align-items: center; }
</style>
""", unsafe_allow_html=True)

# ================= 2. 数据库与网络设置 =================
conn = sqlite3.connect('zzl_v49_stable.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

# 创建一个带重试机制的 Session，解决“加载失败”问题
def create_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

global_session = create_session()

# ================= 3. 核心逻辑 =================

@st.cache_data(ttl=30, show_spinner=False)
def get_indices():
    codes = [('gb_ixic', '纳斯达克', 1, 26), ('rt_hkHSI', '恒生指数', 6, 3), ('sh000001', '上证指数', 3, 2), ('fx_susdcnh', '离岸汇率', 8, 3)]
    res = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])}"
        r = global_session.get(url, headers={'Referer': 'https://finance.sina.com.cn/'}, timeout=5)
        lines = r.text.strip().split('\n')
        for i, cfg in enumerate(codes):
            try:
                parts = lines[i].split('="')[1].split(',')
                curr = float(parts[cfg[2]]); last = float(parts[cfg[3]])
                if curr == 0: curr = last
                res.append({"n": cfg[1], "v": curr, "p": (curr - last) / last * 100})
            except: res.append({"n": cfg[1], "v": 0.0, "p": 0.0})
    except: return []
    return res

def get_details_worker(p_item):
    code = p_item['c']
    money = p_item['m']
    
    try:
        # 获取估值 (增加超时保护)
        r_gs = global_session.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5)
        # 获取净值
        r_jz = global_session.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=5)
        
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
        hm = now.strftime("%H:%M")
        
        # 判定交易状态和主次显示
        # 规则：交易中->估值亮；休市/收盘->净值亮
        close_time = "15:00"
        if any(k in name for k in ["港", "恒生", "纳斯达克", "QDII"]): close_time = "16:00"

        if is_weekend:
            used = jz_val; status = f"☕ 休市 ({jz_date})"
            use_jz = True # 周末看净值
        else:
            if jz_date == today_str: # 晚上更新了净值
                used = jz_val; status = "✅ 今日已更新"
                use_jz = True
            else: # 白天交易中
                used = gz_val
                use_jz = False # 交易中看估值
                if hm < "09:30": status = f"⏳ 待开盘 ({gz_time})"
                elif "11:30" < hm < "13:00": status = f"☕ 午间休市 ({gz_time})"
                elif hm > close_time: status = f"🏁 已收盘 ({gz_time})"
                else: status = f"⚡ 交易中 ({gz_time})"
        
        return {"c": code, "m": money, "name": name, "gz": gz_val, "jz": jz_val, "jz_date": jz_date, "used": used, "status": status, "use_jz": use_jz, "profit_money": money * (used/100)}
    except Exception as e:
        # 失败时的兜底数据，防止红框报错
        return {"c": code, "m": money, "name": f"加载中..{code}", "gz": 0, "jz": 0, "jz_date": "-", "used": 0, "status": "🔄 同步中", "use_jz": True, "profit_money": 0}

# 🔥🔥🔥【修复核心】持仓穿透逻辑 🔥🔥🔥
@st.cache_data(ttl=300, show_spinner=False)
def get_fund_stocks(fund_code, visited=None):
    if visited is None: visited = set()
    if fund_code in visited: return []
    visited.add(fund_code)
    
    # 1. 尝试直接查股票 (API)
    def fetch_api_stocks(code):
        stocks = []
        try:
            # 这是一个查股票持仓的API
            url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={code}&deviceid=Wap&plat=Wap&product=EFund&version=6.4.4"
            r = global_session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
            data = r.json()
            if data and 'Datas' in data:
                for item in data['Datas'][:10]:
                    raw = item['GPDM']
                    # 只有 159/51/56 开头的才是ETF，其他是股票
                    is_etf = raw.startswith(('159', '51', '56')) 
                    prefix = "sh" if raw.startswith(('6','5')) else ("bj" if raw.startswith(('4','8')) else "sz")
                    stocks.append({"c": f"{prefix}{raw}", "n": item['GPJC'], "raw": raw, "is_etf": is_etf})
        except: pass
        return stocks

    # 2. 查“重仓基金” (针对联接基金/FOF)
    def fetch_held_funds(code):
        # 如果是联接基金，它不会有股票持仓，但会在"基金持仓"里显示它买了哪个ETF
        try:
            # 访问 "基金持仓" 页面 (jjcc)
            url = f"http://fundf10.eastmoney.com/jjcc_{code}.html"
            r = global_session.get(url, timeout=3)
            if r.status_code == 200:
                # 在 HTML 里找链接，类似 href="http://fund.eastmoney.com/159732.html"
                # 排除掉自己，找第一个出现的 6 位代码
                codes = re.findall(r'href="http://fund\.eastmoney\.com/(\d{6})\.html"', r.text)
                for c in codes:
                    if c != code and c.startswith(('159', '51', '56')): # 只要ETF
                        return c
        except: pass
        return None

    # === 执行流程 ===
    
    # A. 先查有没有股票
    holdings = fetch_api_stocks(fund_code)
    
    # B. 检查结果
    if holdings:
        # 如果直接查到了ETF (比如在API里就列出了ETF)，穿透它
        for h in holdings:
            if h['is_etf']: return get_fund_stocks(h['raw'], visited)
        # 如果是真股票，去查价格
        real_stocks = [x for x in holdings if not x.get('is_etf', False)]
        if real_stocks: return get_stock_prices(real_stocks)

    # C. 如果没股票，去查它持有哪个基金 (关键步骤！)
    if not holdings:
        # 针对 018897 这种情况，它持仓是空的，必须查 jjcc (重仓基金)
        target_etf = fetch_held_funds(fund_code)
        if target_etf:
            # 找到了爹 (比如 159732)，递归查爹的股票
            return get_fund_stocks(target_etf, visited)

    return []

def get_stock_prices(stock_list):
    if not stock_list: return []
    try:
        sina_codes = [x['c'] for x in stock_list]
        url = f"http://hq.sinajs.cn/list={','.join(sina_codes)}"
        r = global_session.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=3)
        lines = r.text.strip().split('\n')
        final_res = []
        code_map = {x['c']: x['n'] for x in stock_list}
        for line in lines:
            if '="' in line:
                key = line.split('="')[0].split('hq_str_')[-1]
                val = line.split('="')[1]
                parts = val.split(',')
                if len(parts) > 3:
                    curr = float(parts[3]); last = float(parts[2])
                    if curr == 0: curr = last
                    pct = (curr - last) / last * 100 if last > 0 else 0.0
                    name = parts[0] if parts[0] else code_map.get(key, "--")
                    final_res.append({"n": name, "v": curr, "p": pct})
        return final_res
    except: return []

# ================= 4. 页面渲染 =================

c_title, c_btn = st.columns([0.75, 0.25])
with c_title: st.markdown("##### 🌍 全球行情")
with c_btn:
    if st.button("🔄 刷新", use_container_width=True):
        st.cache_data.clear(); st.rerun()

idx_data = get_indices()
if idx_data:
    h = '<div class="market-scroll">'
    for d in idx_data:
        c = "t-red" if d['p'] >= 0 else "t-green"
        h += f'<div class="market-card-small"><div class="t-gray">{d["n"]}</div><div class="{c}">{d["v"]:.2f}</div><div class="{c}" style="font-size:10px;">{d["p"]:+.2f}%</div></div>'
    h += '</div>'
    st.markdown(h, unsafe_allow_html=True)
else: st.caption("行情加载中...")

if 'portfolio' not in st.session_state:
    row = conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    st.session_state.portfolio = json.loads(row[0]) if row else []

# 并发获取数据
total_money = 0.0; total_profit = 0.0; final_list = []
if st.session_state.portfolio:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_details_worker, st.session_state.portfolio))
    for item in results:
        # 只统计成功加载的数据
        if "加载中" not in item['name']:
            total_money += item['m']; total_profit += item['profit_money']
        final_list.append(item)

bg_cls = "#ff4b4b" if total_profit >= 0 else "#2ecc71"
st.markdown(f"""<div class="hero-box" style="background:{bg_cls}"><div style="opacity:0.9; font-size:14px;">总盈亏 (CNY)</div><div style="font-size:40px; font-weight:bold; margin:5px 0;">{total_profit:+.2f}</div><div style="font-size:12px; opacity:0.8;">持仓本金: {total_money:,.0f}</div></div>""", unsafe_allow_html=True)

st.markdown("##### 📑 基金明细")
if not final_list: st.info("请在左侧添加基金")

for item in final_list:
    c1, c2 = st.columns([0.8, 0.2])
    with c1: st.markdown(f"**{item['name']}** <span style='color:#ccc; font-size:12px'>{item['c']}</span>", unsafe_allow_html=True)
    with c2:
        if st.button("删除", key=f"del_{item['c']}"):
            new_p = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            st.session_state.portfolio = new_p
            conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_p), current_user))
            conn.commit(); st.rerun()

    # 修复UI透明度逻辑 (图2的问题)
    # 规则：如果不使用净值(交易中)，估值(左)为1.0，净值(右)为0.5
    #      如果使用净值(收盘/周末)，估值(左)为0.5，净值(右)为1.0
    if item['use_jz']:
        op_gz = "0.5"; wt_gz = "normal"
        op_jz = "1.0"; wt_jz = "bold"
    else:
        op_gz = "1.0"; wt_gz = "bold"
        op_jz = "0.5"; wt_jz = "normal"
    
    color_jz = "#e74c3c" if item['jz'] >= 0 else "#2ecc71"
    color_gz = "#e74c3c" if item['gz'] >= 0 else "#2ecc71"
    profit_color = "#e74c3c" if item['profit_money'] >= 0 else "#2ecc71"

    card = f"""
    <div class="fund-container">
        <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px dashed #eee; padding-bottom:5px;">
            <div style="font-size:12px; color:#666;">{item['status']}</div>
            <div style="font-size:14px; font-weight:bold; color:{profit_color}">¥ {item['profit_money']:+.2f}</div>
        </div>
        <div style="display:flex; justify-content:space-between; text-align:center;">
            <div style="flex:1; opacity:{op_gz};">
                <div class="t-lbl">实时估值</div>
                <div style="color:{color_gz}; font-weight:{wt_gz}; font-size:16px;">{item['gz']:+.2f}%</div>
            </div>
            <div style="width:1px; background:#eee;"></div>
            <div style="flex:1; opacity:{op_jz};">
                <div class="t-lbl">官方净值 ({item['jz_date'][5:]})</div>
                <div style="color:{color_jz}; font-weight:{wt_jz}; font-size:16px;">{item['jz']:+.2f}%</div>
            </div>
        </div>
    </div>
    """
    st.markdown(card, unsafe_allow_html=True)
    
    with st.expander("📊 前十持仓 (智能穿透)"):
        # 智能穿透：018897 -> 查不到股票 -> 查重仓基金 -> 找到159732 -> 查159732股票
        stocks = get_fund_stocks(item['c'])
        if stocks:
            for s in stocks:
                s_color = "t-red" if s['p'] >= 0 else "t-green"
                st.markdown(f"""<div class="stock-row"><span style="flex:2; color:#333; font-weight:500;">{s['n']}</span><span style="flex:1; text-align:right; font-family:monospace;" class="{s_color}">{s['v']:.2f}</span><span style="flex:1; text-align:right; font-family:monospace;" class="{s_color}">{s['p']:+.2f}%</span></div>""", unsafe_allow_html=True)
        else:
            st.caption("暂无数据 (已尝试穿透查询，仍无数据)")
    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("➕ 添加")
    with st.form("add"):
        code_input = st.text_input("代码", placeholder="014143")
        money = st.number_input("本金", value=10000.0)
        if st.form_submit_button("确认"):
            try:
                # 校验代码有效性
                r = global_session.get(f"http://fundgz.1234567.com.cn/js/{code_input}.js", timeout=3)
                if r.status_code == 200:
                    ls = [x for x in st.session_state.portfolio if x['c'] != code_input]
                    ls.append({"c": code_input, "m": money})
                    st.session_state.portfolio = ls
                    conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(ls), current_user)); conn.commit()
                    st.success(f"已添加"); st.rerun()
                else: st.error("代码错误")
            except: st.error("网络错误，请重试")
