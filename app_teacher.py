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

# ==============================================================================
# 1. 页面基础配置 (SaaS 宽屏模式)
# ==============================================================================
st.set_page_config(page_title="英华教务教研指挥舱", layout="wide", page_icon="🏢", initial_sidebar_state="expanded")

# ==============================================================================
# 🎨 顶级 SaaS 美学 CSS 样式注入 (极简、紧凑、去白边)
# ==============================================================================
st.markdown("""
<style>
    #MainMenu {visibility: hidden;} 
    footer {visibility: hidden;} 
    header {background: transparent !important;}
    
    .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; max-width: 96% !important;}
    .stApp { background-color: #F4F7F9; }
    
    /* =========================================================
       1. 侧边栏瘦身与底色
       ========================================================= */
    [data-testid="stSidebar"] {
        min-width: 250px !important; /* 强制变窄 */
        max-width: 250px !important;
        background-color: #0B1120 !important;
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span {
        color: #94A3B8 !important; 
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #F8FAFC !important; 
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.05) !important;
        margin-top: 10px !important; margin-bottom: 10px !important;
    }

    /* =========================================================
       2. 下拉框 (Selectbox) 彻底暗黑化 (消灭弹出白框)
       ========================================================= */
    [data-testid="stSidebar"] div[data-testid="stSelectbox"] {
        margin-bottom: -15px !important; 
    }
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: #1E293B !important; 
        border: 1px solid rgba(255,255,255,0.05) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] div[data-baseweb="select"] div {
        color: #E2E8F0 !important; 
    }
    [data-testid="stSidebar"] div[data-baseweb="select"] svg {
        fill: #94A3B8 !important;
    }
    /* 穿透全局：把弹出的下拉列表背景也改成暗黑 */
    ul[role="listbox"] {
        background-color: #1E293B !important;
    }
    li[role="option"] {
        background-color: #1E293B !important;
        color: #E2E8F0 !important;
    }
    li[role="option"]:hover {
        background-color: #334155 !important;
    }

    /* =========================================================
       3. 导航折叠面板去白底、去臃肿
       ========================================================= */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details, 
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin-bottom: 5px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p {
        font-size: 15px !important;
        font-weight: bold !important;
        color: #94A3B8 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
        fill: #64748B !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        padding: 0 !important; 
    }

    /* =========================================================
       4. 右侧内容区美化
       ========================================================= */
    .header-card {
        background-color: #FFFFFF; padding: 15px 25px; border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.03); display: flex; justify-content: space-between;
        align-items: center; margin-bottom: 20px; border-left: 6px solid #3B82F6;
    }
    div[data-testid="stMetric"] {
        background-color: #FFFFFF; border-radius: 10px; padding: 15px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.02); border: 1px solid #F1F5F9; text-align: center;
    }
    div[data-testid="stMetric"] label { font-size: 14px !important; color: #64748B !important; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 26px !important; color: #0F172A !important; font-weight: 800 !important; }
    div[data-testid="stForm"] { background-color: #ffffff; padding: 40px; border-radius: 15px; box-shadow: 0 8px 20px rgba(0,0,0,0.05); border: none; }
    .ai-box { background: #FFFFFF; border-left: 5px solid #10B981; padding: 20px; border-radius: 8px; font-size: 15px; color: #333; line-height: 1.8; box-shadow: 0 2px 10px rgba(0,0,0,0.03);}
</style>
""", unsafe_allow_html=True)

CHART_CONFIG = {'displayModeBar': False, 'scrollZoom': False}

# ==============================================================================
# 🔐 权限组定义
# ==============================================================================
GLOBAL_ROLES = ["校长", "副校长", "教学主任", "教务处"]
SUBJECT_HEAD_ROLES = ["学科主任"]
TEACHER_ROLES = ["任课教师", "教师"]
HOMEROOM_ROLES = ["班主任"]

if 'current_grade' not in st.session_state: st.session_state.current_grade = "高三"

# ==============================================================================
# 👑 核心引擎：动态读取配置与数据
# ==============================================================================
try:
    ADMIN_PASSWORD = st.secrets["ADMIN_PWD"]
    HOMEROOM_PASSWORD = st.secrets.get("HOMEROOM_PWD", ADMIN_PASSWORD) 
    TEACHER_PASSWORD = st.secrets.get("TEACHER_PWD", ADMIN_PASSWORD)
    URL_TEACHER_ROSTER = st.secrets.get("URL_TEACHER_ROSTER", "") 
    URL_EXAM_CONFIG = st.secrets.get("URL_EXAM_CONFIG", "")
    AI_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
except Exception as e:
    st.error("⚠️ 系统配置读取失败，请检查 Streamlit 后台的 Secrets。")
    st.stop()

