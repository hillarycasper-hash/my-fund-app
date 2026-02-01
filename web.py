import streamlit as st
import hashlib
import sqlite3
import json

# ================= 🎨 顶级视觉引擎 (CSS 重写) =================
def apply_pro_style():
    st.markdown("""
        <style>
        /* 1. 隐藏多余元素 */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* 2. 全局背景：深空灰渐变 */
        .stApp {
            background: radial-gradient(circle at top right, #2c2c2e, #1c1c1e, #000000);
        }

        /* 3. 登录卡片：毛玻璃效果 */
        div[data-testid="stVerticalBlock"] > div:has(.login-box) {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 30px;
            padding: 40px 30px;
            box-shadow: 0 25px 50px rgba(0,0,0,0.5);
        }

        /* 4. 标题艺术字 */
        .glow-text {
            text-align: center;
            font-family: 'Inter', sans-serif;
            background: linear-gradient(to bottom right, #ffffff 30%, #666);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 900;
            letter-spacing: -1px;
            margin-bottom: 0px;
        }

        /* 5. 输入框美化 */
        .stTextInput > div > div > input {
            background-color: rgba(255, 255, 255, 0.05) !important;
            color: white !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            border-radius: 12px !important;
            height: 48px;
        }
        
        /* 6. 按钮：黑金流光效果 */
        .stButton > button {
            background: linear-gradient(90deg, #d4af37, #f9d976);
            color: #1c1c1e !important;
            font-weight: 700 !important;
            border: none !important;
            border-radius: 12px !important;
            height: 48px;
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(212, 175, 55, 0.4);
        }

        /* 7. Tabs 样式优化 */
        .stTabs [data-baseweb="tab-list"] {
            background-color: transparent;
            justify-content: center;
        }
        .stTabs [data-baseweb="tab"] {
            color: #888 !important;
        }
        .stTabs [aria-selected="true"] {
            color: #d4af37 !important;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)

# ================= 🔐 登录界面渲染逻辑 =================

def show_login_page():
    apply_pro_style()
    
    # 顶部留白
    st.write("<div style='height: 8vh'></div>", unsafe_allow_html=True)
    
    # 整个卡片容器
    with st.container():
        st.markdown('<div class="login-box">', unsafe_allow_html=True)
        
        # 标志性标题
        st.markdown('<h1 class="glow-text" style="font-size: 3rem;">ZZL</h1>', unsafe_allow_html=True)
        st.markdown('<p style="text-align:center; color:#888; margin-bottom:2rem;">涨涨乐 Pro · 资产管理系统</p>', unsafe_allow_html=True)

        tab_login, tab_reg = st.tabs(["安全登录", "新用户注册"])
        
        with tab_login:
            st.write("<div style='height: 20px'></div>", unsafe_allow_html=True)
            u = st.text_input("USER", placeholder="输入用户名", key="l_u", label_visibility="collapsed")
            p = st.text_input("PASS", type="password", placeholder="输入密码", key="l_p", label_visibility="collapsed")
            st.write("<div style='height: 10px'></div>", unsafe_allow_html=True)
            if st.button("进入系统", use_container_width=True):
                # 你的数据库校验逻辑
                cur = db_conn.cursor()
                cur.execute('SELECT password, portfolio FROM users WHERE username=?', (u,))
                res = cur.fetchone()
                if res and check_hashes(p, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.session_state.portfolio = json.loads(res[1])
                    st.rerun()
                else:
                    st.error("验证失败，请重试")

        with tab_reg:
            st.write("<div style='height: 20px'></div>", unsafe_allow_html=True)
            nu = st.text_input("SET USER", placeholder="设置新用户名", key="r_u", label_visibility="collapsed")
            np = st.text_input("SET PASS", type="password", placeholder="设置新密码", key="r_p", label_visibility="collapsed")
            st.write("<div style='height: 10px'></div>", unsafe_allow_html=True)
            if st.button("立即开启", use_container_width=True):
                # 你的数据库插入逻辑
                try:
                    cur = db_conn.cursor()
                    cur.execute('INSERT INTO users VALUES (?,?,?)', (nu, make_hashes(np), "[]"))
                    db_conn.commit()
                    st.success("注册成功！请切换登录")
                except:
                    st.error("该用户名已存在")
        
        st.markdown('</div>', unsafe_allow_html=True)

# ================= 🏗️ 程序入口 =================

if not st.session_state.get('logged_in', False):
    show_login_page()
else:
    # 登录后的主程序界面...
    st.write(f"欢迎回来，{st.session_state.username}")
    # 这里放你原来的看板代码...
