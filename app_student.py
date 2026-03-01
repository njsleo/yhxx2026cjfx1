import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from streamlit_option_menu import option_menu
import openai
import os
import functools
import io
import re

st.set_page_config(page_title="英华学校考试学情自诊系统", layout="wide", page_icon="🎓", initial_sidebar_state="expanded")

if 'current_grade' not in st.session_state: st.session_state.current_grade = "高三"

with st.sidebar:
    st.markdown("### 🎓 选择年级")
    selected_grade = st.selectbox("当前年级：", ["高三", "高二", "高一"], index=["高三", "高二", "高一"].index(st.session_state.current_grade))

if selected_grade != st.session_state.current_grade:
    st.session_state.current_grade = selected_grade
    for key in ['logged_in_student', 'logged_in_id', 'logged_in_direction']:
        st.session_state[key] = None
    st.rerun()

# ==============================================================================
# 👑 读取总控台链接与 API
# ==============================================================================
try:
    AI_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
    URL_EXAM_CONFIG = st.secrets.get("URL_EXAM_CONFIG", "")
except Exception as e:
    st.error("⚠️ 系统配置读取失败，请检查后台 Secrets。")
    st.stop()

if AI_API_KEY: client = openai.OpenAI(api_key=AI_API_KEY, base_url="https://api.deepseek.com")
else: client = None

def clean_url(url):
    if pd.isna(url): return ""
    u = str(url).strip()
    if u.lower() == 'nan': return ""
    return u

@st.cache_data(ttl=300) # 每5分钟去总控表拉取一次最新链接
def load_exam_config(url):
    try: return pd.read_csv(url, on_bad_lines='skip')
    except: return pd.DataFrame()

config_df = load_exam_config(URL_EXAM_CONFIG)
EXAMS = []

if not config_df.empty and '年级' in config_df.columns:
    grade_config = config_df[config_df['年级'].astype(str).str.strip() == selected_grade]
    for _, row in grade_config.iterrows():
        EXAMS.append({
            "name": str(row.get('考试名称', '')).strip(),
            "语文": clean_url(row.get('语文')),
            "数学": clean_url(row.get('数学')),
            "英语": clean_url(row.get('英语')),
            "物理": clean_url(row.get('物理')),
            "化学": clean_url(row.get('化学')),
            "生物": clean_url(row.get('生物')),
            "历史": clean_url(row.get('历史')),
            "政治": clean_url(row.get('政治')),
            "地理": clean_url(row.get('地理'))
        })

LATEST_EXAM_IDX = len(EXAMS) - 1 if EXAMS else -1
LATEST_EXAM = EXAMS[-1] if EXAMS else None

# ==============================================================================
# 🛠️ 核心引擎
# ==============================================================================
def clean_str(val):
    if pd.isna(val): return ""
    v = str(val).strip()
    if v.endswith('.0'): v = v[:-2]
    return v

def clean_name(val):
    if pd.isna(val): return ""
    return str(val).replace(" ", "").strip()

def normalize_class_name(c):
    if pd.isna(c): return ""
    c = str(c).replace(" ", "").strip()
    mapping = {'1':'一','2':'二','3':'三','4':'四','5':'五','6':'六','7':'七','8':'八','9':'九','0':'零'}
    for k, v in mapping.items(): c = c.replace(k, v)
    c = c.replace("高三","").replace("高二","").replace("高一","").replace("年级","").replace("()","").replace("（）","")
    if not c.endswith("班"): c += "班"
    return c

@st.cache_data(ttl=600)
def load_data(url, header_lines=0):
    if not url or not url.strip(): return None
    try: return pd.read_csv(url, header=header_lines, on_bad_lines='skip')
    except: return None

