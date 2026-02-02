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
st_autorefresh(interval=30 * 1000, key="global_refresh")

st.markdown("""
<style>
    .stApp { background-color: #f5f7f9; }
    .market-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 5px 2px; scrollbar-width: none; margin-bottom: 10px; }
    .market-card-small { background: white; border: 1px solid #eee; border-radius: 6px; min-width: 80px; text-align: center; padding: 8px 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .hero-box { background: linear-gradient(135deg, #2c3e50 0%, #000000 100%); color: white; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    .fund-container { background: white; border-radius: 10px; padding: 12px; border: 1px solid #e0e0e0; margin-bottom: 0px; box-shadow: 0 2px 5px rgba(0,0,0,0.08); }
    .t-red { color: #e74c3c; font-weight: bold; }
    .t-green { color: #2ecc71; font-weight: bold; }
    .t-gray { color: #999; font-size: 12px; }
    .stock-row { display: flex; justify-content: space-between; font-size: 12px; padding: 5px 0; border-bottom: 1px dashed #f5f5f5; align-items: center; }
</style>
""", unsafe_allow_html=True)

# ================= 2. 网络设置 =================
conn = sqlite3.connect('zzl_v52_fixed.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

def create_session():
    session = requests.Session()
    # 模拟真实浏览器，减少被拦截概率
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'http://fund.eastmoney.com/'
    })
    # 遇到错误自动重试
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

global_session = create_session()

# ================= 3. 核心逻辑 (完全重写穿透算法) =================

@st.cache_data(ttl=60, show_spinner=False)
def get_indices():
    # 简单行情，如果失败就返回空，不卡死
    try:
        url = "http://hq.sinajs.cn/list=gb_ixic,rt_hkHSI,sh000001"
        r = global_session.get(url, timeout=3)
        res = []
        codes = [('gb_ixic', '纳指'), ('rt_hkHSI', '恒指'), ('sh000001', '上证')]
        lines = r.text.strip().split('\n')
        for i, (c, n) in enumerate(codes):
            parts = lines[i].split('="')[1].split(',')
            curr = float(parts[1 if c=='gb_ixic' else 6 if c=='rt_hkHSI' else 3])
            last = float(parts[26 if c=='gb_ixic' else 3 if c=='rt_hkHSI' else 2])
            res.append({"n": n, "v": curr, "p": (curr-last)/last*100})
        return res
    except: return []

def get_details_worker(p_item):
    # 这是获取净值和估值的主函数，不涉及持仓穿透
    code = p_item['c']; money = p_item['m']
    try:
        # 获取实时估值
        r_gs = global_session.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=3)
        # 获取最新净值
        r_jz = global_session.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=3)
        
        name = code; gz_val = 0.0; jz_val = 0.0; jz_date = "-"
        
        if r_gs.status_code == 200:
            txt = r_gs.text
            if "name" in txt: name = re.search(r'name":"(.*?)"', txt).group(1)
            if "gszzl" in txt: gz_val = float(re.search(r'gszzl":"(.*?)"', txt).group(1))
            
        if r_jz.status_code == 200:
            tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
            if len(tds) > 3:
                jz_date = tds[0].text.strip()
                v = tds[3].text.strip().replace("%","")
                if v: jz_val = float(v)

        # 计算逻辑
        now = datetime.now()
        is_today_updated = (jz_date == now.strftime("%Y-%m-%d"))
        # 如果还没收盘，或者今天净值还没出，用估值；否则用净值
        used_val = jz_val if is_today_updated else gz_val
        status = "✅ 更新" if is_today_updated else "⚡ 估值"
        
        # 周末强制用净值
        if now.weekday() >= 5:
            used_val = jz_val; status = "☕ 休市"

        return {"c": code, "m": money, "name": name, "gz": gz_val, "jz": jz_val, "jz_date": jz_date, "profit": money * (used_val/100), "status": status, "err": False}
    except:
        return {"c": code, "m": money, "name": f"等待同步..{code}", "gz": 0, "jz": 0, "jz_date": "-", "profit": 0, "status": "🔄", "err": True}

