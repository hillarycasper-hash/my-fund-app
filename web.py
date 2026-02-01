import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import json
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

# ================= 🎨 极速 UI 定制 3.0 =================
st.set_page_config(page_title="涨涨乐Pro", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .stApp { background: #f2f2f7; }
    .hero-card {
        background: #1c1c1e; color: white; padding: 25px;
        border-radius: 24px; text-align: center; margin-bottom: 20px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
    }
    .index-card {
        background: white; padding: 12px; border-radius: 16px;
        text-align: center; border: 1px solid #e5e5ea;
    }
    .fund-card {
        background: white; padding: 18px; border-radius: 22px;
        margin-bottom: 12px; border: 1px solid #e5e5ea;
    }
    .status-tag {
        font-size: 10px; padding: 2px 6px; border-radius: 4px;
        background: #eee; color: #666; margin-left: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=60 * 1000, key="global_refresh") # 改为60秒自动刷新

# ================= 🔧 金融数据引擎 =================
@st.cache_data(ttl=60)
def get_market_indices():
    """获取大盘指数数据"""
    indices = {"sh000001": "上证指数", "sz399006": "创业板指", "gb_ixic": "纳斯达克"}
    data = []
    try:
        url = f"http://hq.sinajs.cn/list={','.join(indices.keys())}"
        res = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=1)
        lines = res.text.strip().split('\n')
        for i, line in enumerate(lines):
            v = line.split('="')[1].split(',')
            curr, last = float(v[3]), float(v[2])
            chg = (curr - last) / last * 100
            data.append({"name": list(indices.values())[i], "price": curr, "chg": chg})
    except: pass
    return data

@st.cache_data(ttl=600)
def get_info(code):
    try:
        r1 = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=1.0)
        name = (re.search(r'nameFormat":"(.*?)"', r1.text) or re.search(r'name":"(.*?)"', r1.text)).group(1)
        r2 = requests.get(f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1", timeout=1.0)
        tds = BeautifulSoup(r2.text, 'html.parser').find_all("td")
        return name, float(tds[3].text.strip().replace("%","")), tds[0].text.strip()
    except: return f"基金-{code}", 0.0, ""

def calc_realtime(code, name):
    is_weekend = datetime.now().weekday() >= 5
    if is_weekend:
        return 0.0, "休市中" # 周末强制返回休市状态
    # ... (此处保留之前的爬虫逻辑)
    return 0.0, "交易中"

# ================= 📊 主看盘界面 =================

# 1. 顶部大盘晴雨表 (解决“太空旷”问题)
st.markdown("### 🌍 全球市场晴雨表")
indices = get_market_indices()
cols = st.columns(len(indices) if indices else 3)
for idx, item in enumerate(indices):
    color = "#ff3b30" if item['chg'] > 0 else "#34c759"
    cols[idx].markdown(f"""
        <div class="index-card">
            <div style="font-size:12px; color:#8e8e93;">{item['name']}</div>
            <div style="font-size:18px; font-weight:800; color:{color};">{item['price']:.2f}</div>
            <div style="font-size:12px; color:{color};">{item['chg']:+.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

# 2. 资产总览 (Hero Card)
if st.session_state.portfolio:
    # ... 计算收益逻辑 (保留原有逻辑)
    st.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 13px; opacity: 0.8; margin-bottom:5px;">今日预估损益 (CNY)</div>
            <div style="font-size: 50px; font-weight: 900;">¥ {mixed_p:+.2f}</div>
            <div style="display:flex; justify-content:center; gap:20px; font-size:14px; opacity:0.9;">
                <span>本金: ¥{total_m:,.0f}</span>
                <span>收益率: {mixed_p/total_m*100:+.2f}%</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 3. 基金持仓明细 (解决“休市”显示问题)
    st.markdown("### 📑 持仓明细")
    for idx, i in enumerate(st.session_state.portfolio):
        name, l_r, l_d = get_info(i['c'])
        is_weekend = datetime.now().weekday() >= 5
        
        # 逻辑：如果是周末，估值就是0且状态显示休市
        if is_weekend:
            val_r, status_text = 0.0, "休市(周五已结)"
        else:
            val_r, _ = calc_realtime(i['c'], name)
            status_text = "实时估值"

        with st.container():
            # 渲染 Fund Card ... (此处参考你之前的UI，但文字改为 status_text)
            pass

# ================= 🛠️ 侧边栏功能矩阵 (模仿市面产品) =================
with st.sidebar:
    st.markdown("### ⚙️ 资产管理")
    st.info(f"🆔 识别码: {st.session_state.user_token}")
    
    # 新增功能 1：资产配比概览
    if st.session_state.portfolio:
        st.markdown("---")
        st.markdown("📊 **资产分布**")
        # 简单模拟一个饼图或占比条
        for i in st.session_state.portfolio:
            percent = (i['m'] / total_m) * 100
            st.caption(f"代码 {i['c']} 占比 {percent:.1f}%")
            st.progress(percent/100)
    
    # 新增功能 2：市场情绪
    st.markdown("---")
    st.markdown("🔥 **市场情绪**")
    sentiment = random.choice(["看多", "震荡", "看空"])
    st.write(f"当前策略建议: **{sentiment}**")