@st.cache_data(ttl=600, show_spinner=False)
def build_master_df(exam_idx, grade_key):
    if exam_idx < 0 or exam_idx >= len(EXAMS): return None
    exam = EXAMS[exam_idx]
    dfs = []
    subs = ['语文','数学','英语','物理','化学','生物','历史','政治','地理']
    for sub in subs:
        url = exam.get(sub)
        if url:
            df_sub = load_data(url, header_lines=[0,1,2])
            if df_sub is not None:
                name_c, id_c, cls_c = None, None, None
                for col in df_sub.columns:
                    cstr = str(col[0]) if isinstance(col, tuple) else str(col)
                    if '姓名' in cstr: name_c = col
                    elif '考号' in cstr or '学号' in cstr: id_c = col
                    elif '班级' in cstr: cls_c = col
                if name_c and id_c:
                    res = []
                    for _, row in df_sub.iterrows():
                        tot = 0
                        for c in df_sub.columns:
                            if c in [name_c, id_c, cls_c]: continue
                            cstr = str(c[0]) if isinstance(c, tuple) else str(c)
                            if '总分' in cstr or '排名' in cstr: continue
                            try: 
                                val = float(row[c])
                                if pd.notna(val): tot += val
                            except: pass
                        s_name = clean_name(row[name_c])
                        s_id = clean_str(row[id_c])
                        s_cls = normalize_class_name(row[cls_c]) if cls_c else "未分班"
                        if s_id: res.append({'姓名': s_name, '考号': s_id, '班级': s_cls, sub: round(tot, 1)})
                    if res: dfs.append(pd.DataFrame(res))
    if not dfs: return None
    master = functools.reduce(lambda l, r: pd.merge(l, r, on=['姓名','考号','班级'], how='outer'), dfs)
    present_subs = [s for s in subs if s in master.columns]
    master[present_subs] = master[present_subs].fillna(0)
    master['总分'] = master[present_subs].sum(axis=1).round(1)
    
    def get_dir(r):
        if r.get('物理', 0) > 0: return "物理方向"
        if r.get('历史', 0) > 0: return "历史方向"
        cls_n = str(r.get('班级', ''))
        if '文' in cls_n or '史' in cls_n: return "历史方向"
        if '理' in cls_n or '物' in cls_n: return "物理方向"
        return "综合方向"
    master['方向'] = master.apply(get_dir, axis=1)
    master['总分班级排名'] = master.groupby(['班级', '方向'])['总分'].rank(ascending=False, method='min').fillna(0).astype(int)
    master['总分年级排名'] = master.groupby(['方向'])['总分'].rank(ascending=False, method='min').fillna(0).astype(int)
    return master

# ==============================================================================
# 📥 Word 导出引擎 (纯净排版)
# ==============================================================================
def generate_ai_doc(title, content):
    try:
        import docx
        from docx.shared import Pt
        from docx.oxml.ns import qn
        from docx.enum.text import WD_LINE_SPACING, WD_PARAGRAPH_ALIGNMENT
        doc = docx.Document()
        style = doc.styles['Normal']
        style.font.name = '仿宋'
        style._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')
        style.font.size = Pt(10.5)
        
        h = doc.add_heading(level=1)
        h.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = h.add_run(title)
        run.font.name = '黑体'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        run.font.size = Pt(14)
        run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)

        def add_runs_to_paragraph(p, text):
            parts = re.split(r'(\*\*.*?\*\*)', text)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    clean_text = part[2:-2].replace('*', '') 
                    r = p.add_run(clean_text)
                    r.bold = True
                else:
                    clean_text = part.replace('*', '')
                    r = p.add_run(clean_text)
                r.font.name = '仿宋'
                r._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')
                r.font.size = Pt(10.5)

        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            if line.startswith('- '): line = line[2:].strip()
            if line.startswith('* '): line = line[2:].strip()
            line = line.replace('•', '').replace('·', '').strip()
            
            if line.startswith('#'):
                level = 0
                while level < len(line) and line[level] == '#': level += 1
                text = line[level:].strip().replace('*', '')
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE 
                r = p.add_run(text)
                r.bold = True
                r.font.size = Pt(12) 
                r.font.name = '黑体'
                r._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
            else:
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE 
                add_runs_to_paragraph(p, line)

        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue(), f"{title}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    except:
        return f"【{title}】\n\n{content}".encode('utf-8-sig'), f"{title}.txt", "text/plain"

