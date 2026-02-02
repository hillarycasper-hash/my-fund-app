import streamlit as st
import requests
import re
import sqlite3
import json
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor

# ================= 1. 基础配置 (完全保持不变) =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered")

# 保持30秒刷新
st_autorefresh(interval=30 * 1000, key="global_refresh")

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

# ================= 2. 数据库 =================
conn = sqlite3.connect('zzl_v47_fix.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

# ================= 3. 数据获取逻辑 (保留并发加速) =================

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
    except: return []
    return res

def get_details_worker(p_item):
    code = p_item['c']
    money = p_item['m']
    try:
        # 并发获取估值和净值
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=2)
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=2)
        
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
        close_time = "16:00" if any(k in name for k in ["港", "恒生", "纳斯达克", "QDII"]) else "15:00"
        
        if is_weekend:
            used = jz_val; status = f"☕ 休市 ({jz_date})"
            use_jz = True
        else:
            if jz_date == today_str: used = jz_val; status = "✅ 今日已更新"; use_jz = True
            else:
                used = gz_val; use_jz = False
                if hm < "09:30": status = f"⏳ 待开盘 ({gz_time})"
                elif "11:30" < hm < "13:00": status = f"☕ 午间休市 ({gz_time})"
                elif hm > close_time: status = f"🏁 已收盘 ({gz_time})"
                else: status = f"⚡ 交易中 ({gz_time})"
        
        return {"c": code, "m": money, "name": name, "gz": gz_val, "jz": jz_val, "jz_date": jz_date, "used": used, "status": status, "use_jz": use_jz, "profit_money": money * (used/100)}
    except: return {"c": code, "m": money, "name": "加载失败", "gz": 0, "jz": 0, "jz_date": "-", "used": 0, "status": "❌ Err", "use_jz": True, "profit_money": 0}