# 🔥🔥🔥【V52 官方关联穿透法】🔥🔥🔥
@st.cache_data(ttl=300, show_spinner=False)
def get_fund_stocks(fund_code, visited=None):
    if visited is None: visited = set()
    if fund_code in visited: return []
    visited.add(fund_code)
    
    # 1. 直接查股票 API (最优先)
    def fetch_api_stocks(code):
        stocks = []
        try:
            url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={code}&deviceid=Wap&plat=Wap&product=EFund&version=6.4.4"
            r = global_session.get(url, timeout=3)
            data = r.json()
            if 'Datas' in data and data['Datas']:
                for item in data['Datas'][:10]:
                    raw = item['GPDM']
                    is_etf = raw.startswith(('159', '51', '56')) 
                    prefix = "sh" if raw.startswith(('6','5')) else ("bj" if raw.startswith(('4','8')) else "sz")
                    stocks.append({"c": f"{prefix}{raw}", "n": item['GPJC'], "raw": raw, "is_etf": is_etf})
        except: pass
        return stocks

    # 2. 从HTML中找持有的ETF (联接基金专用)
    # 不瞎猜，直接去“持仓”页面找 href 指向 ETF 页面的链接
    def fetch_held_etf_from_html(code):
        try:
            url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10"
            r = global_session.get(url, timeout=3)
            # 查找链接 <a href="http://fund.eastmoney.com/159732.html">
            # 这种是最准的，因为它不仅是数字，还是链接
            match = re.search(r'href="http://fund\.eastmoney\.com/(159\d{3}|51\d{3}|56\d{3})\.html"', r.text)
            if match:
                return match.group(1)
        except: pass
        return None

    # 3. 【核心修复】读取JS配置查找官方关联基金 (不猜代码-1)
    def fetch_brother_from_js(code):
        try:
            url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
            r = global_session.get(url, timeout=3)
            if r.status_code == 200:
                # 查找 fS_code = "018896" 这种格式
                match = re.search(r'fS_code\s*=\s*["\'](\d{6})["\']', r.text)
                if match:
                    brother = match.group(1)
                    if brother != code: return brother
        except: pass
        return None

    # === 执行链条 ===
    
    # A. 查自己
    holdings = fetch_api_stocks(fund_code)
    
    # B. 如果自己持有的是ETF (API显示)，直接穿透ETF
    if holdings:
        for h in holdings:
            if h['is_etf']: return get_fund_stocks(h['raw'], visited)
        # 否则就是真股票
        return get_stock_prices(holdings)

    # C. 如果API没数据，去HTML页面找有没有持仓ETF (针对联接基金)
    # 例如：018897 的API可能是空的，但页面上写着持有 159732
    if not holdings:
        etf_code = fetch_held_etf_from_html(fund_code)
        if etf_code:
            return get_fund_stocks(etf_code, visited)

    # D. 如果还是没数据，读取JS配置，找“大哥” (A类/主份额)
    # 例如：018897 -> fS_code=018896
    if not holdings:
        brother = fetch_brother_from_js(fund_code)
        if brother and brother not in visited:
            return get_fund_stocks(brother, visited)

    return []

def get_stock_prices(stock_list):
    # 批量查股价
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
                val = line.split('="')[1].split(',')
                if len(val) > 3:
                    curr = float(val[3]); last = float(val[2])
                    if curr == 0: curr = last
                    pct = (curr - last) / last * 100 if last > 0 else 0.0
                    name = val[0] if val[0] else code_map.get(key, "--")
                    final_res.append({"n": name, "v": curr, "p": pct})
        return final_res
    except: return []

# ================= 4. UI 渲染 =================

c1, c2 = st.columns([3, 1])
with c1: st.markdown("##### 🌍 市场概况")
with c2: 
    if st.button("🔄 刷新"): st.cache_data.clear(); st.rerun()

# 渲染指数
ids = get_indices()
if ids:
    cols = st.columns(len(ids))
    for i, d in enumerate(ids):
        color = "red" if d['p']>=0 else "green"
        cols[i].markdown(f"**{d['n']}** <span style='color:{color}'>{d['v']:.2f} ({d['p']:+.2f}%)</span>", unsafe_allow_html=True)

# 渲染持仓
if 'portfolio' not in st.session_state:
    row = conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    st.session_state.portfolio = json.loads(row[0]) if row else []

if not st.session_state.portfolio:
    st.info("👈 左侧添加基金 (已移除网络校验，强制添加)")

final_data = []
total_p = 0
with ThreadPoolExecutor(max_workers=5) as ex:
    res = list(ex.map(get_details_worker, st.session_state.portfolio))

for r in res:
    if not r['err']: total_p += r['profit']
    final_data.append(r)

st.markdown(f"### 总盈亏: :{'red' if total_p>=0 else 'green'}[{total_p:+.2f}]")

for item in final_data:
    with st.expander(f"{item['name']} ({item['c']}) {item['profit']:+.2f}", expanded=False):
        c_up, c_del = st.columns([4,1])
        with c_up:
            st.write(f"估值: {item['gz']:+.2f}% | 净值: {item['jz']:+.2f}% ({item['jz_date'][5:]}) | {item['status']}")
        with c_del:
            if st.button("删", key=f"d_{item['c']}"):
                new_p = [x for x in st.session_state.portfolio if x['c'] != item['c']]
                st.session_state.portfolio = new_p
                conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_p), current_user))
                conn.commit(); st.rerun()
        
        # 穿透持仓展示
        st.divider()
        st.caption("🔍 穿透持仓 (智能关联 C类->A类->ETF->股票)")
        stocks = get_fund_stocks(item['c'])
        if stocks:
            for s in stocks:
                color = "red" if s['p']>=0 else "green"
                st.markdown(f"<div class='stock-row'><span>{s['n']}</span><span style='color:{color}'>{s['v']} ({s['p']:+.2f}%)</span></div>", unsafe_allow_html=True)
        else:
            st.caption("暂无公开持仓数据 (可能为新发基金或纯债基)")

# ================= 5. 侧边栏 (无校验强制添加) =================
with st.sidebar:
    st.header("添加基金")
    with st.form("add"):
        code = st.text_input("代码 (6位数字)", max_chars=6)
        amt = st.number_input("持有金额", value=10000)
        if st.form_submit_button("添加"):
            if len(code) == 6 and code.isdigit():
                # 直接添加，不查API，避免被误杀
                ls = [x for x in st.session_state.portfolio if x['c'] != code]
                ls.append({"c": code, "m": amt})
                st.session_state.portfolio = ls
                conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(ls), current_user))
                conn.commit()
                st.success(f"已强制添加 {code}，数据正在后台同步...")
                st.rerun()
            else:
                st.error("请输入正确的6位代码")