if AI_API_KEY: client = openai.OpenAI(api_key=AI_API_KEY, base_url="https://api.deepseek.com")
else: client = None

def clean_url(url):
    if pd.isna(url): return ""
    u = str(url).strip()
    if u.lower() == 'nan': return ""
    return u

@st.cache_data(ttl=300)
def load_exam_config(url):
    try: return pd.read_csv(url, on_bad_lines='skip')
    except: return pd.DataFrame()

def normalize_class_name(c):
    if pd.isna(c): return ""
    c = str(c).replace(" ", "").strip()
    mapping = {'1':'一','2':'二','3':'三','4':'四','5':'五','6':'六','7':'七','8':'八','9':'九','0':'零'}
    for k, v in mapping.items(): c = c.replace(k, v)
    c = c.replace("高三","").replace("高二","").replace("高一","").replace("年级","").replace("()","").replace("（）","")
    if not c.endswith("班"): c += "班"
    return c

def clean_str(val):
    if pd.isna(val): return ""
    v = str(val).strip()
    if v.endswith('.0'): v = v[:-2]
    return v

def clean_name(val):
    if pd.isna(val): return ""
    return str(val).replace(" ", "").strip()

@st.cache_data(ttl=600)
def load_data(url, header_lines=0):
    if not url or not url.strip(): return None
    try: return pd.read_csv(url, header=header_lines, on_bad_lines='skip')
    except: return None

@st.cache_data(ttl=600, show_spinner=False)
def build_master_df(grade_key):
    config_df = load_exam_config(URL_EXAM_CONFIG)
    exams = []
    if not config_df.empty and '年级' in config_df.columns:
        grade_config = config_df[config_df['年级'].astype(str).str.strip() == grade_key]
        for _, row in grade_config.iterrows():
            exams.append({
                "name": str(row.get('考试名称', '')).strip(),
                "语文": clean_url(row.get('语文')), "数学": clean_url(row.get('数学')),
                "英语": clean_url(row.get('英语')), "物理": clean_url(row.get('物理')),
                "化学": clean_url(row.get('化学')), "生物": clean_url(row.get('生物')),
                "历史": clean_url(row.get('历史')), "政治": clean_url(row.get('政治')),
                "地理": clean_url(row.get('地理'))
            })
    if not exams: return None, None, []
    
    latest_exam = exams[-1]
    dfs = []
    subs = ['语文','数学','英语','物理','化学','生物','历史','政治','地理']
    for sub in subs:
        url = latest_exam.get(sub)
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
    if not dfs: return None, latest_exam, exams
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
    return master, latest_exam, exams

# ==============================================================================
# 🎨 导出与排版模块 (🔴 压缩表格行高)
# ==============================================================================
def render_html_table(df):
    html = """
    <div style="width: 100%; overflow-x: auto; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); border: 1px solid #E8E8E8; background: white;">
    <table style="width: 100%; border-collapse: collapse; font-size: 14px; text-align: center; font-family: 'Helvetica Neue', Arial, sans-serif;">
    """
    # 减小了 th 和 td 的 padding，让行高变紧凑
    html += "<tr>" + "".join([f"<th style='background-color: #FAFAFA; color: #333; padding: 10px 12px; border-bottom: 2px solid #E8E8E8; white-space: nowrap; font-weight: 800;'>{col}</th>" for col in df.columns]) + "</tr>"
    for i, row in df.iterrows():
        bg_color = "#FFFFFF" if i % 2 == 0 else "#FAFAFA"
        html += f"<tr style='background-color: {bg_color}; transition: background-color 0.2s;' onmouseover=\"this.style.backgroundColor='#E6F7FF'\" onmouseout=\"this.style.backgroundColor='{bg_color}'\">"
        for col in df.columns:
            val = row[col]
            if isinstance(val, float): val = f"{val:.1f}"
            html += f"<td style='padding: 8px 12px; border-bottom: 1px solid #F0F0F0; color: #555;'>{val}</td>"
        html += "</tr>"
    html += "</table></div>"
    st.markdown(html, unsafe_allow_html=True)