# 🔥🔥🔥【V47 修复核心】专门针对“持有ETF的联接基金”的逻辑 🔥🔥🔥
@st.cache_data(ttl=300, show_spinner=False)
def get_fund_stocks(fund_code, visited=None):
    if visited is None: visited = set()
    if fund_code in visited: return []
    visited.add(fund_code)
    
    # 防止死循环
    if len(visited) > 6: return []

    # === 工具函数：查普通持仓 ===
    def fetch_api_stocks(code):
        stocks = []
        try:
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}
            url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={code}&deviceid=Wap&plat=Wap&product=EFund&version=6.4.4"
            r = requests.get(url, headers=headers, timeout=2)
            data = r.json()
            if data and 'Datas' in data:
                for item in data['Datas'][:10]:
                    raw = item['GPDM']
                    is_etf = raw.startswith(('159', '51', '56', '58'))
                    prefix = "sh" if raw.startswith(('6','5')) else ("bj" if raw.startswith(('4','8')) else "sz")
                    stocks.append({"c": f"{prefix}{raw}", "n": item['GPJC'], "raw": raw, "is_etf": is_etf})
        except: pass
        return stocks

    # === 工具函数：查“持有的基金” (针对联接基金/FOF) ===
    def fetch_held_etf_specifically(code):
        try:
            # 使用“持仓明细”网页，因为它会列出“期末持有的基金”
            url = f"http://fundf10.eastmoney.com/ccmx_{code}.html"
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
            # 正则特异性匹配 ETF 代码
            # 匹配逻辑：href 指向 fund.eastmoney.com/代码.html，且代码以 159/51 开头
            etfs = re.findall(r'href="http://fund\.eastmoney\.com/(159\d{3}|51\d{3}|56\d{3})\.html"', r.text)
            if etfs:
                return etfs[0] # 返回第一个找到的 ETF，通常是核心资产
        except: pass
        return None

    # === 核心流程 ===
    
    # 1. 尝试直接查股票 (API)
    holdings = fetch_api_stocks(fund_code)
    
    # 2. 如果查到了 ETF (API里直接显示了)，直接穿透
    for h in holdings:
        if h['is_etf']:
            return get_fund_stocks(h['raw'], visited)

    # 3. 如果持仓为空 (说明可能是 C类 或 联接基金A类)，尝试“找爹”或“找ETF”
    if not holdings:
        # A. 看看是不是C类，转成A类试试
        parent_code = fund_code
        try:
            r_map = requests.get(f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js", timeout=1)
            match = re.search(r'fS_code\s*=\s*["\'](\d+)["\']', r_map.text)
            if match:
                parent_code = match.group(1)
        except: pass

        # 如果 parent_code 变了，先查一遍 parent_code 的股票
        if parent_code != fund_code:
            holdings = fetch_api_stocks(parent_code)
            # 检查 parent 的持仓有没有 ETF
            for h in holdings:
                if h['is_etf']: return get_fund_stocks(h['raw'], visited)
            if holdings: 
                # 如果 parent 有真实股票，就查股价
                real_stocks = [x for x in holdings if not x.get('is_etf', False)]
                if real_stocks: return get_stock_prices(real_stocks)

        # B. 如果 A类 也是空的 (018896就是这种情况)，说明它彻底是个壳，必须去网页挖 ETF
        # 扫描 parent_code 的网页
        found_etf = fetch_held_etf_specifically(parent_code)
        if found_etf:
            # 找到了藏在网页里的 ETF (如 159732)
            return get_fund_stocks(found_etf, visited)

    # 4. 只有全是真股票才去查价格
    real_stocks = [x for x in holdings if not x.get('is_etf', False)]
    return get_stock_prices(real_stocks)

# 查股价函数 (复用)
def get_stock_prices(stock_list):
    if not stock_list: return []
    try:
        sina_codes = [x['c'] for x in stock_list]
        url_hq = f"http://hq.sinajs.cn/list={','.join(sina_codes)}"
        r_hq = requests.get(url_hq, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=2)
        lines = r_hq.text.strip().split('\n')
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

# ================= 4. 页面渲染 (保持原样) =================

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

# 多线程并发执行
total_money = 0.0; total_profit = 0.0; final_list = []
if st.session_state.portfolio:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_details_worker, st.session_state.portfolio))
    for item in results:
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

    color_jz = "#e74c3c" if item['jz'] >= 0 else "#2ecc71"; wt_jz = "bold" if item['use_jz'] else "normal"
    color_gz = "#e74c3c" if item['gz'] >= 0 else "#2ecc71"; wt_gz = "bold" if not item['use_jz'] else "normal"
    profit_color = "#e74c3c" if item['profit_money'] >= 0 else "#2ecc71"

    card = f"""
    <div class="fund-container">
        <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px dashed #eee; padding-bottom:5px;">
            <div style="font-size:12px; color:#666;">{item['status']}</div>
            <div style="font-size:14px; font-weight:bold; color:{profit_color}">¥ {item['profit_money']:+.2f}</div>
        </div>
        <div style="display:flex; justify-content:space-between; text-align:center;">
            <div style="flex:1;"><div class="t-lbl">实时估值</div><div style="color:{color_gz}; font-weight:{wt_gz}; font-size:16px;">{item['gz']:+.2f}%</div></div>
            <div style="width:1px; background:#eee;"></div>
            <div style="flex:1;"><div class="t-lbl">官方净值 ({item['jz_date'][5:]})</div><div style="color:{color_jz}; font-weight:{wt_jz}; font-size:16px;">{item['jz']:+.2f}%</div></div>
        </div>
    </div>
    """
    st.markdown(card, unsafe_allow_html=True)
    
    with st.expander("📊 前十持仓 (智能穿透)"):
        # 这里调用函数，不影响主线程速度，只有点开时才加载
        stocks = get_fund_stocks(item['c'])
        if stocks:
            for s in stocks:
                s_color = "t-red" if s['p'] >= 0 else "t-green"
                st.markdown(f"""<div class="stock-row"><span style="flex:2; color:#333; font-weight:500;">{s['n']}</span><span style="flex:1; text-align:right; font-family:monospace;" class="{s_color}">{s['v']:.2f}</span><span style="flex:1; text-align:right; font-family:monospace;" class="{s_color}">{s['p']:+.2f}%</span></div>""", unsafe_allow_html=True)
        else:
            st.caption("暂无数据 (此基金可能未披露最新持仓)")
    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("➕ 添加")
    with st.form("add"):
        code_input = st.text_input("代码", placeholder="014143")
        money = st.number_input("本金", value=10000.0)
        if st.form_submit_button("确认"):
            if requests.get(f"http://fundgz.1234567.com.cn/js/{code_input}.js").status_code == 200:
                ls = [x for x in st.session_state.portfolio if x['c'] != code_input]
                ls.append({"c": code_input, "m": money})
                st.session_state.portfolio = ls
                conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(ls), current_user)); conn.commit()
                st.success(f"已添加"); st.rerun()
            else: st.error("代码错误")
