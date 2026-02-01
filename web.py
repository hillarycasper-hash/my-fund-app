import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# ================= 🎨 UI 设定 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: -apple-system, sans-serif !important; }
    .stApp { background: #f2f2f7; }
    .hero-card { background: #1c1c1e; color: white; padding: 25px 20px; border-radius: 24px; text-align: center; margin-bottom: 20px; }
    .fund-card { background: white; padding: 15px; border-radius: 20px; margin-bottom: 12px; border: 1px solid #e5e5ea; }
    .num-main { font-size: 24px; font-weight: 800; line-height: 1.2; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="global_refresh")

# ================= 🧠 核心：数据存取优化 (修复报错关键) =================

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

def storage_manager(data_to_save=None):
    mode = "SAVE" if data_to_save is not None else "LOAD"
    js_code = f"""
    <script>
    const dbName = "ZZL_DB_V2";
    const request = indexedDB.open(dbName, 1);
    request.onupgradeneeded = (e) => {{ e.target.result.createObjectStore("settings"); }};
    request.onsuccess = (e) => {{
        const db = e.target.result;
        const store = db.transaction("settings", "readwrite").objectStore("settings");
        if ("{mode}" === "SAVE") {{
            store.put({json.dumps(data_to_save)}, "portfolio");
        }} else {{
            const getReq = store.get("portfolio");
            getReq.onsuccess = () => {{
                if (getReq.result) {{
                    window.parent.postMessage({{type: 'streamlit:setComponentValue', value: getReq.result}}, '*');
                }}
            }};
        }}
    }};
    </script>
    """
    return components.html(js_code, height=0)

# 执行自动读取
db_res = storage_manager()
# 关键修复：只有当 JS 传回了有效数据且当前状态为空时才更新
if db_res is not None and not st.session_state.portfolio:
    st.session_state.portfolio = db_res
    st.rerun()

# ================= 🔧 爬虫逻辑 (保持稳定) =================

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
            h_data = [(r.find_all("td")[1].text.strip(), float(r.find_all("td")[-3].text.strip().replace("%",""))) for r in soup.find_all("tr")[1:]]
            with ThreadPoolExecutor(max_workers=5) as exe:
                prices = list(exe.map(get_sina_price, [d[0] for d in h_data]))
            return (sum(p[0]*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data)) * f, (prices[0][1] if prices else "")
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
    except: return f"基金-{code}", 0.0, ""

# ================= 📊 主界面 =================

with st.sidebar:
    st.markdown("### 📥 持仓管理")
    with st.form("add_fund", clear_on_submit=True):
        c = st.text_input("基金代码", placeholder="013279")
        m = st.number_input("持有本金", value=1000.0)
        if st.form_submit_button("确认添加", use_container_width=True):
            if c:
                st.session_state.portfolio.append({"c": c, "m": m})
                storage_manager(st.session_state.portfolio) # 存盘
                st.rerun()

    if st.button("🗑️ 清空所有数据", use_container_width=True):
        st.session_state.portfolio = []
        storage_manager([]) # 清空存盘
        st.rerun()

# --- 🚀 核心显示逻辑 (加入容错保护) ---
if st.session_state.portfolio:
    # 再次安全校验：确保列表中每个元素都有 'm' 这个 key
    valid_portfolio = [i for i in st.session_state.portfolio if isinstance(i, dict) and 'm' in i]
    
    if not valid_portfolio:
        st.info("🔄 正在从本地硬盘唤醒持仓数据，请稍候...")
    else:
        is_weekend = datetime.now().weekday() >= 5
        total_m = sum(i['m'] for i in valid_portfolio)
        mixed_p = 0.0
        hero_placeholder = st.empty()
        
        for idx, i in enumerate(valid_portfolio):
            name, l_r, l_d = get_info(i['c'])
            r_r, s_d = calc_realtime(i['c'], name)
            eff_r = l_r if is_weekend else (l_r if l_d == datetime.now().strftime('%Y-%m-%d') else r_r)
            mixed_p += i['m'] * (eff_r / 100)
            
            with st.container():
                c1, c2 = st.columns([0.88, 0.12])
                c1.markdown(f'<div style="font-size:15px; font-weight:700;">💠 {name}</div>', unsafe_allow_html=True)
                if c2.button("✕", key=f"del_{idx}"):
                    st.session_state.portfolio.pop(idx)
                    storage_manager(st.session_state.portfolio) # 更新存盘
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
    st.markdown('<div class="hero-card" style="background:white; color:#1c1c1e; border:1px solid #e5e5ea;"><h2>Hello.</h2><p>请在侧边栏录入基金代码或等待数据加载</p></div>', unsafe_allow_html=True)