def generate_excel_download(df, filename_prefix, title_text):
    try:
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='成绩明细', startrow=1)
            worksheet = writer.sheets['成绩明细']
            num_cols = len(df.columns)
            worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=num_cols)
            title_cell = worksheet.cell(row=1, column=1, value=title_text)
            title_cell.font = Font(size=18, bold=True, color="FFFFFFFF") 
            title_cell.fill = PatternFill(start_color="FF3B82F6", end_color="FF3B82F6", fill_type="solid") 
            title_cell.alignment = Alignment(horizontal="center", vertical="center")
            worksheet.row_dimensions[1].height = 40 
            header_fill = PatternFill(start_color="FF64748B", end_color="FF64748B", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFFFF", size=11)
            even_fill = PatternFill(start_color="FFF8FAFC", end_color="FFF8FAFC", fill_type="solid")
            odd_fill = PatternFill(start_color="FFFFFFFF", end_color="FFFFFFFF", fill_type="solid")
            thin_border = Border(left=Side(style='thin', color='FFDDDDDD'), right=Side(style='thin', color='FFDDDDDD'), 
                                 top=Side(style='thin', color='FFDDDDDD'), bottom=Side(style='thin', color='FFDDDDDD'))
            for col_idx in range(1, num_cols + 1):
                col_letter = get_column_letter(col_idx)
                max_len = sum(2 if ord(c)>127 else 1 for c in str(df.columns[col_idx-1]))
                for row_idx in range(2, len(df) + 3):
                    cell = worksheet.cell(row=row_idx, column=col_idx)
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.border = thin_border
                    if row_idx == 2:
                        cell.fill = header_fill
                        cell.font = header_font
                    else:
                        cell.fill = even_fill if row_idx % 2 == 0 else odd_fill
                        cell.font = Font(size=11)
                    val_str = str(cell.value) if cell.value is not None else ""
                    val_len = sum(2 if ord(c)>127 else 1 for c in val_str)
                    if val_len > max_len: max_len = val_len
                worksheet.column_dimensions[col_letter].width = max_len + 4
            for row_idx in range(2, len(df) + 3):
                worksheet.row_dimensions[row_idx].height = 22
        return buffer.getvalue(), f"{filename_prefix}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception as e:
        return df.to_csv(index=False).encode('utf-8-sig'), f"{filename_prefix}.csv", "text/csv"

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
def get_ai_grouped_advice_for_teacher(grade, subject, grouped_data_str):
    if not client: return "⚠️ AI 尚未配置。"
    prompt = f"""你是资深的{grade}{subject}教研专家。
以下是我所带班级在本次考试中，各个薄弱知识点及对应的具体学生名单（仅列出了得分率不足 60% 的学生）：
{grouped_data_str}
请你基于以上真实数据，为我生成一份「精准靶向辅导与分层教学报告」。
要求：
1. 深度剖析：直接针对上述出现的薄弱点进行深度归类分析，指出学生在模型或思路上可能的错因。
2. 靶向措施：给出具体、可操作的课堂补救和教学措施。
3. 必须在建议中自然地提及对应的学生名字，让这份报告具有极强的落地实操性。
"""
    try:
        res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "system", "content": "你是精准教研专家AI。"}, {"role": "user", "content": prompt}])
        return res.choices[0].message.content
    except: return "AI 生成失败"

# ==============================================================================
# 🛡️ 状态管理与初始化
# ==============================================================================
if 'teacher_role' not in st.session_state: st.session_state.teacher_role = None 
if 'teacher_name' not in st.session_state: st.session_state.teacher_name = None
if 'teacher_subject' not in st.session_state: st.session_state.teacher_subject = None
if 'teacher_classes' not in st.session_state: st.session_state.teacher_classes = []

def logout():
    for key in ['teacher_role', 'teacher_name', 'teacher_subject', 'teacher_classes']: st.session_state[key] = None
    st.rerun()

# ==============================================================================
# 🌐 左侧 SaaS 导航边栏 (极致克制风)
# ==============================================================================
menu_sel = "首页" # 防止报错默认值
adm_direction = "物理方向" # 防止报错默认值

if st.session_state.teacher_role:
    with st.sidebar:
        st.markdown(f"<h2 style='margin-top:-20px; padding-bottom: 10px;'>🏫 英华教务系统</h2>", unsafe_allow_html=True)
        
        # 顶部：用户信息模块 (高级深邃卡片)
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); padding: 18px; border-radius: 12px; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.05); box-shadow: 0 4px 12px rgba(0,0,0,0.2);'>
            <div style='color: #F8FAFC; font-size: 18px; font-weight: 800; letter-spacing: 1px;'>👨‍🏫 {st.session_state.teacher_name}</div>
            <div style='color: #94A3B8; font-size: 13px; margin-top: 6px;'>🛡️ 权限：{st.session_state.teacher_role}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 核心筛选器 (极简无标题，紧凑贴合)
        selected_grade = st.selectbox("隐藏标签1", ["高三", "高二", "高一"], index=["高三", "高二", "高一"].index(st.session_state.current_grade), label_visibility="collapsed")
        adm_direction = st.selectbox("隐藏标签2", ["物理方向", "历史方向", "综合方向"], label_visibility="collapsed")
        
        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        
        # 🔴 浅黑底色的悬浮下拉导航菜单 (无底色高亮，仅文字变亮)
        with st.expander("📊 考试分析", expanded=True):
            menu_sel = option_menu(
                menu_title=None,
                options=["首页", "成绩明细表", "历次追踪分析", "AI 教研中心"],
                icons=["grid-fill", "table", "graph-up-arrow", "robot"],
                menu_icon="cast",
                default_index=0,
                styles={
                    # 容器底色为浅黑/深灰
                    "container": {"padding": "5px!important", "background-color": "#162032", "border-radius": "10px"},
                    "icon": {"color": "#64748B", "font-size": "15px"},
                    # 缩小 margin 和 padding，让行距变小
                    "nav-link": {"font-size": "14px", "text-align": "left", "margin":"0px 0", "color": "#64748B", "border-radius": "6px", "padding": "6px 15px"},
                    # 选中时不加背景色，仅字体变纯白加粗
                    "nav-link-selected": {"background-color": "transparent", "color": "#F8FAFC", "font-weight": "bold"},
                    "nav-link:hover": {"background-color": "rgba(255,255,255,0.03)"}
                }
            )
        
        st.divider()
        st.button("🚪 退出当前账号", on_click=logout, use_container_width=True, type="secondary")
        
        if selected_grade != st.session_state.current_grade:
            st.session_state.current_grade = selected_grade
            st.rerun()

