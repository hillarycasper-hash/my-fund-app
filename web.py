import streamlit as st
import hashlib
import sqlite3
import json

# ================= 🎨 视觉引擎：深度定制黑金 UI =================
def apply_pro_style():
    st.markdown("""
        <style>
        /* 隐藏 Streamlit 默认的装饰线和空白 */
        [data-testid="stDecoration"] {display: none;}
        [data-testid="stHeader"] {background: rgba(0,0,0,0);}
        
        /* 全局背景 */
        .stApp {
            background: #0e0e0e;
            background-image: radial-gradient(circle at 50% -20%, #2c2c2e 0%, #0e0e0e 80%);
        }

        /* 修复输入框文字看不见的问题 */
        .stTextInput input {
            color: #ffffff !important; /* 文字纯白 */
            background-color: rgba(255, 255, 255, 0.08) !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 12px !important;
            padding: 10px 15px !important;
            caret-color: #d4af37 !important; /* 光标金色 */
        }
        
        /* 输入框聚焦效果 */
        .stTextInput input:focus {
            border-color: #d4af37 !important;
            box-shadow: 0 0 0 1px #d4af37 !important;
        }

        /* 登录卡片容器：去掉那个多余的框 */
        .login-container {
            max-width: 400px;
            margin: 0 auto;
            padding: 2rem 1.5rem;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 28px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(15px);
            text-align: center;
        }

        /* ZZL Logo 艺术化 */
        .logo-font {
            font-size: 4.5rem;
            font-weight: 900;
            background: linear-gradient(135deg, #fff 0%, #d4af37 50%, #8a6d3b 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0px;
            line-height: 1;
            filter: drop-shadow(0 5px 15px rgba(212,175,55,0.2));
        }

        /* 按钮样式强化 */
        .stButton > button {
            width: 100%;
            background: linear-gradient(90deg, #d4af37, #f9d976) !important;
            color: #000 !important;
            border: none !important;
            font-weight: 800 !important;
            font-size: 1rem !important;
            padding: 0.6rem !important;
            border-radius: 14px !important;
            box-shadow: 0 4px 15px rgba(212,175,55,0.3) !important;
        }
        </style>
    """, unsafe_allow_html=True)

# ================= 🔐 交互逻辑：解决注册 bug =================

def show_login_page():
    apply_pro_style()
    
    # 居中布局
    st.write("<div style='height: 10vh'></div>", unsafe_allow_html=True)
    
    # 使用自定义容器开始绘制
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<h1 class="logo-font">ZZL</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#666; font-size:0.9rem; margin-bottom:2rem;">ZZL PRO · 资产管理系统</p>', unsafe_allow_html=True)

    tab_login, tab_reg = st.tabs(["安全登录", "新用户注册"])
    
    with tab_login:
        st.write("<div style='height: 20px'></div>", unsafe_allow_html=True)
        u = st.text_input("用户名", placeholder="USERNAME", key="l_u", label_visibility="collapsed")
        p = st.text_input("密码", type="password", placeholder="PASSWORD", key="l_p", label_visibility="collapsed")
        
        if st.button("进入系统", key="btn_login"):
            if u and p:
                cur = db_conn.cursor()
                cur.execute('SELECT password, portfolio FROM users WHERE username=?', (u,))
                res = cur.fetchone()
                if res and check_hashes(p, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.session_state.portfolio = json.loads(res[1])
                    st.rerun()
                else:
                    st.error("❌ 账号或密码有误")
            else:
                st.warning("⚠️ 请填写完整信息")

    with tab_reg:
        st.write("<div style='height: 20px'></div>", unsafe_allow_html=True)
        nu = st.text_input("设置用户名", placeholder="NEW USERNAME", key="r_u", label_visibility="collapsed")
        np = st.text_input("设置密码", type="password", placeholder="SET PASSWORD", key="r_p", label_visibility="collapsed")
        
        if st.button("立即开启", key="btn_reg"):
            if nu and np:
                # 显式检查是否存在
                cur = db_conn.cursor()
                cur.execute('SELECT username FROM users WHERE username=?', (nu,))
                if cur.fetchone():
                    st.error("❌ 该用户名已被占用，请换一个")
                else:
                    try:
                        cur.execute('INSERT INTO users VALUES (?,?,?)', (nu, make_hashes(np), "[]"))
                        db_conn.commit()
                        st.success("✅ 注册成功！现在请切换到登录页")
                        st.balloons()
                    except Exception as e:
                        st.error(f"注册出错了: {e}")
            else:
                st.warning("⚠️ 请输入想要设置的账号密码")

    st.markdown('</div>', unsafe_allow_html=True)
