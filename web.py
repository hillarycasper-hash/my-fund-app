import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import hashlib
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 全局 UI 样式控制 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

def apply_custom_style():
    st.markdown("""
        <style>
        .stApp { background: #f2f2f7; }
        /* 登录页专用样式 */
        .login-header { text-align: center; margin-bottom: 2rem; padding-top: 2rem; }
        .login-header h1 { font-size: 2.5rem; font-weight: 800; color: #1c1c1e; }
        
        /* 看板专用样式 */
        .hero-card { 
            background: linear-gradient(135deg, #1c1c1e 0%, #3a3a3c 100%); 
            color: white; padding: 25px; border-radius: 24px; 
            text-align: center; margin-bottom: 20px; box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        .fund-card { 
            background: white; padding: 18px; border-radius: 20px; 
            margin-bottom: 12px; border: 1px solid #e5e5ea; 
        }
        .num-main { font-size: 26px; font-weight: 800; line-height: 1.1; }
        </style>
    """, unsafe_allow_html=True)

apply_custom_style()
st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ================= 🗄️ 数据库核心逻辑 =================
def init_db():
    conn = sqlite3.connect('zzl_pro_v5.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, portfolio TEXT)')
    conn.commit()
    return conn

db_conn = init_db()

def make_hashes(pwd): return hashlib.sha256(str.encode(pwd)).hexdigest()
def check_hashes(pwd, hashed): return make_hashes(pwd) == hashed

# ================= 🔧 爬虫与计算引擎 =================
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