@st.cache_data(ttl=2592000, show_spinner=False)
def get_ai_advice_for_student(grade, student_name, subject, weak_points, strong_points):
    if not client: return "⚠️ AI 尚未配置。"
    prompt = f"你是经验丰富的{grade}{subject}教师。学生 {student_name} 优势：{strong_points}。薄弱：{weak_points}。请结合具体知识点，写约300字的个性化鼓励和提分计划，给出具体的学习方法指导。"
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "system", "content": "你是专业AI导师。"}, {"role": "user", "content": prompt}])
        return res.choices[0].message.content
    except: return "AI 生成失败"

if 'logged_in_student' not in st.session_state: st.session_state.logged_in_student = None
if 'logged_in_id' not in st.session_state: st.session_state.logged_in_id = None
if 'logged_in_direction' not in st.session_state: st.session_state.logged_in_direction = None

def logout():
    for key in ['logged_in_student', 'logged_in_id', 'logged_in_direction']: st.session_state[key] = None
    st.rerun()

st.markdown("""
<style>
    #MainMenu {visibility: hidden;} header {visibility: hidden;} footer {visibility: hidden;}
    .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
    .stApp { background-color: #f4f7f9; }
    div[data-testid="stMetric"] { background-color: #ffffff; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.03); border: 1px solid #ebeef5; text-align: center; }
    div[data-testid="stForm"] { background-color: #ffffff; padding: 30px; border-radius: 15px; box-shadow: 0 8px 20px rgba(0,0,0,0.05); border: none; }
    div[data-testid="stFormSubmitButton"] > button { background-color: #0068C9; color: white; font-weight: bold; border-radius: 8px; border: none; padding: 10px 0; }
    .congrats-banner { background: linear-gradient(90deg, #FFFBEB, #FFF7ED); border: 2px solid #FCD34D; color: #92400E; padding: 12px 20px; border-radius: 12px; text-align: center; font-size: 18px; font-weight: bold; margin-bottom: 25px; box-shadow: 0 4px 12px rgba(252, 211, 77, 0.2); line-height: 1.6; }
    .main-title { text-align: center; color: #1E3A8A; font-size: 28px; font-weight: 800; margin-bottom: 15px; }
    .ai-box { background: linear-gradient(135deg, #f0f7ff 0%, #e6f3ff 100%); border-left: 5px solid #0068C9; padding: 25px; border-radius: 12px; font-size: 16px; color: #333; line-height: 1.8; box-shadow: 0 4px 15px rgba(0,104,201,0.1);}
</style>
""", unsafe_allow_html=True)

CHART_CONFIG = {'displayModeBar': False, 'scrollZoom': False}

selected_nav = option_menu(
    menu_title=None, options=["成绩总览", "历次追踪", "深度诊断"], 
    icons=["clipboard-data", "graph-up", "bullseye"], menu_icon="cast", default_index=0, orientation="horizontal",
    styles={ "container": {"padding": "5px", "background-color": "#ffffff", "border-radius": "12px", "box-shadow": "0 4px 15px rgba(0,0,0,0.08)", "margin-bottom": "30px", "position": "sticky", "top": "15px", "z-index": "9999"}, "nav-link-selected": {"background-color": "#0068C9", "color": "white", "font-weight": "bold"} }
)

