import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# ================= 🎨 UI 极致优化 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: -apple-system, sans-serif !important; }
    .stApp { background: #f2f2f7; }
    .hero-card { background: linear-gradient(135deg, #1c1c1e 0%, #3a3a3c 100%); color: white; padding: 25px 20px; border-radius: 24px; text-align: center; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.15); }
    .fund-card { background: white; padding: 16px; border-radius: 20px; margin-bottom: 12px; border: 1px solid #e5e5ea; }
    .num-main { font-size: 24px; font-weight: 800; line-height: 1.2; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="global_refresh")

# ================= 🧠 核心：超稳健存取逻辑 =================

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

def storage_manager(data_to_save=None):
    mode = "SAVE" if data_to_save is not None else "LOAD"
    # 使用唯一的 DB 名字防止冲突
    js_code = f"""
    <script>
    const dbName = "ZZL_FINAL_DB";
    const request = indexedDB.open(dbName, 2);
    request.onupgradeneeded = (e) => {{ e.target.result.createObjectStore("data"); }};
    request.onsuccess = (e) => {{
        const db = e.target.result;
        const tx = db.transaction("data", "readwrite");
        const store = tx.objectStore("data");
        if ("{mode}" === "SAVE") {{
            store.put({json.dumps(data_to_save)}, "portfolio");
        }} else {{
            const getReq = store.get("portfolio");
            getReq.onsuccess = () => {{
                if (getReq.result && Array.isArray(getReq.result)) {{
                    window.parent.postMessage({{type: 'streamlit:setComponentValue', value: getReq.result}}, '*');
                }}
            }};
        }}
    }};
    </script>
    """
    return components.html(js_code, height=0)

# 自动尝试加载
db_res = storage_manager()

# 强力校验函数：确保数据是我们要的格式
def get_clean_portfolio(raw_data):
    if not raw_data or not isinstance(raw_data, list):
        return []
    clean = []
    for item in raw_data:
        # 严格检查：必须是字典，且包含 'c' 和 'm'
        if isinstance(item, dict) and 'c' in item and 'm' in item:
            clean.append(item)
    return clean

if db_res is not None:
    loaded = get_clean_portfolio(db_res)
    if loaded and not st.session_state.portfolio:
        st.session_state.portfolio = loaded
        st.rerun()

# ================= 🔧 爬虫逻辑 (防死锁版) =================

@st.cache_data(ttl=600)
def get_sina_price(code):
    prefix = "sh" if code.startswith(('6', '5', '11')) else "sz" if code.startswith(('0', '3', '1', '15')) else "rt_hk" if len(code)==5 else ""
    if not prefix: return 0.0, ""
    try:
        res = requests.get(f"http://hq.sinajs.cn/list={prefix}{code}", headers={'Referer': 'https://finance.sina.com.cn'}, timeout=0.8)
        v = res.text.split('="')[1].strip('";').split(',')
        curr, last = (float(v[6]), float(v[3])) if "hk" in prefix else (float(v[3]), float(v[2]))
        return ((curr - last) / last) * 100 if last > 0 else 0.0, (v[-4] if "hk" not in prefix else v[-2])
    except: return 0.0, ""

def calc_realtime(code, name):
    f = 0.99 if any(x in name for x in ["指数", "ETF", "纳指", "标普"]) else 0.92
    try:
        res = requests.get(f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10", timeout=1.2)
        match = re.search(r'content:"(.*?)"', res.text)
        if match:
            soup = BeautifulSoup(match.group(1), 'html.parser')
            rows = soup.find_all("tr")[1:]
            if not rows: return 0.0, ""
            h_data = [(r.find_all("td")[1].text.strip(), float(r.find_all("td")[-3].text.strip().replace("%",""))) for r in rows]
            with ThreadPoolExecutor(max_workers=5) as exe:
                prices = list(exe.map(get_sina_price, [d[0] for d in h_data]))
            return (sum(p[0]*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data)) * f, prices[0][1]
    except: pass
    return 0.0, ""

@st.cache_data(ttl=3600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = re.search(r'name":"(.*?)"', r1.text).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"代码{code}", 0.0, ""

# ================= 📊 界面 =================

with st.sidebar:
    st.markdown("### 📥 持仓管理")
    with st.form("add_fund", clear_on_submit=True):
        c = st.text_input("代码", placeholder="013279")
        m = st.number_input("本金", value=1000.0)
        if st.form_submit_button("添加", use_container_width=True):
            if c:
                st.session_state.portfolio.append({"c": c, "m": m})
                storage_manager(st.session_state.portfolio)
                st.rerun()

    if st.button("🗑️ 清空所有数据", use_container_width=True):
        st.session_state.portfolio = []
        storage_manager([])
        st.rerun()
    
    st.markdown("---")
    if st.button("🔄 手动同步历史数据", use_container_width=True):
        # 强制触发一次读取
        st.rerun()

# --- 核心显示逻辑 ---
# 使用清洗后的数据，彻底规避 TypeError
current_data = get_clean_portfolio(st.session_state.portfolio)

if current_data:
    is_weekend = datetime.now().weekday() >= 5
    total_m = sum(i['m'] for i in current_data)
    mixed_p = 0.0
    
    hero_placeholder = st.empty()
    
    for idx, i in enumerate(current_data):
        name, l_r, l_d = get_info(i['c'])
        r_r, s_d = calc_realtime(i['c'], name)
        eff_r = l_r if is_weekend else (l_r if l_d == datetime.now().strftime('%Y-%m-%d') else r_r)
        mixed_p += i['m'] * (eff_r / 100)
        
        with st.container():
            c1, c2 = st.columns([0.88, 0.12])
            c1.markdown(f'<div style="font-size:15px; font-weight:700;">💠 {name}</div>', unsafe_allow_html=True)
            if c2.button("✕", key=f"del_{idx}_{i['c']}"):
                st.session_state.portfolio.pop(idx)
                storage_manager(st.session_state.portfolio)
                st.rerun()
            
            st.markdown(f"""
                <div class="fund-card" style="margin-top:-10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div style="flex:1;">
                            <div style="font-size:10px; color:#8e8e93;">实时估值 [{s_d or '获取中'}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if r_r>0 else '#34c759'};">{r_r:+.2f}%</div>
                            <div style="font-size:12px; font-weight:700; color:{'#ff3b30' if r_r>0 else '#34c759'};">¥ {i['m']*r_r/100:+.2f}</div>
                        </div>
                        <div style="flex:1; border-left:1px solid #f2f2f7; padding-left:12px;">
                            <div style="font-size:10px; color:#8e8e93;">官方昨结 [{l_d}]</div>
                            <div class="num-main" style="color:{'#ff3b30' if l_r>0 else '#34c759'};">{l_r:+.2f}%</div>
                            <div style="font-size:12px; font-weight:700; color:{'#ff3b30' if l_r>0 else '#34c759'};">¥ {i['m']*l_r/100:+.2f}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    hero_placeholder.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 52px; font-weight: 900; line-height:1;">¥ {mixed_p:+.2f}</div>
            <div style="font-size: 14px; opacity: 0.8; margin-top:10px;">本金合计 ¥{total_m:,.0f} | 预估收益率 {(mixed_p/total_m*100):+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)
else:
    # 引导界面
    st.markdown("""
        <div class="hero-card" style="background:white; color:#1c1c1e; border:1px solid #e5e5ea;">
            <h2>你好，欢迎使用</h2>
            <p style="color:#8e8e93;">数据加载中或请在侧边栏录入资产</p>
        </div>
    """, unsafe_allow_html=True)
