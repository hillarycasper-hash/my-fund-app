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

# ================= 1. 基础配置 (完全还原UI) =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered")
st_autorefresh(interval=30 * 1000, key="global_refresh")

st.markdown("""
<style>
    .stApp { background-color: #f5f7f9; }
    /* 还原横向滚动条 */
    .market-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 5px 2px; scrollbar-width: none; margin-bottom: 10px; }
    .market-card-small { background: white; border: 1px solid #eee; border-radius: 6px; min-width: 80px; text-align: center; padding: 8px 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    /* 还原深色Hero Box */
    .hero-box { background: linear-gradient(135deg, #2c3e50 0%, #000000 100%); color: white; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    .fund-container { background: white; border-radius: 10px; padding: 12px; border: 1px solid #e0e0e0; margin-bottom: 0px; box-shadow: 0 2px 5px rgba(0,0,0,0.08); }
    /* 还原按钮样式 */
    div[data-testid="column"] button { border: 1px solid #ffcccc !important; background: white !important; color: #ff4b4b !important; font-size: 11px !important; padding: 0px 8px !important; min-height: 0px !important; height: 24px !important; line-height: 22px !important; border-radius: 12px !important; float: right; }
    div[data-testid="column"] button:hover { border-color: #ff4b4b !important; background-color: #ff4b4b !important; color: white !important; }
    .t-red { color: #e74c3c; font-weight: bold; }
    .t-green { color: #2ecc71; font-weight: bold; }
    .t-gray { color: #999; font-size: 12px; }
    .t-lbl { font-size: 10px; color: #bbb; }
    .stock-row { display: flex; justify-content: space-between; font-size: 12px; padding: 5px 0; border-bottom: 1px dashed #f5f5f5; align-items: center; }
</style>
""", unsafe_allow_html=True)

# ================= 2. 网络底层 (加强伪装) =================
conn = sqlite3.connect('zzl_v53_restored.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Referer': 'http://fund.eastmoney.com/'
    })
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

global_session = create_session()

# ================= 3. 核心逻辑 (修复持仓+添加) =================

@st.cache_data(ttl=60, show_spinner=False)
def get_indices():
    # 还原：横向滚动的三个指数
    codes = [('gb_ixic', '纳斯达克', 1, 26), ('rt_hkHSI', '恒生指数', 6, 3), ('sh000001', '上证指数', 3, 2)]
    res = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join([c[0] for c in codes])}"
        r = global_session.get(url, timeout=3)
        lines = r.text.strip().split('\n')
        for i, cfg in enumerate(codes):
            try:
                parts = lines[i].split('="')[1].split(',')
                curr = float(parts[cfg[2]]); last = float(parts[cfg[3]])
                res.append({"n": cfg[1], "v": curr, "p": (curr - last) / last * 100})
            except: res.append({"n": cfg[1], "v": 0.0, "p": 0.0})
    except: return []
    return res

def get_details_worker(p_item):
    code = p_item['c']; money = p_item['m']
    try:
        r_gs = global_session.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=3)
        r_jz = global_session.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=3)
        
        name = code; gz_val = 0.0; jz_val = 0.0; jz_date = ""
        if r_gs.status_code == 200:
            txt = r_gs.text
            if "name" in txt: name = re.search(r'name":"(.*?)"', txt).group(1)
            if "gszzl" in txt: gz_val = float(re.search(r'gszzl":"(.*?)"', txt).group(1))
            
        if r_jz.status_code == 200:
            tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
            if len(tds) > 3:
                jz_date = tds[0].text.strip()
                v_str = tds[3].text.strip().replace("%","")
                jz_val = float(v_str) if v_str else 0.0

        now = datetime.now()
        is_weekend = now.weekday() >= 5
        use_jz = (jz_date == now.strftime("%Y-%m-%d")) or is_weekend
        
        used = jz_val if use_jz else gz_val
        status = f"✅ 净值 ({jz_date})" if use_jz else "⚡ 估值"
        
        return {"c": code, "m": money, "name": name, "gz": gz_val, "jz": jz_val, "jz_date": jz_date, "used": used, "status": status, "use_jz": use_jz, "profit_money": money * (used/100)}
    except:
        return {"c": code, "m": money, "name": f"⏳ 加载中..{code}", "gz": 0, "jz": 0, "jz_date": "-", "used": 0, "status": "🔄", "use_jz": True, "profit_money": 0}