def calc_realtime_valuation(code, name):
    f = 0.99 if any(x in name for x in ["指数", "ETF", "纳指", "标普"]) else 0.92
    try:
        res = requests.get(f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10", timeout=1.2)
        match = re.search(r'content:"(.*?)"', res.text)
        if match:
            soup = BeautifulSoup(match.group(1), 'html.parser')
            rows = soup.find_all("tr")[1:]
            h_data = [(r.find_all("td")[1].text.strip(), float(r.find_all("td")[-3].text.strip().replace("%",""))) for r in rows]
            with ThreadPoolExecutor(max_workers=5) as exe:
                prices = list(exe.map(get_sina_price, [d[0] for d in h_data]))
            return (sum(p[0]*h[1] for p, h in zip(prices, h_data)) / sum(h[1] for h in h_data)) * f, (prices[0][1] if prices else "")
    except: pass
    return 0.0, ""

@st.cache_data(ttl=3600)
def get_fund_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = re.search(r'name":"(.*?)"', r1.text).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金{code}", 0.0, "未知"

# ================= 🔐 登录状态检查 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# ================= 📺 界面分流渲染 =================

if not st.session_state.logged_in:
    # --- 登录注册界面 ---
    st.markdown('<div class="login-header"><h1>涨涨乐 <span>Pro</span></h1><p>数据永久保存 · 会员专属看盘</p></div>', unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        t1, t2 = st.tabs(["🔑 账号登录", "✨ 注册新账户"])
        with t1:
            u = st.text_input("用户名", key="l_u")
            p = st.text_input("密码", type="password", key="l_p")
            if st.button("立即进入", use_container_width=True, type="primary"):
                cur = db_conn.cursor()
                cur.execute('SELECT password, portfolio FROM users WHERE username=?', (u,))
                res = cur.fetchone()
                if res and check_hashes(p, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.session_state.portfolio = json.loads(res[1])
                    st.rerun()
                else: st.error("账号或密码不对哦")
        with t2:
            nu = st.text_input("设置用户名", key="r_u")
            np = st.text_input("设置密码", type="password", key="r_p")
            if st.button("创建并登录", use_container_width=True):
                try:
                    cur = db_conn.cursor()
                    cur.execute('INSERT INTO users VALUES (?,?,?)', (nu, make_hashes(np), "[]"))
                    db_conn.commit()
                    st.success("注册成功！请点击登录页进入")
                except: st.error("换个名字吧，这个被人占用了")
else:
    # --- 登录后的专业看板 ---
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.username}")
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
        st.markdown("---")
        with st.form("add_fund", clear_on_submit=True):
            new_c = st.text_input("基金代码", placeholder="如: 013279")
            new_m = st.number_input("持有本本金", value=10000.0)
            if st.form_submit_button("确认添加", use_container_width=True):
                if new_c:
                    st.session_state.portfolio.append({"c": new_c, "m": new_m})
                    # 同步到数据库
                    cur = db_conn.cursor()
                    cur.execute('UPDATE users SET portfolio=? WHERE username=?', 
                                (json.dumps(st.session_state.portfolio), st.session_state.username))
                    db_conn.commit()
                    st.rerun()
        if st.button("🗑️ 清空所有持仓", use_container_width=True):
            st.session_state.portfolio = []
            cur = db_conn.cursor()
            cur.execute('UPDATE users SET portfolio=? WHERE username=?', ("[]", st.session_state.username))
            db_conn.commit()
            st.rerun()

    # 主看板显示
    if st.session_state.portfolio:
        is_weekend = datetime.now().weekday() >= 5
        total_m = sum(i['m'] for i in st.session_state.portfolio)
        mixed_profit = 0.0
        hero_placeholder = st.empty()
        
        for idx, i in enumerate(st.session_state.portfolio):
            name, l_r, l_d = get_fund_info(i['c'])
            r_r, s_d = calc_realtime_valuation(i['c'], name)
            # 自动切换结算模式
            eff_r = l_r if is_weekend else (l_r if l_d == datetime.now().strftime('%Y-%m-%d') else r_r)
            mixed_profit += i['m'] * (eff_r / 100)
            
            with st.container():
                c1, c2 = st.columns([0.9, 0.1])
                c1.markdown(f'**💠 {name}** ({i["c"]})')
                if c2.button("✕", key=f"del_{idx}"):
                    st.session_state.portfolio.pop(idx)
                    cur = db_conn.cursor()
                    cur.execute('UPDATE users SET portfolio=? WHERE username=?', 
                                (json.dumps(st.session_state.portfolio), st.session_state.username))
                    db_conn.commit()
                    st.rerun()
                
                st.markdown(f"""
                    <div class="fund-card">
                        <div style="display: flex; justify-content: space-between;">
                            <div style="flex:1;">
                                <div style="font-size:10px; color:#8e8e93;">实时估值 [{s_d or '休市'}]</div>
                                <div class="num-main" style="color:{'#ff3b30' if r_r>0 else '#34c759'};">{r_r:+.2f}%</div>
                                <div style="font-size:13px; font-weight:700; color:{'#ff3b30' if r_r>0 else '#34c759'};">¥ {i['m']*r_r/100:+.2f}</div>
                            </div>
                            <div style="flex:1; border-left:1px solid #f2f2f7; padding-left:15px;">
                                <div style="font-size:10px; color:#8e8e93;">官方收盘 [{l_d}]</div>
                                <div class="num-main" style="color:{'#ff3b30' if l_r>0 else '#34c759'};">{l_r:+.2f}%</div>
                                <div style="font-size:13px; font-weight:700; color:{'#ff3b30' if l_r>0 else '#34c759'};">¥ {i['m']*l_r/100:+.2f}</div>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

        hero_placeholder.markdown(f"""
            <div class="hero-card">
                <div style="font-size: 14px; opacity: 0.8; margin-bottom:5px;">当前账户预估总收益</div>
                <div style="font-size: 50px; font-weight: 900; line-height:1;">¥ {mixed_profit:+.2f}</div>
                <div style="font-size: 13px; margin-top:10px; opacity: 0.9;">本金合计 ¥{total_m:,.0f} | 整体收益率 {(mixed_profit/total_m*100):+.2f}%</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div class="hero-card" style="background:white; color:#1c1c1e; border:1px solid #e5e5ea;">
                <h2>欢迎回来</h2>
                <p>账户当前为空，请在侧边栏添加基金开始监控</p>
            </div>
        """, unsafe_allow_html=True)