# ==============================================================================
# 🚪 登录界面 (未登录状态)
# ==============================================================================
if not st.session_state.teacher_role:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    c_left, c_mid, c_right = st.columns([1, 1.5, 1])
    with c_mid:
        with st.form("teacher_login"):
            st.markdown(f"<h2 style='text-align: center; color: #0F172A; margin-bottom: 30px; font-weight: 800;'>🏫 英华数据指挥舱</h2>", unsafe_allow_html=True)
            t_name = st.text_input("👤 教职工姓名 (需与学校花名册一致)")
            pwd = st.text_input("🔐 访问密码", type="password")
            
            selected_grade = st.session_state.current_grade 
            
            if st.form_submit_button("安全验证并进入", use_container_width=True):
                try: roster_df = pd.read_csv(URL_TEACHER_ROSTER, on_bad_lines='skip')
                except: roster_df = None
                
                if roster_df is not None and '教师姓名' in roster_df.columns:
                    t_info = roster_df[roster_df['教师姓名'].astype(str).str.strip() == t_name.strip()]
                    if not t_info.empty:
                        info = t_info.iloc[0]
                        actual_role = str(info.get('角色', '')).strip()
                        is_auth = False
                        
                        if actual_role in GLOBAL_ROLES and pwd == ADMIN_PASSWORD: is_auth = True
                        elif actual_role in HOMEROOM_ROLES and (pwd == HOMEROOM_PASSWORD or pwd == ADMIN_PASSWORD): is_auth = True
                        elif actual_role in SUBJECT_HEAD_ROLES and (pwd == TEACHER_PASSWORD or pwd == ADMIN_PASSWORD): is_auth = True
                        elif actual_role in TEACHER_ROLES and (pwd == TEACHER_PASSWORD or pwd == ADMIN_PASSWORD): is_auth = True
                        
                        if is_auth:
                            st.session_state.teacher_role = actual_role
                            st.session_state.teacher_name = t_name.strip()
                            st.session_state.teacher_subject = str(info.get('学科', '')).strip()
                            classes_raw = str(info.get('管理班级', ''))
                            classes_clean = re.sub(r'[，、。；/|\s]+', ',', classes_raw)
                            st.session_state.teacher_classes = [normalize_class_name(c) for c in classes_clean.split(',') if c.strip()]
                            st.rerun()
                        else: st.error("❌ 密码错误或权限不匹配，请核对您的身份密码。")
                    else: st.error(f"❌ 权限表中未找到【{t_name}】。")
                else: st.error("⚠️ 无法读取教师权限表，请检查后台配置。")

