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

# 强制 CSS：修复按钮对齐，防止代码块显示
st.markdown("""
<style>
    /* 全局背景 */
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
        border: 1px solid #e0e0e0; margin-bottom: 10px;
    }
    
    /* 修正删除按钮，让它不要太突兀 */
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
</style>
""", unsafe_allow_html=True)

# ================= 2. 数据库 (无需登录) =================
conn = sqlite3.connect('zzl_v25_fixed.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, portfolio TEXT)')
current_user = 'admin'

# ================= 3. 数据获取 (双重数据) =================

@st.cache_data(ttl=30, show_spinner=False)
def get_indices():
    """获取全球行情，防止转圈"""
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
                if curr == 0: curr = last # 休市修正
                res.append({"n": cfg[1], "v": curr, "p": (curr - last) / last * 100})
            except:
                res.append({"n": cfg[1], "v": 0.0, "p": 0.0})
    except:
        return []
    return res

@st.cache_data(ttl=60, show_spinner=False)
def get_details(code):
    """
    同时获取：估值 + 净值 + 状态
    """
    try:
        # 1. 估值
        r_gs = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.5)
        # 2. 净值
        r_jz = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.5)
        
        name = code
        gz_val = 0.0 # 估值涨跌幅
        gz_time = "" # 估值时间
        
        if r_gs.status_code == 200:
            txt = r_gs.text
            if "name" in txt: name = re.search(r'name":"(.*?)"', txt).group(1)
            if "gszzl" in txt: gz_val = float(re.search(r'gszzl":"(.*?)"', txt).group(1))
            if "gztime" in txt: gz_time = re.search(r'gztime":"(.*?)"', txt).group(1)
            
        jz_val = 0.0 # 净值涨跌幅
        jz_date = "" # 净值日期
        
        if r_jz.status_code == 200:
            tds = BeautifulSoup(r_jz.text, 'html.parser').find_all("td")
            if len(tds) > 3:
                jz_date = tds[0].text.strip()
                v_str = tds[3].text.strip().replace("%","")
                jz_val = float(v_str) if v_str else 0.0
                
        # 3. 判定逻辑
        now = datetime.now()
        is_weekend = now.weekday() >= 5 # 周末
        today_str = now.strftime("%Y-%m-%d")
        
        # 决定使用哪个值计算盈亏 (used_rate)
        # 状态文案 (status_txt)
        
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
            "name": name,
            "gz": gz_val,      # 估值(展示用)
            "jz": jz_val,      # 净值(展示用)
            "jz_date": jz_date,
            "used": used_rate, # 计算用
            "status": status_txt,
            "use_jz": is_using_jz # 标记到底用了谁
        }
    except:
        return None

# ================= 4. 页面逻辑 =================

# 1. 顶部大盘
st.markdown("##### 🌍 全球行情")
idx_data = get_indices()
if idx_data:
    # 拼接HTML (不缩进)
    h = '<div class="market-scroll">'
    for d in idx_data:
        c = "t-red" if d['p'] >= 0 else "t-green"
        h += f'<div class="market-card-small"><div class="t-gray">{d["n"]}</div><div class="{c}">{d["v"]:.2f}</div><div class="{c}" style="font-size:10px;">{d["p"]:+.2f}%</div></div>'
    h += '</div>'
    st.markdown(h, unsafe_allow_html=True)
else:
    st.caption("行情加载失败，请刷新")

# 2. 读取持仓
if 'portfolio' not in st.session_state:
    row = conn.execute('SELECT portfolio FROM users WHERE username=?', (current_user,)).fetchone()
    st.session_state.portfolio = json.loads(row[0]) if row else []

# 3. 计算数据
total_money = 0.0
total_profit = 0.0
final_list = []

for p in st.session_state.portfolio:
    info = get_details(p['c'])
    if info:
        total_money += p['m']
        # 核心：根据判定结果计算盈亏
        profit = p['m'] * (info['used'] / 100)
        total_profit += profit
        final_list.append({**p, **info, 'profit_money': profit})

# 4. 总盈亏卡片
bg_cls = "#ff4b4b" if total_profit >= 0 else "#2ecc71"
st.markdown(f"""
<div class="hero-box" style="background:{bg_cls}">
    <div style="opacity:0.9; font-size:14px;">总盈亏 (CNY)</div>
    <div style="font-size:40px; font-weight:bold; margin:5px 0;">{total_profit:+.2f}</div>
    <div style="font-size:12px; opacity:0.8;">持仓本金: {total_money:,.0f}</div>
</div>
""", unsafe_allow_html=True)

# 5. 详细列表 (重点修复：双重显示 + 删除键)
st.markdown("##### 📑 基金明细")

if not final_list:
    st.info("请在左侧添加基金")

for item in final_list:
    # --- 布局：第一行 标题 + 删除键 ---
    c1, c2 = st.columns([0.85, 0.15]) # 严格比例
    
    with c1:
        # 显示名字和代码
        st.markdown(f"**{item['name']}** <span style='color:#ccc; font-size:12px'>{item['c']}</span>", unsafe_allow_html=True)
    
    with c2:
        # 删除按钮，紧跟在名字右边
        if st.button("🗑", key=f"del_{item['c']}"):
            new_p = [x for x in st.session_state.portfolio if x['c'] != item['c']]
            st.session_state.portfolio = new_p
            conn.execute('UPDATE users SET portfolio=? WHERE username=?', (json.dumps(new_p), current_user))
            conn.commit()
            st.rerun()

    # --- 数据显示区域 (HTML卡片) ---
    # 根据使用的是估值还是净值，高亮对应的数字
    color_gz = "black"
    color_jz = "black"
    wt_gz = "normal"
    wt_jz = "normal"
    
    # 谁生效，谁变粗变大
    if item['use_jz']:
        color_jz = "#e74c3c" if item['jz'] >= 0 else "#2ecc71"
        wt_jz = "bold"
        color_gz = "#999" # 估值变灰
    else:
        color_gz = "#e74c3c" if item['gz'] >= 0 else "#2ecc71"
        wt_gz = "bold"
        color_jz = "#999" # 净值变灰
    
    profit_color = "#e74c3c" if item['profit_money'] >= 0 else "#2ecc71"

    # 卡片 HTML (无缩进，双列显示)
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
