import streamlit as st
import requests
import sqlite3
import hashlib
import json
import re

# ================= 🎨 全局样式美化 =================
st.set_page_config(page_title="涨涨乐Pro-会员登录", page_icon="📈", layout="centered")

def local_css():
    st.markdown("""
        <style>
        /* 隐藏Streamlit默认页边距 */
        .block-container { padding-top: 2rem; }
        
        /* 渐变背景卡片 */
        .login-card {
            background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
            padding: 2rem;
            border-radius: 20px;
            color: white;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            margin-bottom: 2rem;
        }
        
        /* 登录标题样式 */
        .login-header {
            text-align: center;
            margin-bottom: 1.5rem;
        }
        .login-header h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: -webkit-linear-gradient(#fff, #999);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        /* 输入框样式微调 */
        .stTextInput input {
            border-radius: 10px !important;
            border: 1px solid #444 !important;
            background-color: #f9f9f9 !important;
        }
        
        /* 选项卡样式优化 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
            justify-content: center;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            border-radius: 10px;
            background-color: transparent;
        }
        
        /* 成功/错误信息位置优化 */
        .stAlert { border-radius: 12px; }
        </style>
    """, unsafe_allow_html=True)

local_css()

# ================= 🗄️ 数据库逻辑 (保持不变) =================
def init_db():
    conn = sqlite3.connect('users_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, portfolio TEXT)')
    conn.commit()
    return conn

db_conn = init_db()

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return make_hashes(password) == hashed_text

# ================= 🔐 登录状态管理 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# ================= 📺 界面渲染 =================

if not st.session_state.logged_in:
    # 1. 顶部 LOGO/标题区
    st.markdown("""
        <div class="login-header">
            <h1>涨涨乐 <span>Pro</span></h1>
            <p style="color: #888;">专业基金收益监控 · 资产永久同步</p>
        </div>
    """, unsafe_allow_html=True)

    # 2. 居中的登录/注册卡片
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        tab1, tab2 = st.tabs(["👋 欢迎回来", "✨ 开启新账户"])
        
        with tab1:
            st.markdown('<div style="height: 15px;"></div>', unsafe_allow_html=True)
            with st.container():
                user = st.text_input("用户名", placeholder="输入您的用户名", key="login_user")
                pwd = st.text_input("密码", type="password", placeholder="输入您的密码", key="login_pwd")
                st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
                if st.button("安全登录", use_container_width=True, type="primary"):
                    c = db_conn.cursor()
                    c.execute('SELECT password, portfolio FROM users WHERE username =?', (user,))
                    data = c.fetchone()
                    if data and check_hashes(pwd, data[0]):
                        st.session_state.logged_in = True
                        st.session_state.username = user
                        st.session_state.portfolio = json.loads(data[1])
                        st.success("登录成功，正在跳转...")
                        st.rerun()
                    else:
                        st.error("❌ 用户名或密码错误")

        with tab2:
            st.markdown('<div style="height: 15px;"></div>', unsafe_allow_html=True)
            with st.container():
                new_user = st.text_input("用户名", placeholder="建议使用手机号或常用名", key="reg_user")
                new_pwd = st.text_input("密码", type="password", placeholder="设置 6 位以上密码", key="reg_pwd")
                conf_pwd = st.text_input("确认密码", type="password", placeholder="再次输入密码", key="reg_pwd_conf")
                
                st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
                if st.button("立即创建账号", use_container_width=True):
                    if len(new_user) < 2:
                        st.warning("⚠️ 用户名太短了")
                    elif new_pwd != conf_pwd:
                        st.warning("⚠️ 两次输入的密码不一致")
                    elif len(new_pwd) < 6:
                        st.warning("⚠️ 为了安全，密码至少需要6位")
                    else:
                        c = db_conn.cursor()
                        try:
                            c.execute('INSERT INTO users(username, password, portfolio) VALUES (?,?,?)', 
                                      (new_user, make_hashes(new_pwd), "[]"))
                            db_conn.commit()
                            st.balloons()
                            st.success("✅ 注册成功！现在请切换到登录标签进行登录。")
                        except:
                            st.error("❌ 该用户名已被占用")

    st.markdown("""
        <div style="text-align:center; margin-top: 3rem; color: #bbb; font-size: 0.8rem;">
            数据存储于加密数据库，我们不会泄露您的任何持仓信息。
        </div>
    """, unsafe_allow_html=True)

else:
    # --- 登录后的主程序界面 (直接复用你之前的业务逻辑) ---
    st.title(f"📈 欢迎，{st.session_state.username}")
    if st.sidebar.button("退出登录"):
        st.session_state.logged_in = False
        st.rerun()
    st.write("这里继续放你之前的基金详情展示代码...")
