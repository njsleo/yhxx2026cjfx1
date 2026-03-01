import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import openai
import os
import functools
import io
import re

st.set_page_config(page_title="英华学校教务教研指挥舱", layout="wide", page_icon="🏢", initial_sidebar_state="expanded")

if 'current_grade' not in st.session_state: st.session_state.current_grade = "高三"

with st.sidebar:
    st.markdown("### 🏢 教务指挥舱中控台")
    selected_grade = st.selectbox("切换当前操作年级：", ["高三", "高二", "高一"], index=["高三", "高二", "高一"].index(st.session_state.current_grade))
    st.divider()
    st.info(f"💡 当前系统已锁定为【{selected_grade}】数据通道。")

if selected_grade != st.session_state.current_grade:
    st.session_state.current_grade = selected_grade
    for key in ['teacher_role', 'teacher_name', 'teacher_subject', 'teacher_classes']:
        st.session_state[key] = None
    st.rerun()

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

# ==============================================================================
# 👑 核心引擎：动态读取《全校考试总控台》
# ==============================================================================
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
    # 自动筛选出当前所选年级的考试配置
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
# 🛠️ 数据净化与总分聚合
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
# 🎨 UI 组件与排版引擎 
# ==============================================================================
def render_html_table(df):
    html = """
    <div style="width: 100%; overflow-x: auto; margin-bottom: 25px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
    <table style="width: 100%; border-collapse: collapse; font-size: 16px; text-align: center; font-family: 'Helvetica Neue', Arial, sans-serif;">
    """
    html += "<tr>" + "".join([f"<th style='background-color: #0068C9; color: white; padding: 18px 12px; border: 1px solid #e1e4e8; white-space: nowrap; font-weight: bold;'>{col}</th>" for col in df.columns]) + "</tr>"
    for i, row in df.iterrows():
        bg_color = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
        html += f"<tr style='background-color: {bg_color}; transition: background-color 0.2s;' onmouseover=\"this.style.backgroundColor='#E6F3FF'\" onmouseout=\"this.style.backgroundColor='{bg_color}'\">"
        for col in df.columns:
            val = row[col]
            if isinstance(val, float): val = f"{val:.1f}"
            html += f"<td style='padding: 16px 12px; border: 1px solid #e1e4e8; color: #2c3e50;'>{val}</td>"
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
            title_cell.font = Font(size=20, bold=True, color="FFFFFFFF") 
            title_cell.fill = PatternFill(start_color="FF0068C9", end_color="FF0068C9", fill_type="solid") 
            title_cell.alignment = Alignment(horizontal="center", vertical="center")
            worksheet.row_dimensions[1].height = 45 
            header_fill = PatternFill(start_color="FF4A90E2", end_color="FF4A90E2", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFFFF", size=12)
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
                worksheet.row_dimensions[row_idx].height = 25
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
# 🛡️ 状态与样式 
# ==============================================================================
if 'teacher_role' not in st.session_state: st.session_state.teacher_role = None 
if 'teacher_name' not in st.session_state: st.session_state.teacher_name = None
if 'teacher_subject' not in st.session_state: st.session_state.teacher_subject = None
if 'teacher_classes' not in st.session_state: st.session_state.teacher_classes = []

def logout():
    for key in ['teacher_role', 'teacher_name', 'teacher_subject', 'teacher_classes']: st.session_state[key] = None
    st.rerun()

st.markdown("""
<style>
    #MainMenu {visibility: hidden;} header {visibility: hidden;} footer {visibility: hidden;}
    .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
    .stApp { background-color: #f4f7f9; }
    div[data-testid="stMetric"] { background-color: #ffffff; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.03); border: 1px solid #ebeef5; text-align: center; }
    div[data-testid="stForm"] { background-color: #ffffff; padding: 30px; border-radius: 15px; box-shadow: 0 8px 20px rgba(0,0,0,0.05); border: none; }
    div[data-testid="stFormSubmitButton"] > button { background-color: #0068C9; color: white; font-weight: bold; border-radius: 8px; border: none; padding: 10px 0; }
    .main-title { text-align: center; color: #1E3A8A; font-size: 28px; font-weight: 800; margin-bottom: 15px; }
    .ai-box { background: linear-gradient(135deg, #f0f7ff 0%, #e6f3ff 100%); border-left: 5px solid #0068C9; padding: 25px; border-radius: 12px; font-size: 16px; color: #333; line-height: 1.8; box-shadow: 0 4px 15px rgba(0,104,201,0.1);}
</style>
""", unsafe_allow_html=True)

CHART_CONFIG = {'displayModeBar': False, 'scrollZoom': False}

# 🔴 权限角色定义字典
GLOBAL_ROLES = ["校长", "副校长", "教学主任", "教务处"]
SUBJECT_HEAD_ROLES = ["学科主任"]
TEACHER_ROLES = ["任课教师", "教师"]
HOMEROOM_ROLES = ["班主任"]

if not st.session_state.teacher_role:
    st.markdown(f"<h1 class='main-title'>🏫 英华教务教研指挥舱 ({selected_grade})</h1>", unsafe_allow_html=True)
    col_left, col_mid, col_right = st.columns([1, 1.8, 1])
    with col_mid:
        with st.container(border=True):
            st.markdown(f"<h3 style='text-align: center; color: #555;'>👨‍🏫 教职工统一登录端口</h3><br>", unsafe_allow_html=True)
            t_name = st.text_input("👤 您的姓名 (需与学校花名册一致)")
            pwd = st.text_input("🔐 通行密码", type="password")
            
            if st.button("验证并进入控制台", use_container_width=True, type="primary"):
                try: roster_df = pd.read_csv(URL_TEACHER_ROSTER, on_bad_lines='skip')
                except: roster_df = None
                
                if roster_df is not None and '教师姓名' in roster_df.columns:
                    t_info = roster_df[roster_df['教师姓名'].astype(str).str.strip() == t_name.strip()]
                    if not t_info.empty:
                        info = t_info.iloc[0]
                        actual_role = str(info.get('角色', '')).strip()
                        is_auth = False
                        
                        # 🔴 密码校验逻辑：高管组用ADMIN密码；学科主任和普通老师通用；班主任用班主任密码。
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

else:
    role = st.session_state.teacher_role
    name = st.session_state.teacher_name
    subject = st.session_state.teacher_subject
    my_classes = st.session_state.teacher_classes
    
    c1, c2 = st.columns([5, 1])
    c1.markdown(f"### 👨‍🏫 欢迎，{name}老师！【权限级别：{role} | {selected_grade}】")
    if c2.button("🚪 安全退出 (切换身份必点)", use_container_width=True): logout()
    
    master_df = build_master_df(LATEST_EXAM_IDX, selected_grade)
    if master_df is not None and not master_df.empty:
        adm_direction = st.selectbox("👉 选择分析群体", ["物理方向", "历史方向", "综合方向"])
        df_direction_global = master_df[master_df['方向'] == adm_direction]
        class_avg_global = pd.DataFrame()
        if not df_direction_global.empty and '总分' in df_direction_global.columns:
            class_avg_global = df_direction_global.groupby('班级')['总分'].mean().round(1).reset_index()
            class_avg_global['均分排名'] = class_avg_global['总分'].rank(ascending=False, method='min').astype(int)
        
        df_filtered = df_direction_global.copy()
        
        # ==========================================================
        # 🔴 五级权限数据过滤墙
        # ==========================================================
        if role in GLOBAL_ROLES:
            st.success(f"👑 {role}全局权限：已为您展示【{selected_grade}】全体班级数据。")
        elif role in SUBJECT_HEAD_ROLES:
            st.success(f"🎯 学科主任权限：已为您展示【{selected_grade}】所有班级的【{subject}】数据对比。")
            # 不筛班级，但后续图表只画该学科
        elif role in HOMEROOM_ROLES or role in TEACHER_ROLES:
            def class_match(cls_str):
                c1 = normalize_class_name(cls_str)
                for my_c in my_classes:
                    if my_c in c1 or c1 in my_c: return True
                return False
            df_filtered = df_filtered[df_filtered['班级'].apply(class_match)]
            if role in HOMEROOM_ROLES: st.success(f"🛡️ 班主任数据保护生效：仅查看【{'、'.join(my_classes)}】数据。")
            else: st.success(f"🛡️ 单科保护生效：仅查看所带班级的【{subject}】成绩。")
        
        if not df_filtered.empty:
            st.divider()
            
            # --- 单科视图：适用于 学科主任、任课教师 ---
            if role in SUBJECT_HEAD_ROLES + TEACHER_ROLES:
                if subject in df_filtered.columns:
                    st.markdown(f"#### 📊 【{subject}】成绩透视与教研")
                    
                    class_avg = df_filtered.groupby('班级')[subject].mean().round(1).reset_index()
                    overall_avg = df_filtered[subject].mean().round(1) 
                    
                    fig_bar_t = px.bar(class_avg, x='班级', y=subject, text_auto=True, color='班级', title=f"各班级【{subject}】平均分横向对比")
                    fig_bar_t.update_traces(textposition='outside', width=0.5)
                    fig_bar_t.add_hline(y=overall_avg, line_dash="dash", line_color="#FF4B4B", annotation_text=f"该群体均分基准线: {overall_avg:.1f}", annotation_position="top left", annotation_font=dict(color="#FF4B4B", size=14, weight="bold"))
                    y_max = class_avg[subject].max() * 1.15 if not class_avg.empty else 100
                    fig_bar_t.update_layout(dragmode=False, showlegend=False, yaxis_range=[0, y_max], margin=dict(t=50, b=20, l=20, r=20))
                    st.plotly_chart(fig_bar_t, use_container_width=True, config=CHART_CONFIG)
                    
                    st.markdown(f"#### 📋 【{subject}】学生成绩排名总表")
                    df_filtered[f'{subject}班级排名'] = df_filtered.groupby('班级')[subject].rank(ascending=False, method='min').fillna(0).astype(int)
                    df_filtered[f'{subject}年级排名'] = df_filtered[subject].rank(ascending=False, method='min').fillna(0).astype(int)
                    table_to_show = df_filtered[['姓名', '考号', '班级', f'{subject}年级排名', f'{subject}班级排名', subject]].sort_values(by=subject, ascending=False)
                    render_html_table(table_to_show)
                    
                    excel_title = f"【{LATEST_EXAM['name']}】{subject}专项成绩单"
                    file_data, file_name, mime_type = generate_excel_download(table_to_show, f"{LATEST_EXAM['name']}_{subject}专项成绩单", excel_title)
                    st.download_button(label="📥 一键下载精美 Excel 成绩单", data=file_data, file_name=file_name, mime=mime_type, type="primary")
                    
                    # --- AI 教研系统 ---
                    if LATEST_EXAM.get(subject):
                        st.divider()
                        st.markdown(f"#### 🧠 【{subject}】底层错因诊断与 AI 靶向辅导规划")
                        df_diag = load_data(LATEST_EXAM[subject], header_lines=[0, 1, 2])
                        if df_diag is not None:
                            name_c, id_c, cls_c = None, None, None
                            for col in df_diag.columns:
                                cstr = str(col[0]) if isinstance(col, tuple) else str(col)
                                if '姓名' in cstr: name_c = col
                                elif '考号' in cstr or '学号' in cstr: id_c = col
                                elif '班级' in cstr: cls_c = col
                            
                            if name_c and cls_c:
                                df_diag_my = df_diag.copy()
                                # 如果是普通老师，只看自己班；学科主任看全区
                                if role in TEACHER_ROLES:
                                    def is_my_class(c_val):
                                        c1 = normalize_class_name(c_val)
                                        for my_c in my_classes:
                                            if my_c in c1 or c1 in my_c: return True
                                        return False
                                    df_diag_my = df_diag[df_diag[cls_c].apply(is_my_class)]
                                
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
                                            for _, row in df_diag_my.iterrows():
                                                stu_n = clean_name(row[name_c])
                                                try: score = float(row[col])
                                                except: score = 0
                                                if score < full * 0.6: 
                                                    if kp not in weak_group_map: weak_group_map[kp] = []
                                                    if stu_n and stu_n not in weak_group_map[kp]: weak_group_map[kp].append(stu_n)
                                    if k_stats:
                                        k_final = [{"知识点": kp, "班级整体掌握率": round(sum(rates)/len(rates)*100, 1)} for kp, rates in k_stats.items()]
                                        df_k = pd.DataFrame(k_final).sort_values("班级整体掌握率")
                                        fig_k = px.bar(df_k, x="班级整体掌握率", y="知识点", orientation='h')
                                        fig_k.update_layout(dragmode=False)
                                        st.plotly_chart(fig_k, use_container_width=True, config=CHART_CONFIG)
                                        
                                        sorted_weak_kps = sorted(weak_group_map.items(), key=lambda x: len(x[1]), reverse=True)
                                        grouped_str_list = []
                                        for kp, students in sorted_weak_kps[:5]:
                                            if students: grouped_str_list.append(f"【{kp}】得分率<60%的薄弱名单（需重点关注）：{', '.join(students)}")
                                        grouped_data_str = "\n".join(grouped_str_list)
                                        
                                        ai_t_key = f"ai_tea_{selected_grade}_{name}_{subject}"
                                        saved_t_list_key = f"saved_ai_tea_list_{selected_grade}_{name}_{subject}"
                                        if saved_t_list_key not in st.session_state: st.session_state[saved_t_list_key] = []
                                        if AI_API_KEY:
                                            if st.button("✨ 智能生成【分层教学与靶向辅导报告】", type="primary"):
                                                with st.spinner("AI 正在深度剖析试卷单题得分，进行聚类分析..."):
                                                    ai_reply = get_ai_grouped_advice_for_teacher(selected_grade, subject, grouped_data_str)
                                                    st.session_state[ai_t_key] = ai_reply

                                            if ai_t_key in st.session_state:
                                                saved_reply = st.session_state[ai_t_key]
                                                st.markdown(f"<div class='ai-box'><b>👨‍🏫 教学指导 AI：</b><br><br>{saved_reply}</div><br>", unsafe_allow_html=True)
                                                doc_title = f"【{LATEST_EXAM['name']}】{subject}学科_分层辅导教研报告"
                                                t_c1, t_c2, t_c3 = st.columns([1.5, 1, 1])
                                                with t_c1:
                                                    if st.button("📌 将此版教研报告存入下方档案库"):
                                                        st.session_state[saved_t_list_key].insert(0, saved_reply)
                                                        st.toast("✅ 已成功存入网页历史档案库！")
                                                with t_c2:
                                                    export_fmt = st.selectbox("导出格式", ["Word文档 (自动精排版)", "TXT纯文本"], label_visibility="collapsed", key="fmt_tea")
                                                with t_c3:
                                                    if "Word" in export_fmt: file_data, file_name, mime_type = generate_ai_doc(doc_title, saved_reply)
                                                    else: file_data, file_name, mime_type = saved_reply.encode('utf-8-sig'), f"{doc_title}.txt", "text/plain"
                                                    st.download_button(label="📥 导出报告至电脑", data=file_data, file_name=file_name, mime=mime_type, type="primary")

                                            if st.session_state[saved_t_list_key]:
                                                with st.expander(f"📂 网页端已暂存的教研报告 (共 {len(st.session_state[saved_t_list_key])} 份) - 点击展开"):
                                                    for idx, old_rep in enumerate(st.session_state[saved_t_list_key]):
                                                        st.markdown(f"**🔖 暂存版本 {len(st.session_state[saved_t_list_key]) - idx}**")
                                                        st.markdown(old_rep)
                                                        st.divider()
                else: st.warning(f"当前群体的考试中未找到您的专属学科【{subject}】。")
            
            # --- 全局多科视图：适用于 校长组、教务处、班主任 ---
            else:
                if role in HOMEROOM_ROLES and not class_avg_global.empty:
                    st.markdown(f"#### 🏆 【本班核心指标快报】")
                    metric_cols = st.columns(len(my_classes))
                    for i, cls in enumerate(my_classes):
                        cls_info = class_avg_global[class_avg_global['班级'].apply(lambda x: normalize_class_name(cls) in normalize_class_name(x))]
                        if not cls_info.empty:
                            avg = cls_info.iloc[0]['总分']
                            rk = cls_info.iloc[0]['均分排名']
                            metric_cols[i].metric(label=f"{cls} 平均分", value=f"{avg} 分", delta=f"该方向年级第 {rk} 名", delta_color="off")
                        else: metric_cols[i].metric(label=f"{cls}", value="暂无数据")
                    st.markdown("<br>", unsafe_allow_html=True)
                
                avail_metrics = ['总分']
                for s in ['语文','数学','英语','物理','化学','生物','历史','政治','地理']:
                    if s in df_filtered.columns and df_filtered[s].sum() > 0: avail_metrics.append(s)
                st.info("💡 下方图表支持自由切换查看【总分】或各门【单科】成绩对比！")
                selected_metric = st.selectbox("📊 请选择要对比的指标：", avail_metrics)
                
                class_avg = df_filtered.groupby('班级')[selected_metric].mean().round(1).reset_index()
                overall_avg = df_filtered[selected_metric].mean().round(1) 
                
                fig_bar_tot = px.bar(class_avg, x='班级', y=selected_metric, text_auto=True, color='班级', title=f"各班级【{selected_metric}】均分横向对比")
                fig_bar_tot.update_traces(textposition='outside', width=0.5)
                fig_bar_tot.add_hline(y=overall_avg, line_dash="dash", line_color="#FF4B4B", annotation_text=f"平均线: {overall_avg:.1f}", annotation_position="top left", annotation_font=dict(color="#FF4B4B", size=14, weight="bold"))
                y_max = class_avg[selected_metric].max() * 1.15 if not class_avg.empty else 100
                fig_bar_tot.update_layout(dragmode=False, showlegend=False, yaxis_range=[0, y_max], margin=dict(t=50, b=20, l=20, r=20))
                st.plotly_chart(fig_bar_tot, use_container_width=True, config=CHART_CONFIG)
                
                st.markdown("#### 📋 学生全科大表明细")
                cols = df_filtered.columns.tolist()
                front_cols = ['姓名', '考号', '班级', '总分', '总分年级排名', '总分班级排名', '方向']
                other_cols = [c for c in cols if c not in front_cols]
                table_to_show = df_filtered[front_cols + other_cols].sort_values(by=['班级', '总分'], ascending=[True, False])
                render_html_table(table_to_show)
                
                excel_title = f"【{LATEST_EXAM['name']}】{adm_direction}成绩汇总单"
                file_data, file_name, mime_type = generate_excel_download(table_to_show, f"{LATEST_EXAM['name']}_{adm_direction}成绩汇总单", excel_title)
                st.download_button(label="📥 一键下载精美 Excel 汇总单", data=file_data, file_name=file_name, mime=mime_type, type="primary")

            # ==========================================================
            # 🔍 历次档案调取系统 (所有老师均可使用)
            # ==========================================================
            st.divider()
            st.markdown("#### 🔍 个人历次档案调阅系统")
            st.info("💡 在下拉框中搜索学生姓名，一键调取该生自入学以来的成绩波动轨迹！")
            student_options = df_filtered.apply(lambda x: f"{x['班级']} | {x['姓名']} | 考号:{x['考号']}", axis=1).tolist()
            if student_options:
                sel_student_str = st.selectbox("请搜索目标学生：", ["-- 请选择学生 --"] + student_options)
                if sel_student_str != "-- 请选择学生 --":
                    sel_id = clean_str(sel_student_str.split("考号:")[1].strip())
                    sel_name = sel_student_str.split("|")[1].strip()
                    history_records = []
                    with st.spinner(f"正在云端库检索【{sel_name}】的档案..."):
                        for i, exam in enumerate(EXAMS):
                            m_df = build_master_df(i, selected_grade)
                            if m_df is not None and not m_df.empty:
                                stu_h = m_df[m_df['考号'] == sel_id]
                                if not stu_h.empty:
                                    row = stu_h.iloc[0]
                                    rec = {"考试名称": exam['name']}
                                    if '总分' in row: rec['总分'] = float(row['总分'])
                                    if '总分年级排名' in row: rec['年级排名'] = int(row['总分年级排名'])
                                    for s in ['语文','数学','英语','物理','化学','生物','历史','政治','地理']:
                                        if s in row and pd.notna(row[s]): rec[s] = float(row[s])
                                    history_records.append(rec)
                    if history_records:
                        df_hist = pd.DataFrame(history_records)
                        # 任课教师 / 学科主任 默认看该单科
                        if role in TEACHER_ROLES + SUBJECT_HEAD_ROLES:
                            if subject in df_hist.columns:
                                fig = px.line(df_hist, x="考试名称", y=subject, markers=True, title=f"【{sel_name}】{subject} 历次走势", line_shape="spline")
                                fig.update_traces(line_color="#FF4B4B", marker=dict(size=10))
                                fig.update_layout(dragmode=False)
                                st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
                            else: st.warning(f"未检索到该生【{subject}】的历史成绩。")
                        else:
                            t_col1, t_col2 = st.columns(2)
                            with t_col1:
                                if "总分" in df_hist.columns:
                                    fig1 = px.line(df_hist, x="考试名称", y="总分", markers=True, title=f"【{sel_name}】历次总分走势", line_shape="spline")
                                    fig1.update_traces(line_color="#FF4B4B", marker=dict(size=10))
                                    fig1.update_layout(dragmode=False)
                                    st.plotly_chart(fig1, use_container_width=True, config=CHART_CONFIG)
                            with t_col2:
                                if "年级排名" in df_hist.columns:
                                    fig2 = px.line(df_hist, x="考试名称", y="年级排名", markers=True, title=f"【{sel_name}】历次总分年级排名走势", line_shape="spline")
                                    fig2.update_traces(line_color="#0068C9", marker=dict(size=10))
                                    fig2.update_yaxes(autorange="reversed")
                                    fig2.update_layout(dragmode=False)
                                    st.plotly_chart(fig2, use_container_width=True, config=CHART_CONFIG)
                            
                            st.markdown("##### 🔬 该生单科历史透视")
                            avail_hist_subs = [s for s in ['语文','数学','英语','物理','化学','生物','历史','政治','地理'] if s in df_hist.columns]
                            if avail_hist_subs:
                                sel_hist_sub = st.selectbox("选择要查看的单科：", avail_hist_subs, key="hist_sub")
                                fig3 = px.line(df_hist, x="考试名称", y=sel_hist_sub, markers=True, title=f"【{sel_name}】{sel_hist_sub} 历次成绩走势", line_shape="spline")
                                fig3.update_traces(line_color="#10B981", marker=dict(size=10))
                                fig3.update_layout(dragmode=False)
                                st.plotly_chart(fig3, use_container_width=True, config=CHART_CONFIG)
                    else: st.info("暂未抓取到该生的历史轨迹。")
        else: st.warning("⚠️ 在当前选择的群体中，未找到您的数据。")