import streamlit as st
import hashlib
import sqlite3
import json

# ================= 🎨 强制样式穿透 (解决文字看不见 & 布局错位) =================
def apply_pro_style():
    st.markdown("""
        <style>
        /* 1. 强制全局背景 */
        .stApp { background-color: #0e0e0e !important; }

        /* 2. 彻底移除所有默认边框和多余的灰色方块 */
        div[data-testid="stVerticalBlock"] > div { background-color: transparent !important; border: none !important; box-shadow: none !important; }
        
        /* 3. 强制输入框文字为纯白色，并调整背景色 */
        input {
            color: #FFFFFF !important; 
            -webkit-text-fill-color: #FFFFFF !important; /* 针对部分移动端浏览器 */
            background-color: rgba(255, 255, 255, 0.1) !important;
            border: 1px solid #444 !important;
        }
        
        /* 4. 修改 Placeholder (提示词) 颜色为灰色，避免干扰 */
        input::placeholder { color: #888 !important; }

        /* 5. 重新定义 Logo 样式，去除上方空隙 */
        .big-logo {
            font-size: 80px;
            font-weight: 900;
            text-align: center;
            background: linear-gradient(180deg, #FFFFFF, #D4AF37);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-top: -20px;
            margin-bottom: 0px;
        }

        /* 6. 自定义登录卡片 */
        .custom-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 20px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        </style>
    """, unsafe_allow_html=True)

def show_login_page():
    apply_pro_style()
    
    # 调整整体高度位置
    st.markdown('<div style="height: 50px;"></div>', unsafe_allow_html=True)
    
    # 使用自定义 HTML 结构，不使用 st.container 以免产生灰色框
    st.markdown('<h1 class="big-logo">ZZL</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; color:#888; margin-top:-10px;">PRO 资产管理系统</p>', unsafe_allow_html=True)
    st.markdown('<div style="height: 30px;"></div>', unsafe_allow_html=True)

    # 左右留白，让登录框居中
    _, col_mid, _ = st.columns([0.1, 0.8, 0.1])
    
    with col_mid:
        tab_login, tab_reg = st.tabs(["🔑 安全登录", "✨ 快速注册"])
        
        with tab_login:
            st.write("") # 间距
            # 注意：key 值一定要唯一
            login_user = st.text_input("账号", placeholder="请输入用户名", key="final_l_u", label_visibility="collapsed")
            login_pwd = st.text_input("密码", type="password", placeholder="请输入密码", key="final_l_p", label_visibility="collapsed")
            
            if st.button("立即进入系统", key="final_btn_l", use_container_width=True):
                if login_user and login_pwd:
                    # 数据库操作建议增加异常捕获
                    conn = sqlite3.connect('zzl_users_new.db') # 改个名字，换个新环境
                    c = conn.cursor()
                    c.execute('SELECT password, portfolio FROM users WHERE username=?', (login_user,))
                    result = c.fetchone()
                    conn.close() # 查完立即关闭，防止锁死
                    
                    if result and check_hashes(login_pwd, result[0]):
                        st.session_state.logged_in = True
                        st.session_state.username = login_user
                        st.session_state.portfolio = json.loads(result[1])
                        st.rerun()
                    else:
                        st.error("❌ 账号或密码不正确")
                else:
                    st.warning("请完整填写信息")

        with tab_reg:
            st.write("") 
            reg_user = st.text_input("设置账号", placeholder="建议用手机号", key="final_r_u", label_visibility="collapsed")
            reg_pwd = st.text_input("设置密码", type="password", placeholder="建议6位以上", key="final_r_p", label_visibility="collapsed")
            
            if st.button("创建并登录", key="final_btn_r", use_container_width=True):
                if reg_user and reg_pwd:
                    conn = sqlite3.connect('zzl_users_new.db') # 保持一致
                    c = conn.cursor()
                    # 1. 先查重
                    c.execute('SELECT username FROM users WHERE username=?', (reg_user,))
                    if c.fetchone():
                        st.error("❌ 这个用户名已经有人用了")
                        conn.close()
                    else:
                        try:
                            # 2. 插入
                            c.execute('INSERT INTO users(username, password, portfolio) VALUES (?,?,?)', 
                                      (reg_user, make_hashes(reg_pwd), "[]"))
                            conn.commit()
                            conn.close()
                            st.success("✅ 注册成功！请切换到登录页进入")
                            st.balloons()
                        except Exception as e:
                            st.error(f"注册失败: {e}")
                            conn.close()
                else:
                    st.warning("请完整填写信息")
