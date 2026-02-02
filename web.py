import streamlit as st
import requests
import re
import sqlite3
import json
from datetime import datetime
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor

# ================= 1. 基础配置 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="centered")

# 保持30秒刷新，但因为有了并发，加载会极快
st_autorefresh(interval=30 * 1000, key="global_refresh")

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
conn = sqlite3.connect('zzl_v45_speed.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

# ================= 3. 数据获取逻辑 (并发加速版) =================

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

# 单个基金获取详情（将被多线程调用）
def get_details_worker(p_item):
    code = p_item['c']
    money = p_item['m']
    try:
        # 并行请求估值和净值，减少等待
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
        
        close_time = "15:00"
        if any(keyword in name for keyword in ["港", "恒生", "H股", "互联", "纳斯达克", "标普", "QDII"]): 
            close_time = "16:00"

        if is_weekend:
            used_rate = jz_val
            status_txt = f"☕ 休市 ({jz_date})"
            is_using_jz = True
        else:
            if jz_date == today_str: 
                used_rate = jz_val
                status_txt = "✅ 今日已更新"
                is_using_jz = True
            else:
                used_rate = gz_val
                is_using_jz = False
                if hm < "09:30":
                    status_txt = f"⏳ 待开盘 ({gz_time})"
                elif "11:30" < hm < "13:00":
                    status_txt = f"☕ 午间休市 ({gz_time})"
                elif hm > close_time:
                    status_txt = f"🏁 已收盘 ({gz_time})"
                else:
                    status_txt = f"⚡ 交易中 ({gz_time})"
        
        profit = money * (used_rate / 100)
        return {
            "c": code, "m": money, "name": name, 
            "gz": gz_val, "jz": jz_val, "jz_date": jz_date, 
            "used": used_rate, "status": status_txt, "use_jz": is_using_jz,
            "profit_money": profit
        }
    except: 
        return {
            "c": code, "m": money, "name": "加载失败", 
            "gz": 0, "jz": 0, "jz_date": "-", 
            "used": 0, "status": "❌ 网络错误", "use_jz": True,
            "profit_money": 0
        }

# 🔥🔥🔥【V45 强力穿透版】针对 018897 这种顽固分子的终极方案 🔥🔥🔥
@st.cache_data(ttl=300, show_spinner=False)
def get_fund_stocks(fund_code, visited=None):
    if visited is None: visited = set()
    if fund_code in visited: return []
    visited.add(fund_code)
    
    # 防止无限递归
    if len(visited) > 8: return []

    # 1. 通用 API 获取
    def fetch_data(target):
        stocks = []
        try:
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}
            url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={target}&deviceid=Wap&plat=Wap&product=EFund&version=6.4.4"
            r = requests.get(url, headers=headers, timeout=2)
            data = r.json()
            if data and 'Datas' in data:
                # 检查是否包含 ETF 代码 (159xxx, 51xxxx)
                # 某些联接基金会把 ETF 放在 "GPDM" 字段里，虽然它不是股票
                for item in data['Datas'][:10]:
                    raw = item['GPDM']
                    is_etf = raw.startswith(('159', '51', '56', '58'))
                    prefix = "sh" if raw.startswith(('6','5')) else ("bj" if raw.startswith(('4','8')) else "sz")
                    stocks.append({"c": f"{prefix}{raw}", "n": item['GPJC'], "raw": raw, "is_etf": is_etf})
        except: pass
        return stocks

    # 2. 网页嗅探 (兜底逻辑)
    def scan_html_for_parent_or_etf(target):
        try:
            # 暴力扫描关联代码
            url = f"http://fundf10.eastmoney.com/jjcc_{target}.html"
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
            # 找所有 fund.eastmoney.com/xxxxxx.html 的链接
            codes = re.findall(r'fund\.eastmoney\.com/(\d{6})\.html', r.text)
            unique_codes = []
            for c in codes:
                if c != target and c not in visited:
                    unique_codes.append(c)
            return unique_codes
        except: return []

    # --- 执行流程 ---

    # Step A: 查自己
    holdings = fetch_data(fund_code)

    # Step B: 决策
    # 如果持仓列表里竟然有 ETF (比如 159732)，说明它是联接基金，必须马上递归那个 ETF
    for h in holdings:
        if h['is_etf']:
            # 发现 ETF！直接抛弃当前层级，去查这个 ETF
            return get_fund_stocks(h['raw'], visited)

    # 如果持仓是空的，或者看起来不对劲（全是债券或空的），找爸爸/关联基金
    if not holdings:
        # 1. 查 Pingzhongdata 找 A 类
        try:
            r_map = requests.get(f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js", timeout=1)
            match = re.search(r'fS_code\s*=\s*["\'](\d+)["\']', r_map.text)
            if match:
                parent = match.group(1)
                if parent != fund_code:
                    return get_fund_stocks(parent, visited)
        except: pass

        # 2. 如果还没有，去页面里扫 ETF 代码
        linked_codes = scan_html_for_parent_or_etf(fund_code)
        # 优先试 ETF 代码
        for lc in linked_codes:
            if lc.startswith(('159', '51')):
                res = get_fund_stocks(lc, visited)
                if res: return res
        # 其次试其他代码 (A类)
        for lc in linked_codes:
            if not lc.startswith(('159', '51')):
                res = get_fund_stocks(lc, visited)
                if res: return res

    # Step C: 查股价 (走到这里说明找到了真正的股票)
    real_stocks = [x for x in holdings if not x.get('is_etf', False)]
    if not real_stocks: return []

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

c_title, c_btn = st.columns([0.75, 0.25])
with c_title:
    st.markdown("##### 🌍 全球行情")
with c_btn:
    if st.button("🔄 刷新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

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

# 🔥 性能优化核心：多线程并发获取所有基金数据 🔥
total_money = 0.0
total_profit = 0.0
final_list = []

if st.session_state.portfolio:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_details_worker, st.session_state.portfolio))
    
    for item in results:
        total_money += item['m']
        total_profit += item['profit_money']
        final_list.append(item)
else:
    final_list = []

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
    
    with st.expander("📊 前十持仓 (智能穿透)"):
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
        code_input = st.text_input("代码", placeholder="例如 014143")
        money = st.number_input("本金", value=10000.0)
        if st.form_submit_button("确认"):
            # 简单的测试一下代码是否有效
            res = requests.get(f"http://fundgz.1234567.com.cn/js/{code_input}.js", timeout=2)
            if res.status_code == 200:
                ls = [x for x in st.session_state.portfolio if x['c'] != code_input]
                ls.append({"c": code_input, "m": money})
                st.session_state.portfolio = ls
                conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(ls), current_user))
                conn.commit()
                st.success(f"已添加")
                st.rerun()
            else: st.error("代码错误")