if not st.session_state.logged_in_student:
    st.markdown(f"<h1 class='main-title'>🏫 英华学校【{selected_grade}】学情查询端</h1>", unsafe_allow_html=True)
    latest_master = build_master_df(LATEST_EXAM_IDX, selected_grade)
    if latest_master is not None and not latest_master.empty:
        top_p = latest_master[latest_master['方向'] == '物理方向'].sort_values('总分', ascending=False).head(5)['姓名'].tolist()
        top_h = latest_master[latest_master['方向'] == '历史方向'].sort_values('总分', ascending=False).head(5)['姓名'].tolist()
        str_p = f"🚀 理科前五名：{'、'.join(top_p)}" if top_p else ""
        str_h = f"🌟 文科前五名：{'、'.join(top_h)}" if top_h else ""
        banner_html = f"🎉 <b>【{LATEST_EXAM['name']}】成绩表彰光荣榜</b> 🏆<br>"
        if str_p: banner_html += f"<span style='font-size: 16px; color: #D97706;'>{str_p}</span>"
        if str_p and str_h: banner_html += "<br>"
        if str_h: banner_html += f"<span style='font-size: 16px; color: #D97706;'>{str_h}</span>"
        st.markdown(f'<div class="congrats-banner">{banner_html}</div>', unsafe_allow_html=True)
    
    col_left, col_mid, col_right = st.columns([1, 1.8, 1])
    with col_mid:
        with st.form("student_login"):
            st.markdown(f"<h3 style='text-align: center; color: #555;'>👨‍🎓 学生/家长登录入口</h3><br>", unsafe_allow_html=True)
            name = st.text_input("👤 学生姓名", placeholder="请输入真实姓名")
            stu_id = st.text_input("🔢 考号/学号", placeholder="请输入准确考号")
            if st.form_submit_button("🔍 立即查分", use_container_width=True):
                if name and stu_id:
                    if latest_master is not None:
                        clean_n = clean_name(name)
                        clean_i = clean_str(stu_id)
                        match = latest_master[(latest_master['姓名'] == clean_n) & (latest_master['考号'] == clean_i)]
                        if not match.empty:
                            st.session_state.logged_in_student = clean_n
                            st.session_state.logged_in_id = clean_i
                            st.session_state.logged_in_direction = match.iloc[0]['方向']
                            st.rerun()
                        else: st.error("❌ 未查询到成绩，请确认姓名和考号是否正确。")
                    else: st.warning("系统暂未配置该年级的考试数据。")
                else: st.error("⚠️ 请完整填写信息")