# ==============================================================================
# 📊 核心业务区 (已登录状态)
# ==============================================================================
else:
    role = st.session_state.teacher_role
    name = st.session_state.teacher_name
    subject = st.session_state.teacher_subject
    my_classes = st.session_state.teacher_classes
    
    # 顶部 Header 卡片
    st.markdown(f"""
    <div class="header-card">
        <h3 style="margin: 0; color: #0F172A; font-weight: 800;">❖ {menu_sel} <span style="font-size:16px; color:#94A3B8; font-weight:normal; margin-left: 10px;">/ {st.session_state.current_grade} · {adm_direction}</span></h3>
    </div>
    """, unsafe_allow_html=True)
    
    master_df, LATEST_EXAM, EXAMS_LIST = build_master_df(st.session_state.current_grade)
    
    if master_df is not None and not master_df.empty:
        df_direction_global = master_df[master_df['方向'] == adm_direction]
        class_avg_global = pd.DataFrame()
        if not df_direction_global.empty and '总分' in df_direction_global.columns:
            class_avg_global = df_direction_global.groupby('班级')['总分'].mean().round(1).reset_index()
            class_avg_global['均分排名'] = class_avg_global['总分'].rank(ascending=False, method='min').astype(int)
        
        df_filtered = df_direction_global.copy()
        
        if role in GLOBAL_ROLES: pass
        elif role in SUBJECT_HEAD_ROLES: pass 
        elif role in HOMEROOM_ROLES or role in TEACHER_ROLES:
            def class_match(cls_str):
                c1 = normalize_class_name(cls_str)
                for my_c in my_classes:
                    if my_c in c1 or c1 in my_c: return True
                return False
            df_filtered = df_filtered[df_filtered['班级'].apply(class_match)]

        if df_filtered.empty:
            st.warning("⚠️ 在当前选择的群体或年级中，未找到您的授权班级数据。")
        else:
            is_single_subject_view = role in TEACHER_ROLES + SUBJECT_HEAD_ROLES
            
            # =====================================================================
            # 模块一：首页
            # =====================================================================
            if menu_sel == "首页":
                total_stu = len(df_filtered)
                class_count = df_filtered['班级'].nunique()
                
                metric_col = subject if (is_single_subject_view and subject in df_filtered.columns) else '总分'
                
                if not is_single_subject_view:
                    avail_metrics = ['总分'] + [s for s in ['语文','数学','英语','物理','化学','生物','历史','政治','地理'] if s in df_filtered.columns and df_filtered[s].sum() > 0]
                    st.markdown("<p style='font-size: 14px; font-weight: bold; color: #64748B; margin-bottom: -10px;'>⚡ 切换全局大盘分析指标</p>", unsafe_allow_html=True)
                    c_sel, _ = st.columns([1, 4])
                    metric_col = c_sel.selectbox("隐藏下拉", avail_metrics, label_visibility="collapsed")
                    st.markdown("<br>", unsafe_allow_html=True)
                else:
                    if subject not in df_filtered.columns:
                        st.warning(f"当前考试未配置您的学科【{subject}】的数据。")
                        st.stop()
                
                overall_avg = df_filtered[metric_col].mean().round(1) if total_stu > 0 else 0
                class_avgs = df_filtered.groupby('班级')[metric_col].mean()
                top_class = class_avgs.idxmax() if not class_avgs.empty else "无"
                
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("所辖班级数", f"{class_count} 个")
                k2.metric("覆盖学生人数", f"{total_stu} 人")
                k3.metric(f"{metric_col}群像均分", f"{overall_avg} 分")
                k4.metric(f"{metric_col}领跑班级", top_class)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                if not class_avgs.empty:
                    df_bar = class_avgs.reset_index().round(1)
                    fig_bar = px.bar(df_bar, x='班级', y=metric_col, text_auto=True, color='班级', 
                                     color_discrete_sequence=px.colors.qualitative.Pastel,
                                     title=f"🏆 各班级【{metric_col}】均分横向对比阵列")
                    
                    fig_bar.update_traces(textposition='outside', width=0.35, textfont_size=14, marker_line_width=0)
                    
                    fig_bar.add_hline(y=overall_avg, line_dash="dot", line_color="#EF4444", line_width=2,
                                      annotation_text=f"🎯 群像均分红线: {overall_avg:.1f}", annotation_position="top left", 
                                      annotation_font=dict(color="#EF4444", size=13, weight="bold"))
                    
                    y_max = df_bar[metric_col].max() * 1.15 if not df_bar.empty else 100
                    fig_bar.update_layout(
                        dragmode=False, showlegend=False, yaxis_range=[0, y_max], 
                        plot_bgcolor='rgba(248, 250, 252, 0.5)', 
                        paper_bgcolor='white',
                        margin=dict(t=60, b=30, l=30, r=30),
                        xaxis_title=None, yaxis_title=None,
                        yaxis=dict(showgrid=True, gridcolor='#F1F5F9', gridwidth=1)
                    )
                    
                    with st.container(border=True):
                        st.plotly_chart(fig_bar, use_container_width=True, config=CHART_CONFIG)

            # =====================================================================
            # 模块二：成绩明细表
            # =====================================================================
            elif menu_sel == "成绩明细表":
                if is_single_subject_view:
                    st.info(f"💡 当前为学科专属视图，仅展示【{subject}】的单科成绩及排名。")
                    if subject in df_filtered.columns:
                        df_filtered[f'{subject}班级排名'] = df_filtered.groupby('班级')[subject].rank(ascending=False, method='min').fillna(0).astype(int)
                        df_filtered[f'{subject}年级排名'] = df_filtered[subject].rank(ascending=False, method='min').fillna(0).astype(int)
                        table_to_show = df_filtered[['姓名', '考号', '班级', f'{subject}年级排名', f'{subject}班级排名', subject]].sort_values(by=subject, ascending=False)
                        render_html_table(table_to_show)
                        
                        file_data, file_name, mime_type = generate_excel_download(table_to_show, f"【{st.session_state.current_grade}】_{subject}明细", f"【{LATEST_EXAM['name']}】{subject}成绩单")
                        st.download_button(label="📥 下载精美 Excel 成绩单", data=file_data, file_name=file_name, mime=mime_type, type="primary")
                    else:
                        st.warning(f"当前考试中未找到您的学科【{subject}】。")
                else:
                    st.info("💡 当前为全科汇总视图。")
                    cols = df_filtered.columns.tolist()
                    front_cols = ['姓名', '考号', '班级', '总分', '总分年级排名', '总分班级排名', '方向']
                    other_cols = [c for c in cols if c not in front_cols]
                    table_to_show = df_filtered[front_cols + other_cols].sort_values(by=['班级', '总分'], ascending=[True, False])
                    render_html_table(table_to_show)
                    
                    file_data, file_name, mime_type = generate_excel_download(table_to_show, f"【{st.session_state.current_grade}】_{adm_direction}全科明细", f"【{LATEST_EXAM['name']}】{adm_direction}成绩汇总单")
                    st.download_button(label="📥 下载全科 Excel 汇总单", data=file_data, file_name=file_name, mime=mime_type, type="primary")

            # =====================================================================
            # 模块三：历次追踪分析
            # =====================================================================
            elif menu_sel == "历次追踪分析":
                st.info("🔍 在下方下拉框中搜索学生姓名，系统将跨越“时间胶囊”自动聚合该生的所有历史轨迹！")
                student_options = df_filtered.apply(lambda x: f"{x['班级']} | {x['姓名']} | 考号:{x['考号']}", axis=1).tolist()
                
                if student_options:
                    st.markdown("<p style='font-size: 14px; font-weight: bold; color: #64748B; margin-bottom: -10px;'>🔎 检索目标学生</p>", unsafe_allow_html=True)
                    c_sel, _ = st.columns([1, 1])
                    sel_student_str = c_sel.selectbox("隐藏标签", ["-- 请点击输入或选择学生 --"] + student_options, label_visibility="collapsed")
                    
                    if sel_student_str != "-- 请点击输入或选择学生 --":
                        sel_id = clean_str(sel_student_str.split("考号:")[1].strip())
                        sel_name = sel_student_str.split("|")[1].strip()
                        
                        history_records = []
                        with st.spinner(f"正在从云端数据库抽取【{sel_name}】的历史档案..."):
                            for i, exam in enumerate(EXAMS_LIST):
                                exam_df = None
                                dfs_sub = []
                                subs_hist = ['语文','数学','英语','物理','化学','生物','历史','政治','地理']
                                for sh in subs_hist:
                                    u = exam.get(sh)
                                    if u:
                                        d_sub = load_data(u, header_lines=[0,1,2])
                                        if d_sub is not None:
                                            n_c, i_c = None, None
                                            for col in d_sub.columns:
                                                cstr = str(col[0]) if isinstance(col, tuple) else str(col)
                                                if '姓名' in cstr: n_c = col
                                                elif '考号' in cstr or '学号' in cstr: i_c = col
                                            if n_c and i_c:
                                                r_ls = []
                                                for _, row in d_sub.iterrows():
                                                    if clean_str(row[i_c]) == sel_id:
                                                        tot = 0
                                                        for c in d_sub.columns:
                                                            if c in [n_c, i_c]: continue
                                                            if '总分' in str(c) or '排名' in str(c): continue
                                                            try: 
                                                                v = float(row[c])
                                                                if pd.notna(v): tot += v
                                                            except: pass
                                                        r_ls.append({'考号': sel_id, sh: round(tot, 1)})
                                                if r_ls: dfs_sub.append(pd.DataFrame(r_ls))
                                if dfs_sub:
                                    exam_master = functools.reduce(lambda l, r: pd.merge(l, r, on=['考号'], how='outer'), dfs_sub)
                                    p_subs = [s for s in subs_hist if s in exam_master.columns]
                                    exam_master['总分'] = exam_master[p_subs].fillna(0).sum(axis=1).round(1)
                                    row = exam_master.iloc[0]
                                    rec = {"考试名称": exam['name']}
                                    if '总分' in row: rec['总分'] = float(row['总分'])
                                    for s in subs_hist:
                                        if s in row and pd.notna(row[s]): rec[s] = float(row[s])
                                    history_records.append(rec)
                                        
                        if history_records:
                            st.markdown("<br>", unsafe_allow_html=True)
                            df_hist = pd.DataFrame(history_records)
                            with st.container(border=True):
                                if is_single_subject_view:
                                    if subject in df_hist.columns:
                                        fig = px.line(df_hist, x="考试名称", y=subject, markers=True, title=f"📈 【{sel_name}】{subject} 历次成绩波动曲线", line_shape="spline")
                                        fig.update_traces(line_color="#3B82F6", marker=dict(size=10))
                                        fig.update_layout(dragmode=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(showgrid=True, gridcolor='#F1F5F9'))
                                        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
                                    else:
                                        st.warning(f"未检索到该生【{subject}】的历史成绩。")
                                else:
                                    t_col1, t_col2 = st.columns(2)
                                    with t_col1:
                                        if "总分" in df_hist.columns:
                                            fig1 = px.line(df_hist, x="考试名称", y="总分", markers=True, title=f"📈 【{sel_name}】历次总分波动曲线", line_shape="spline")
                                            fig1.update_traces(line_color="#3B82F6", marker=dict(size=10))
                                            fig1.update_layout(dragmode=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(showgrid=True, gridcolor='#F1F5F9'))
                                            st.plotly_chart(fig1, use_container_width=True, config=CHART_CONFIG)
                                    with t_col2:
                                        avail_hist_subs = [s for s in ['语文','数学','英语','物理','化学','生物','历史','政治','地理'] if s in df_hist.columns]
                                        if avail_hist_subs:
                                            st.markdown("<p style='font-size: 14px; font-weight: bold; color: #64748B; margin-bottom: -10px;'>🔬 透视单科走势</p>", unsafe_allow_html=True)
                                            sel_hist_sub = st.selectbox("隐藏标签", avail_hist_subs, key="hist_sub", label_visibility="collapsed")
                                            fig3 = px.line(df_hist, x="考试名称", y=sel_hist_sub, markers=True, title=f"📉 【{sel_name}】{sel_hist_sub} 单科走势", line_shape="spline")
                                            fig3.update_traces(line_color="#10B981", marker=dict(size=10))
                                            fig3.update_layout(dragmode=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(showgrid=True, gridcolor='#F1F5F9'))
                                            st.plotly_chart(fig3, use_container_width=True, config=CHART_CONFIG)
                        else:
                            st.info("暂未抓取到该生的历史轨迹。")

            # =====================================================================
            # 模块四：AI 教研中心
            # =====================================================================
            elif menu_sel == "AI 教研中心":
                st.info("🧠 欢迎进入 AI 教研舱。系统将自动抓取底层题库，计算全班单题得分率，并进行智能聚类！")
                
                analyze_subject = subject
                if not is_single_subject_view:
                    avail_subs = [s for s in ['语文','数学','英语','物理','化学','生物','历史','政治','地理'] if s in df_filtered.columns]
                    if avail_subs:
                        st.markdown("<p style='font-size: 14px; font-weight: bold; color: #64748B; margin-bottom: -10px;'>⚙️ 选择要进行 AI 诊断的学科</p>", unsafe_allow_html=True)
                        c_sel, _ = st.columns([1, 3])
                        analyze_subject = c_sel.selectbox("隐藏下拉", avail_subs, label_visibility="collapsed")
                        st.markdown("<br>", unsafe_allow_html=True)
                    else:
                        analyze_subject = None
                
                if analyze_subject and LATEST_EXAM and LATEST_EXAM.get(analyze_subject):
                    df_diag = load_data(LATEST_EXAM[analyze_subject], header_lines=[0, 1, 2])
                    if df_diag is not None:
                        name_c, id_c, cls_c = None, None, None
                        for col in df_diag.columns:
                            cstr = str(col[0]) if isinstance(col, tuple) else str(col)
                            if '姓名' in cstr: name_c = col
                            elif '考号' in cstr or '学号' in cstr: id_c = col
                            elif '班级' in cstr: cls_c = col
                        
                        if name_c and cls_c:
                            def is_my_scope(c_val):
                                c1 = normalize_class_name(c_val)
                                if role in GLOBAL_ROLES + SUBJECT_HEAD_ROLES:
                                    return c1 in df_filtered['班级'].tolist()
                                for my_c in my_classes:
                                    if my_c in c1 or c1 in my_c: return True
                                return False
                            
                            df_diag_my = df_diag[df_diag[cls_c].apply(is_my_scope)]
                            
                            if not df_diag_my.empty:
                                k_stats = {}
                                weak_group_map = {} 
                                
                                for col in df_diag_my.columns:
                                    if col in [name_c, id_c, cls_c]: continue
                                    cstr = str(col[0]) if isinstance(col, tuple) else str(col)
                                    if '总分' in cstr or '排名' in cstr: continue
                                    
                                    q_name = str(col[0]).strip() if isinstance(col, tuple) else str(col).strip()
                                    kp = str(col[1]).strip() if isinstance(col, tuple) and len(col) > 1 else q_name
                                    if kp == "" or kp.startswith("Unnamed"): kp = q_name
                                    
                                    try: full = float(col[2]) if isinstance(col, tuple) and len(col) > 2 else 0
                                    except: full = 0
                                    if full <= 0:
                                        try: full = float(pd.to_numeric(df_diag_my[col], errors='coerce').max())
                                        except: full = 0
                                        
                                    if full > 0:
                                        if kp not in k_stats: k_stats[kp] = []
                                        k_stats[kp].append(pd.to_numeric(df_diag_my[col], errors='coerce').mean() / full)
                                        
                                        for _, r_data in df_diag_my.iterrows():
                                            stu_n = clean_name(r_data[name_c])
                                            try: score = float(r_data[col])
                                            except: score = 0
                                            if score < full * 0.6: 
                                                if kp not in weak_group_map: weak_group_map[kp] = []
                                                if stu_n and stu_n not in weak_group_map[kp]:
                                                    weak_group_map[kp].append(stu_n)
                                        
                                if k_stats:
                                    with st.container(border=True):
                                        k_final = [{"知识点": kp, "群体整体掌握率": round(sum(rates)/len(rates)*100, 1)} for kp, rates in k_stats.items()]
                                        df_k = pd.DataFrame(k_final).sort_values("群体整体掌握率")
                                        fig_k = px.bar(df_k, x="群体整体掌握率", y="知识点", orientation='h', title=f"🎯 【{analyze_subject}】知识点群体掌握率扫描")
                                        fig_k.update_layout(dragmode=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                                        st.plotly_chart(fig_k, use_container_width=True, config=CHART_CONFIG)
                                    
                                    sorted_weak_kps = sorted(weak_group_map.items(), key=lambda x: len(x[1]), reverse=True)
                                    grouped_str_list = []
                                    for kp, students in sorted_weak_kps[:5]:
                                        if students: grouped_str_list.append(f"【{kp}】得分率<60%的薄弱名单（需重点关注）：{', '.join(students)}")
                                    grouped_data_str = "\n".join(grouped_str_list)
                                    
                                    ai_t_key = f"ai_tea_{st.session_state.current_grade}_{name}_{analyze_subject}"
                                    saved_t_list_key = f"saved_ai_tea_list_{st.session_state.current_grade}_{name}_{analyze_subject}"
                                    
                                    if saved_t_list_key not in st.session_state: st.session_state[saved_t_list_key] = []

                                    if AI_API_KEY:
                                        if st.button("✨ 一键生成【AI 分层教学与靶向辅导报告】", type="primary"):
                                            with st.spinner("AI 大脑正在深度剖析每个学生的单题得分，进行聚类提取..."):
                                                ai_reply = get_ai_grouped_advice_for_teacher(st.session_state.current_grade, analyze_subject, grouped_data_str)
                                                st.session_state[ai_t_key] = ai_reply

                                        if ai_t_key in st.session_state:
                                            saved_reply = st.session_state[ai_t_key]
                                            st.markdown(f"<div class='ai-box'><b>🤖 专家指导建议：</b><br><br>{saved_reply}</div><br>", unsafe_allow_html=True)
                                            
                                            doc_title = f"【{LATEST_EXAM['name']}】{analyze_subject}_AI教研报告"
                                            
                                            t_c1, t_c2, t_c3 = st.columns([1.5, 1, 1])
                                            with t_c1:
                                                if st.button("📌 存入本设备暂存库"):
                                                    st.session_state[saved_t_list_key].insert(0, saved_reply)
                                                    st.toast("✅ 已成功存入！")
                                            with t_c3:
                                                file_data, file_name, mime_type = generate_ai_doc(doc_title, saved_reply)
                                                st.download_button(label="📥 下载 Word 排版报告", data=file_data, file_name=file_name, mime=mime_type, type="primary")

                                        if st.session_state[saved_t_list_key]:
                                            with st.expander(f"📂 本机暂存报告库 (共 {len(st.session_state[saved_t_list_key])} 份)"):
                                                for idx, old_rep in enumerate(st.session_state[saved_t_list_key]):
                                                    st.markdown(f"**🔖 版本 {len(st.session_state[saved_t_list_key]) - idx}**")
                                                    st.markdown(old_rep)
                                                    st.divider()
                else:
                    st.warning(f"目前缺少【{analyze_subject}】的单题明细表，无法进行 AI 深度诊断。")
    else:
        st.warning("📡 尚未配置数据或当前年级无考试记录。")