# 🔥【核心修复】持仓穿透逻辑
@st.cache_data(ttl=300, show_spinner=False)
def get_fund_stocks(fund_code, visited=None):
    if visited is None: visited = set()
    if fund_code in visited: return []
    visited.add(fund_code)
    
    # 1. 尝试直接获取股票 (API)
    stocks = []
    try:
        url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=6.4.4"
        r = global_session.get(url, timeout=3)
        data = r.json()
        if 'Datas' in data and data['Datas']:
            for item in data['Datas'][:10]:
                raw = item['GPDM']
                is_etf = raw.startswith(('159', '51', '56')) 
                prefix = "sh" if raw.startswith(('6','5')) else ("bj" if raw.startswith(('4','8')) else "sz")
                stocks.append({"c": f"{prefix}{raw}", "n": item['GPJC'], "raw": raw, "is_etf": is_etf})
    except: pass

    # 2. 如果API拿到了数据
    if stocks:
        # 检查是否全是ETF (联接基金情况)
        for s in stocks:
            if s['is_etf']: return get_fund_stocks(s['raw'], visited) # 递归穿透ETF
        return get_stock_prices(stocks) # 正常的股票基金

    # 3. 🔥如果API是空的 (比如 018897 C类)，去HTML页面硬抓“持仓ETF”
    # 这一步专门解决“联接基金”看不到持仓的问题
    try:
        url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=10"
        r = global_session.get(url, timeout=3)
        # 寻找类似于 <a href='...159732.html'>159732</a> 的结构
        etf_codes = re.findall(r'href="http://fund\.eastmoney\.com/(159\d{3}|51\d{3}|56\d{3})\.html"', r.text)
        if etf_codes:
            # 找到了它持有的ETF (比如 159732)，直接去查这个ETF的持仓
            return get_fund_stocks(etf_codes[0], visited)
    except: pass

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
                val = line.split('="')[1].split(',')
                if len(val) > 3:
                    curr = float(val[3]); last = float(val[2])
                    if curr == 0: curr = last
                    pct = (curr - last) / last * 100 if last > 0 else 0.0
                    final_res.append({"n": val[0], "v": curr, "p": pct})
        return final_res
    except: return []

# ================= 4. 界面渲染 (还原旧版) =================

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

if 'portfolio' not in st.session_state:
    row = conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    st.session_state.portfolio = json.loads(row[0]) if row else []

total_money = 0.0; total_profit = 0.0; final_list = []
if st.session_state.portfolio:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_details_worker, st.session_state.portfolio))
    for item in results:
        if "加载中" not in item['name']:
            total_money += item['m']; total_profit += item['profit_money']
        final_list.append(item)

# 还原：深色 Hero Box
bg_cls = "#e74c3c" if total_profit >= 0 else "#2ecc71" # 使用标准红绿颜色
st.markdown(f"""
<div class="hero-box">
    <div style="opacity:0.9; font-size:14px;">总盈亏 (CNY)</div>
    <div style="font-size:40px; font-weight:bold; margin:5px 0; color:{bg_cls}">{total_profit:+.2f}</div>
    <div style="font-size:12px; opacity:0.8;">持仓本金: {total_money:,.0f}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("##### 📑 基金明细")

for item in final_list:
    c1, c2 = st.columns([0.8, 0.2])
    with c1: st.markdown(f"**{item['name']}** <span style='color:#ccc; font-size:12px'>{item['c']}</span>", unsafe_allow_html=True)
    with c2:
        if st.button("删除", key=f"del_{item['c']}"):
            new_p = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            st.session_state.portfolio = new_p
            conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_p), current_user))
            conn.commit(); st.rerun()

    # 样式逻辑
    color_jz = "#e74c3c" if item['jz'] >= 0 else "#2ecc71"
    color_gz = "#e74c3c" if item['gz'] >= 0 else "#2ecc71"
    profit_color = "#e74c3c" if item['profit_money'] >= 0 else "#2ecc71"
    
    st.markdown(f"""
    <div class="fund-container">
        <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px dashed #eee; padding-bottom:5px;">
            <div style="font-size:12px; color:#666;">{item['status']}</div>
            <div style="font-size:14px; font-weight:bold; color:{profit_color}">¥ {item['profit_money']:+.2f}</div>
        </div>
        <div style="display:flex; justify-content:space-between; text-align:center;">
            <div style="flex:1;">
                <div class="t-lbl">实时估值</div>
                <div style="color:{color_gz}; font-weight:bold; font-size:16px;">{item['gz']:+.2f}%</div>
            </div>
            <div style="width:1px; background:#eee;"></div>
            <div style="flex:1;">
                <div class="t-lbl">官方净值 ({item['jz_date'][5:]})</div>
                <div style="color:{color_jz}; font-weight:bold; font-size:16px;">{item['jz']:+.2f}%</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("📊 穿透持仓 (智能分析)"):
        stocks = get_fund_stocks(item['c'])
        if stocks:
            for s in stocks:
                s_color = "t-red" if s['p'] >= 0 else "t-green"
                st.markdown(f"""<div class="stock-row"><span style="flex:2;">{s['n']}</span><span style="flex:1; text-align:right;">{s['v']:.2f}</span><span style="flex:1; text-align:right;" class="{s_color}">{s['p']:+.2f}%</span></div>""", unsafe_allow_html=True)
        else:
            st.caption("暂无数据 (已尝试穿透查询 ETF)")
    st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)

# ================= 5. 侧边栏 (绝对不再报错版) =================
with st.sidebar:
    st.header("➕ 添加")
    with st.form("add_fast"):
        code_input = st.text_input("代码", placeholder="018897")
        money = st.number_input("本金", value=10000.0)
        submitted = st.form_submit_button("确认")
        
        if submitted:
            # 🛑 关键修改：只要是6位数字，直接写入，绝不联网校验
            # 这样就永远不会出现“网络错误”
            if len(code_input) == 6 and code_input.isdigit():
                current_list = st.session_state.portfolio
                # 查重
                if not any(x['c'] == code_input for x in current_list):
                    current_list.append({"c": code_input, "m": money})
                    st.session_state.portfolio = current_list
                    conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(current_list), current_user))
                    conn.commit()
                    st.success(f"✅ 已强制添加 {code_input}")
                    st.rerun()
                else:
                    st.warning("已存在")
            else:
                st.error("请输入6位数字代码")