else:
    c1, c2 = st.columns([4, 1])
    c1.markdown(f"**当前用户：** {st.session_state.logged_in_student} ({selected_grade}) | **系统判定方向：** {st.session_state.logged_in_direction}")
    if c2.button("🚪 退出登录", use_container_width=True): logout()
    st.divider()

    master_df = build_master_df(LATEST_EXAM_IDX, selected_grade)
    stu_data = master_df[(master_df['姓名'] == st.session_state.logged_in_student) & (master_df['考号'] == st.session_state.logged_in_id)].iloc[0]
    
    if selected_nav == "成绩总览":
        st.markdown(f"### 🏆 【{LATEST_EXAM['name']}】成绩概览")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("姓名", stu_data['姓名'])
        k2.metric("方向", stu_data['方向'])
        k3.metric("总分", f"{stu_data['总分']}")
        k4.metric("班级名次", f"第 {stu_data['总分班级排名']} 名")
        k5.metric("年级名次", f"第 {stu_data['总分年级排名']} 名")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📊 各科得分对比")
        subs = ['语文','数学','英语','物理','化学','生物','历史','政治','地理']
        valid_subs = [s for s in subs if s in stu_data and stu_data[s] > 0]
        
        if valid_subs:
            chart_data = pd.DataFrame({"科目": valid_subs, "得分": [stu_data[s] for s in valid_subs]})
            col_bar, col_radar = st.columns(2)
            with col_bar:
                fig1 = px.bar(chart_data, x='科目', y='得分', text_auto=True, color='科目')
                fig1.update_traces(textposition='outside', width=0.5)
                fig1.update_layout(showlegend=False, margin=dict(t=40, b=20, l=20, r=20), paper_bgcolor='rgba(0,0,0,0)', dragmode=False)
                st.plotly_chart(fig1, use_container_width=True, config=CHART_CONFIG)
            with col_radar:
                fig2 = px.line_polar(chart_data, r='得分', theta='科目', line_close=True)
                fig2.update_traces(fill='toself', line_color='#0068C9')
                fig2.update_layout(margin=dict(t=40, b=20, l=40, r=40), paper_bgcolor='rgba(0,0,0,0)', dragmode=False)
                st.plotly_chart(fig2, use_container_width=True, config=CHART_CONFIG)
        
    elif selected_nav == "历次追踪":
        st.markdown(f"### 📈 历次考试波动轨迹")
        history_records = []
        with st.spinner("正在云端汇聚历次成绩轨迹..."):
            for i, exam in enumerate(EXAMS):
                m_df = build_master_df(i, selected_grade)
                if m_df is not None and not m_df.empty:
                    stu_h = m_df[(m_df['姓名'] == st.session_state.logged_in_student) & (m_df['考号'] == st.session_state.logged_in_id)]
                    if not stu_h.empty:
                        history_records.append({ "考试名称": exam['name'], "总分": float(stu_h.iloc[0]['总分']), "年级排名": int(stu_h.iloc[0]['总分年级排名']) })
        
        if history_records:
            df_trend = pd.DataFrame(history_records)
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                fig_score = px.line(df_trend, x="考试名称", y="总分", markers=True, title="总分走势图", line_shape="spline")
                fig_score.update_traces(line_color="#FF4B4B", marker=dict(size=10))
                fig_score.update_layout(dragmode=False)
                st.plotly_chart(fig_score, use_container_width=True, config=CHART_CONFIG)
            with col_t2:
                fig_rank = px.line(df_trend, x="考试名称", y="年级排名", markers=True, title="总分年级排名走势 (向下代表进步)", line_shape="spline")
                fig_rank.update_traces(line_color="#0068C9", marker=dict(size=10))
                fig_rank.update_yaxes(autorange="reversed")
                fig_rank.update_layout(dragmode=False)
                st.plotly_chart(fig_rank, use_container_width=True, config=CHART_CONFIG)
        else: st.info("暂未抓取到您的历史轨迹。")

    elif selected_nav == "深度诊断":
        avail_subs = [s for s in ['语文','数学','英语','物理','化学','生物','历史','政治','地理'] if s in stu_data and stu_data[s] > 0 and LATEST_EXAM.get(s)]
        if not avail_subs: st.info("暂未配置您所考科目的详细题库数据。")
        else:
            sel_sub = st.selectbox("👇 选择诊断科目", avail_subs)
            df_diag = load_data(LATEST_EXAM[sel_sub], header_lines=[0, 1, 2])
            if df_diag is not None:
                name_c, id_c, cls_c = None, None, None
                for col in df_diag.columns:
                    cstr = str(col[0]) if isinstance(col, tuple) else str(col)
                    if '姓名' in cstr: name_c = col
                    elif '考号' in cstr or '学号' in cstr: id_c = col
                    elif '班级' in cstr: cls_c = col
                if name_c and id_c:
                    found_idx = -1
                    for idx, row in df_diag.iterrows():
                        if clean_name(row[name_c]) == st.session_state.logged_in_student and clean_str(row[id_c]) == st.session_state.logged_in_id: 
                            found_idx = idx; break
                    if found_idx != -1:
                        knowledge_map = {} 
                        for col in df_diag.columns:
                            if col in [name_c, id_c, cls_c]: continue
                            cstr = str(col[0]) if isinstance(col, tuple) else str(col)
                            if '总分' in cstr or '排名' in cstr: continue
                            q_name = str(col[0]).strip() if isinstance(col, tuple) else str(col).strip()
                            k_point = str(col[1]).strip() if isinstance(col, tuple) and len(col) > 1 else q_name
                            if k_point == "" or k_point.startswith("Unnamed"): k_point = q_name
                            try: full = float(col[2]) if isinstance(col, tuple) and len(col) > 2 else 0
                            except: full = 0
                            if full <= 0:
                                try: full = float(pd.to_numeric(df_diag[col], errors='coerce').max())
                                except: full = 0
                            if full <= 0: continue
                            if k_point not in knowledge_map: knowledge_map[k_point] = {'my': 0, 'full': 0, 'class_total': 0}
                            try: my_s = float(df_diag.iloc[found_idx][col])
                            except: my_s = 0
                            class_s = pd.to_numeric(df_diag[col], errors='coerce').mean()
                            knowledge_map[k_point]['my'] += my_s
                            knowledge_map[k_point]['full'] += full
                            knowledge_map[k_point]['class_total'] += class_s
                        
                        k_data, weak_points_list, strong_points_list = [], [], []
                        for kp, val in knowledge_map.items():
                            my_rate = round((val['my']/val['full'])*100, 1) if val['full']>0 else 0
                            avg_rate = round((val['class_total']/val['full'])*100, 1) if val['full']>0 else 0
                            k_data.append({'知识点': kp, '我的掌握率': my_rate, '班级平均': avg_rate})
                            if my_rate < avg_rate: weak_points_list.append(kp)
                            else: strong_points_list.append(kp)
                        
                        df_kp = pd.DataFrame(k_data)
                        if not df_kp.empty:
                            c_chart, c_text = st.columns([1.2, 1])
                            with c_chart:
                                fig = go.Figure()
                                cats = df_kp['知识点'].tolist() + [df_kp['知识点'].tolist()[0]]
                                mys = df_kp['我的掌握率'].tolist() + [df_kp['我的掌握率'].tolist()[0]]
                                avgs = df_kp['班级平均'].tolist() + [df_kp['班级平均'].tolist()[0]]
                                fig.add_trace(go.Scatterpolar(r=avgs, theta=cats, fill='toself', name='班级平均', line_color='#cccccc'))
                                fig.add_trace(go.Scatterpolar(r=mys, theta=cats, fill='toself', name='我的掌握', line_color='#FF4B4B'))
                                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), paper_bgcolor='rgba(0,0,0,0)', dragmode=False)
                                st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
                            with c_text:
                                st.markdown("#### 🩺 专家系统诊断")
                                if weak_points_list:
                                    for row in k_data:
                                        if row['知识点'] in weak_points_list:
                                            st.write(f"▪ **{row['知识点']}** (落后 {row['班级平均'] - row['我的掌握率']:.1f}%)")
                                else: st.success("🎉 所有知识点均达标！")
                            
                            st.divider()
                            
                            ai_state_key = f"ai_stu_{selected_grade}_{st.session_state.logged_in_id}_{sel_sub}"
                            saved_list_key = f"saved_ai_stu_list_{selected_grade}_{st.session_state.logged_in_id}_{sel_sub}"
                            if saved_list_key not in st.session_state: st.session_state[saved_list_key] = []

                            if AI_API_KEY:
                                if st.button(f"✨ 提取专家 AI 提分建议", type="primary"):
                                    with st.spinner("AI 导师正在云端调取档案..."):
                                        w_str = "、".join(weak_points_list) if weak_points_list else "无"
                                        s_str = "、".join(strong_points_list) if strong_points_list else "无"
                                        ai_reply = get_ai_advice_for_student(selected_grade, st.session_state.logged_in_student, sel_sub, w_str, s_str)
                                        st.session_state[ai_state_key] = ai_reply

                                if ai_state_key in st.session_state:
                                    saved_reply = st.session_state[ai_state_key]
                                    st.markdown(f"<div class='ai-box'><b>👨‍🏫 AI导师：</b><br><br>{saved_reply}</div><br>", unsafe_allow_html=True)
                                    
                                    doc_title = f"{st.session_state.logged_in_student}_{sel_sub}_专属提分计划"
                                    t_c1, t_c2, t_c3 = st.columns([1.5, 1, 1])
                                    with t_c1:
                                        if st.button("📌 将此版建议存入网页下方档案库"):
                                            st.session_state[saved_list_key].insert(0, saved_reply)
                                            st.toast("✅ 已成功存入下方档案库！")
                                    with t_c2:
                                        export_fmt = st.selectbox("导出格式", ["Word文档 (自动精排版)", "TXT纯文本"], label_visibility="collapsed", key="fmt_stu")
                                    with t_c3:
                                        if "Word" in export_fmt:
                                            file_data, file_name, mime_type = generate_ai_doc(doc_title, saved_reply)
                                        else:
                                            file_data = saved_reply.encode('utf-8-sig')
                                            file_name = f"{doc_title}.txt"
                                            mime_type = "text/plain"
                                        st.download_button(label="📥 导出本地文件", data=file_data, file_name=file_name, mime=mime_type, type="primary")

                                if st.session_state[saved_list_key]:
                                    with st.expander(f"📂 网页端已暂存的分析报告 (共 {len(st.session_state[saved_list_key])} 份) - 点击对比"):
                                        for idx, old_rep in enumerate(st.session_state[saved_list_key]):
                                            st.markdown(f"**🔖 暂存版本 {len(st.session_state[saved_list_key]) - idx}**")
                                            st.markdown(old_rep)
                                            st.divider()
