import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime
import uuid
import re

# --- 1. 전역 설정 및 상수 ---
st.set_page_config(page_title="26년 슈팅스타 통합관리 V0.9", page_icon="🌱", layout="wide")

INACTIVE_STATUS = ['이사', '비활성', '졸업', '타교회']
ALL_STATUS_OPTS = ["일반", "새친구", "교사", "교역자", "전도사", "목사", "이사", "졸업", "타교회", "비활성"]

st.markdown("""
    <style>
    .class-header { background-color: #f1f8ff; padding: 12px 15px; border-radius: 8px; color: #0366d6; font-weight: 800; font-size: 1.1rem; margin-top: 20px; margin-bottom: 15px; border-left: 5px solid #0366d6; }
    div[data-testid="stToggle"] { border: 2px solid #eef2f6; padding: 12px 18px; border-radius: 16px; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.2s ease-in-out; margin-bottom: 10px; }
    div[data-testid="stToggle"]:hover { border-color: #0366d6; background-color: #f8fbff; }
    .total-summary { background-color: #e6f2ff; padding: 15px; border-radius: 10px; text-align: center; color: #005bb5; font-size: 1.2rem; font-weight: bold; margin-bottom: 20px; }
    .event-card { border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin-bottom: 15px; background-color: #fafafa; }
    div[data-testid="stButton"] button { width: 100%; border-radius: 6px; text-align: left; padding: 4px 8px; font-size: 0.9rem; }
    
    /* 모바일 환경 탭 메뉴 자동 줄바꿈 적용 */
    div[data-baseweb="tab-list"] {
        flex-wrap: wrap !important;
        gap: 5px;
    }
    div[data-baseweb="tab"] {
        flex: 1 1 auto;
        justify-content: center;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    
    /* [핵심 개선] 행사기록 사진 1/2 축소 및 가로/세로 혼합 비율 깔끔하게 썸네일 고정 */
    div[data-testid="column"] div[data-testid="stImage"] img {
        height: 120px !important;
        object-fit: cover !important;
        border-radius: 8px;
    }
    div[data-testid="column"] div[data-testid="stVideo"] video {
        height: 120px !important;
        object-fit: cover !important;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 시스템 접근 제어 ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("## 🔒 26년 슈팅스타 시스템 접근 제어")
    pwd = st.text_input("슈팅스타 비밀번호8자리(특수문자포함)를 입력하세요", type="password")
    if st.button("로그인"):
        if "admin_password" in st.secrets and pwd == st.secrets["admin_password"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")
    st.stop()

if "GOOGLE_PROXY_URL" in st.secrets: GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else: st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!"); st.stop()

start_date = datetime.date(2026, 1, 4)

# --- 3. 공통 유틸리티 함수 ---
def safe_str(val):
    if pd.isna(val) or str(val).strip() in ['None', 'nan', 'NaT', '']: return ''
    return str(val).strip()

def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        headers = {"Authorization": f"Bearer {st.secrets.get('PROXY_AUTH_KEY', '')}"} if "PROXY_AUTH_KEY" in st.secrets else {}
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}, headers=headers, timeout=120)
        res.raise_for_status()
        return res.json().get("fileUrl", "")
    except Exception as e: 
        return ""

def chunked_update(worksheet, cells, chunk_size=100):
    for i in range(0, len(cells), chunk_size):
        worksheet.update_cells(cells[i:i + chunk_size])

def parse_date_safe(date_str):
    if not date_str: return datetime.date(2015, 1, 1)
    try:
        clean_str = str(date_str).replace(" ", "").strip().rstrip('.').replace('.', '-').replace('/', '-')
        if len(clean_str) == 8 and clean_str.count('-') == 0: return datetime.datetime.strptime(clean_str, "%Y%m%d").date()
        return datetime.datetime.strptime(clean_str, "%Y-%m-%d").date()
    except: return datetime.date(2015, 1, 1)

def natural_sort_key(s):
    clean_s = str(s).replace(" ", "")
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', clean_s)]

def class_sort_key(c):
    c_str = str(c).replace(" ", "")
    priority = 1
    if any(k in c_str for k in ['교역자', '전도사', '목사']): priority = 3
    elif any(k in c_str for k in ['선생님', '교사']): priority = 2
    return (priority, [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', c_str)])

def get_teacher_rank(name, memo):
    text = str(name) + " " + str(memo)
    match = re.search(r'\[(\d+)\]', text)
    if match: return int(match.group(1))
    if '전도사' in text or '목사' in text: return 10
    if '부장' in text: return 20
    if '부감' in text: return 30
    if '총무' in text: return 40
    if '회계' in text: return 50
    return 60 

def is_enrolled_at_date(row, target_date):
    reg_str = safe_str(row.get('등록일', ''))
    if reg_str:
        reg_date = parse_date_safe(reg_str)
        if reg_date > target_date: return False
    s = safe_str(row.get('학교상태', '일반'))
    if s in INACTIVE_STATUS:
        change_str = safe_str(row.get('변동일', ''))
        if change_str:
            change_date = parse_date_safe(change_str)
            if change_date <= target_date: return False
        else: return False
    return True

def check_is_staff(row):
    s = safe_str(row.get('학교상태', ''))
    c = safe_str(row.get('학년(담임)', row.get('반', '')))
    m = safe_str(row.get('비고', ''))
    if s in ['교사', '교역자', '전도사', '목사']: return True
    if s in INACTIVE_STATUS:
        if any(k in c for k in ['교사', '교역자', '전도사', '목사', '임원']): return True
        if any(k in m for k in ['교사', '교역자', '전도사', '목사', '부장', '부감', '총무']): return True
    return False

def get_role(row):
    s = safe_str(row.get('학교상태', ''))
    c = safe_str(row.get('학년(담임)', row.get('반', '')))
    m = safe_str(row.get('비고', ''))
    if s in ['교역자', '전도사', '목사'] or any(k in m for k in ['전도사', '목사', '교역자']) or any(k in c for k in ['교역자', '전도사']):
        return 'pastor'
    if s == '교사' or any(k in c for k in ['교사', '임원']) or any(k in m for k in ['교사', '부장', '부감', '총무', '회계']):
        return 'teacher'
    return 'student'

def get_date_from_week_str(w_str):
    w_str = str(w_str).strip()
    if w_str.endswith('주'):
        try:
            w_num = int(w_str.replace('주', ''))
            return start_date + datetime.timedelta(days=(w_num-1)*7)
        except: pass
    return parse_date_safe(w_str)

def format_week_display(w_str):
    w_str = str(w_str).strip()
    d = get_date_from_week_str(w_str)
    if w_str.endswith('주'):
        return f"{w_str} ({d.strftime('%m/%d')})"
    return w_str

# --- 4. 구글 시트 데이터 연동 ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource
def get_worksheets():
    client = init_connection()
    sh = client.open_by_key("1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q")
    ws_m = sh.worksheet("교적부")
    try: ws_a = sh.worksheet("활동간식")
    except: ws_a = sh.add_worksheet("활동간식", 500, 15); ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항"] + [f"사진{i}" for i in range(1, 11)] + ["등록일"])
    try: ws_s = sh.worksheet("주차별통계")
    except: 
        ws_s = sh.add_worksheet("주차별통계", 200, 11)
        ws_s.append_row(["주차", "내용(비고)", "유년부 재적", "출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "업데이트일시"])
    return ws_m, ws_a, ws_s

@st.cache_data(ttl=600)
def fetch_sheet_data():
    ws_m, ws_a, ws_s = get_worksheets()
    return ws_m.get_all_values(), ws_a.get_all_values(), ws_s.get_all_values()

def get_all_data():
    try:
        ws_m, ws_a, ws_s = get_worksheets()
        vals_m, vals_a, vals_s = fetch_sheet_data()
        df_m = pd.DataFrame(vals_m[1:], columns=vals_m[0]) if len(vals_m) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        if not df_m.empty and '이름' in df_m.columns:
            df_m = df_m[df_m['이름'].astype(str).str.strip() != '']
            df_m = df_m[~df_m['이름'].isin(['None', 'nan', ''])]
        if '상태' in df_m.columns and '학교상태' not in df_m.columns: df_m.rename(columns={'상태': '학교상태'}, inplace=True)
        df_a = pd.DataFrame(vals_a[1:], columns=vals_a[0]) if len(vals_a) > 1 else pd.DataFrame()
        df_a['sheet_row'] = range(2, len(df_a) + 2)
        df_s = pd.DataFrame(vals_s[1:], columns=vals_s[0]) if len(vals_s) > 1 else pd.DataFrame()
        return ws_m, df_m, vals_m[0], ws_a, df_a, ws_s, df_s
    except Exception as e: return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat = get_all_data()

if df is None or df.empty:
    st.warning("⚠️ 데이터 로딩 중입니다. 잠시만 기다려주세요.")
    st.stop()

class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')
status_col = '학교상태' if '학교상태' in df.columns else '상태'

if '이름' in df.columns:
    valid_names_df = df[df['이름'].astype(str).str.strip() != '']
    dup_names = valid_names_df[valid_names_df.duplicated('이름', keep=False)]['이름'].unique()
    if len(dup_names) > 0:
        dup_details = []
        for n in dup_names:
            rows = valid_names_df[valid_names_df['이름'] == n]['sheet_row'].tolist()
            dup_details.append(f"[{n}: 구글시트 {rows}행]")
        st.error(f"🚨 **더블카운트 원인 발견 (데이터 중복):** 교적부 시트에 똑같은 이름이 2번 이상 등록된 사람이 있습니다! 구글 시트를 열어 중복된 행을 찾아 하나를 삭제해주세요.\n\n**🔍 중복 명단: {', '.join(dup_details)}**")

weeks_list = [f"{i}주" for i in range(1, 53)]
week_display_map = {f"{i}주": format_week_display(f"{i}주") for i in range(1, 53)}

# --- 모달 팝업용 수정 함수 ---
@st.dialog("📝 인원 정보 수정 팝업")
def edit_student_dialog(target_dict):
    st.info(f"💡 **{safe_str(target_dict.get('이름', ''))}** 님의 정보를 수정합니다.")
    with st.form("modal_edit_form"):
        col_i, col_f = st.columns([1, 2])
        if safe_str(target_dict.get('사진')) and str(target_dict['사진']).startswith('http'): 
            col_i.image(target_dict['사진'], use_container_width=True)
        
        c1, c2 = col_f.columns(2)
        e_name = c1.text_input("이름", value=safe_str(target_dict.get('이름','')))
        e_class = c2.text_input("학년(담임)", value=safe_str(target_dict.get(class_col,'')))
        
        bd_val = parse_date_safe(safe_str(target_dict.get('생년월일', '')))
        e_birth = c1.date_input("생년월일", value=bd_val, min_value=datetime.date(1900,1,1)).strftime("%Y-%m-%d")
        
        e_reg = c1.text_input("등록일 (YYYY-MM-DD)", value=safe_str(target_dict.get('등록일','')), placeholder="예: 2026-05-10")
        e_change = c2.text_input("변동일 (이사/졸업/타교회 등)", value=safe_str(target_dict.get('변동일','')), placeholder="변동 발생 날짜")
        
        e_school = c1.text_input("학교", value=safe_str(target_dict.get('학교','')))
        e_phone = c2.text_input("연락처", value=safe_str(target_dict.get('연락처','')))
        
        curr_s = safe_str(target_dict.get('학교상태', '일반'))
        e_status = col_f.selectbox("구분 (상태)", ALL_STATUS_OPTS, index=ALL_STATUS_OPTS.index(curr_s) if curr_s in ALL_STATUS_OPTS else 0)
        e_parents = col_f.text_input("부모", value=safe_str(target_dict.get('부모(아빠/엄마)','')))
        e_addr = col_f.text_input("주소", value=safe_str(target_dict.get('주소','')))
        e_memo = col_f.text_input("비고", value=safe_str(target_dict.get('비고','')))
        e_photo = col_f.file_uploader("사진변경")
        
        if st.form_submit_button("💾 정보 저장", type="primary", use_container_width=True):
            with st.spinner("저장 중..."):
                p_url = upload_photo(e_photo, e_name) if e_photo else safe_str(target_dict.get('사진',''))
                actual_headers = ws.row_values(1)
                
                missing_headers = [col for col in ['등록일', '변동일'] if col not in actual_headers]
                if missing_headers:
                    start_col = len(actual_headers) + 1
                    h_cells = []
                    for i, mh in enumerate(missing_headers):
                        actual_headers.append(mh)
                        h_cells.append(gspread.Cell(1, start_col + i, mh))
                    try:
                        chunked_update(ws, h_cells)
                    except Exception:
                        ws.add_cols(10)
                        chunked_update(ws, h_cells)
                
                r_idx = int(target_dict['sheet_row'])
                update_map = {'이름': e_name, '학년(담임)': e_class, '반': e_class, '생년월일': e_birth, '학교': e_school, '주소': e_addr, '부모(아빠/엄마)': e_parents, '연락처': e_phone, '비고': e_memo, '사진': p_url, '등록일': e_reg, '변동일': e_change}
                
                cells_to_update = []
                for k, v in update_map.items():
                    if k in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index(k)+1, str(v)))
                if '상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('상태')+1, e_status))
                elif '학교상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('학교상태')+1, e_status))
                
                if cells_to_update: chunked_update(ws, cells_to_update)
                fetch_sheet_data.clear(); st.rerun()

# --- 5. 화면(탭) 구성 ---
tabs = st.tabs(["🏫 반편성", "📋 교적부", "🎂 생일표", "🌱 새친구", "⚙️ 행사", "✅ 출석", "📊 통계"])

# ==========================================
# [탭 0] 반편성
# ==========================================
with tabs[0]:
    st.subheader("🏫 반별 명단")
    all_classes = sorted([c for c in df[class_col].unique() if str(c).strip()], key=class_sort_key)
    
    for i in range(0, len(all_classes), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(all_classes):
                c_name = all_classes[i+j]
                group = df[df[class_col] == c_name].copy()
                group['role'] = group.apply(get_role, axis=1)
                
                def get_sort_key(row):
                    s = row[status_col]
                    if s in INACTIVE_STATUS: return 100
                    if row['role'] in ['teacher', 'pastor']: return get_teacher_rank(row['이름'], row.get('비고', ''))
                    if s == '새친구': return 60
                    return 80
                    
                group['sort_key'] = group.apply(get_sort_key, axis=1)
                group = group.sort_values(by=['sort_key', '이름'])
                
                is_teacher_grp = any(k in str(c_name) for k in ['선생님', '교사'])
                is_pastor_grp = any(k in str(c_name) for k in ['교역자', '전도사', '목사'])
                
                if is_teacher_grp:
                    active_count = len(group[~group[status_col].isin(INACTIVE_STATUS) & (group['role'] == 'teacher')])
                    header_title = f"{c_name} ({active_count}명)"
                elif is_pastor_grp:
                    active_count = len(group[~group[status_col].isin(INACTIVE_STATUS) & (group['role'] == 'pastor')])
                    header_title = f"{c_name} ({active_count}명)"
                else:
                    active_count = len(group[~group[status_col].isin(INACTIVE_STATUS) & (group['role'] == 'student')])
                    header_title = f"{c_name} (학생 {active_count}명)"
                
                with cols[j]:
                    with st.container(border=True):
                        st.markdown(f"<h4 style='color:#0366d6; margin-bottom:10px; border-bottom:1px solid #eee;'>{header_title}</h4>", unsafe_allow_html=True)
                        btn_cols = st.columns(2)
                        for idx_j, (_, r) in enumerate(group.iterrows()):
                            s = r[status_col]
                            n = r['이름']
                            if r['role'] == 'pastor': label = f"✝️ {n}"
                            elif r['role'] == 'teacher': label = f"🧑‍🏫 {n}"
                            elif s == '새친구': label = f"🔴 {n}"
                            elif s in INACTIVE_STATUS: label = f"🚫 {n} ({s})"
                            else: label = f"👤 {n}"
                            
                            with btn_cols[idx_j % 2]:
                                if st.button(label, key=f"btn_link_{r['sheet_row']}", help="클릭하여 즉시 정보 수정", use_container_width=True):
                                    edit_student_dialog(r.to_dict())
                        
                        with st.expander(f"➕ 새친구 추가"):
                            with st.form(f"qa_{i+j}"):
                                new_n = st.text_input("새친구 이름", placeholder="이름 입력")
                                if st.form_submit_button("등록"):
                                    if new_n:
                                        new_row = [""] * len(headers)
                                        h_map = {str(h): idx for idx, h in enumerate(headers)}
                                        if '학생ID' in h_map: new_row[h_map['학생ID']] = f"S-{datetime.datetime.now().strftime('%y%m')}-{str(uuid.uuid4())[:4].upper()}"
                                        if '이름' in h_map: new_row[h_map['이름']] = new_n
                                        if class_col in h_map: new_row[h_map[class_col]] = c_name
                                        if '생년월일' in h_map: new_row[h_map['생년월일']] = datetime.date.today().strftime("%Y-%m-%d")
                                        if '학교상태' in h_map: new_row[h_map['학교상태']] = "새친구"
                                        elif '상태' in h_map: new_row[h_map['상태']] = "새친구"
                                        ws.append_row(new_row); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 1] 교적부 통합 관리
# ==========================================
with tabs[1]:
    st.subheader("📋 교적부 통합 관리")
    df['role'] = df.apply(get_role, axis=1)
    df['is_staff_flag'] = df.apply(check_is_staff, axis=1)
    
    active_students = df[(df['role'] == 'student') & (~df[status_col].isin(INACTIVE_STATUS))]
    st_count = len(active_students[active_students[status_col] == '일반'])
    new_count = len(active_students[active_students[status_col] == '새친구'])
    
    active_staff = df[(df['role'].isin(['teacher', 'pastor'])) & (~df[status_col].isin(INACTIVE_STATUS))]
    tc_count = len(active_staff[active_staff['role'] == 'teacher'])
    ps_count = len(active_staff[active_staff['role'] == 'pastor'])
    
    mv_count = len(df[df[status_col] == '이사'])
    gr_count = len(df[df[status_col] == '졸업'])
    other_ch_count = len(df[df[status_col] == '타교회'])
    inact_count = len(df[df[status_col] == '비활성'])
    total_inact = mv_count + gr_count + other_ch_count + inact_count
    
    st.markdown("##### 👥 전체 인원 현황 (Live)")
    dash_r1_1, dash_r1_2 = st.columns(2)
    dash_r1_1.metric("총 재적 (유년부)", f"{st_count + new_count}명", f"일반 {st_count}명 / 새친구 {new_count}명")
    dash_r1_2.metric("사역자 (선생님/교역자)", f"{tc_count + ps_count}명", f"선생님 {tc_count}명 / 전도사님, 목사님 {ps_count}명")
    
    dash_r2_1, dash_r2_2 = st.columns(2)
    dash_r2_1.metric("비활성 총합 (이사/졸업/타교회/단순비활성)", f"{total_inact}명", f"이사 {mv_count} / 졸업 {gr_count} / 타교회 {other_ch_count} / 단순비활성 {inact_count}")
    
    active_sum_calc = len(df) - total_inact
    dash_r2_2.metric("실제 활동 데이터 총합", f"{active_sum_calc}명", f"전체 DB {len(df)}명 - 비활성 제외")
    st.divider()
    
    manage_mode = st.radio("작업 모드", ["👀 전체보기", "📝 수정/비활성", "➕ 인원추가"], horizontal=True)
    req_cols = ['학생ID', '학년(담임)', '이름', '학교상태', '등록일', '변동일', '학교', '부모(아빠/엄마)', '연락처', '주소', '비고']
    available_cols = [c for c in req_cols if c in df.columns]
    
    if manage_mode == "👀 전체보기":
        st.dataframe(df[available_cols], use_container_width=True, hide_index=True)
        
    elif manage_mode == "📝 수정/비활성":
        search_list = ["학생 선택"] + df.apply(lambda r: f"{r['이름']} | {r.get(class_col,'')} ({r.get('학교상태','일반')})", axis=1).tolist()
        sel_idx = st.selectbox("수정할 인원 선택", range(len(search_list)), format_func=lambda x: search_list[x])
        if sel_idx > 0:
            target = df.iloc[sel_idx - 1]
            edit_student_dialog(target.to_dict())
                    
    elif manage_mode == "➕ 인원추가":
        with st.form("add_new"):
            col1, col2 = st.columns(2)
            n_name = col1.text_input("이름 (필수)")
            n_class = col1.text_input("학년(담임) (필수)")
            n_status = col2.selectbox("구분", ALL_STATUS_OPTS, index=1)
            n_reg = col1.date_input("등록일자", value=datetime.date.today()).strftime("%Y-%m-%d")
            n_photo = st.file_uploader("사진 첨부")
            if st.form_submit_button("✨ 등록하기"):
                if n_name and n_class:
                    p_url = upload_photo(n_photo, n_name)
                    new_row = [""] * len(headers)
                    h_map = {str(h): i for i, h in enumerate(headers)}
                    if '학생ID' in h_map: new_row[h_map['학생ID']] = f"S-{datetime.datetime.now().strftime('%y%m')}-{str(uuid.uuid4())[:4].upper()}"
                    if '이름' in h_map: new_row[h_map['이름']] = n_name
                    if class_col in h_map: new_row[h_map[class_col]] = n_class
                    if '생년월일' in h_map: new_row[h_map['생년월일']] = "2015-01-01"
                    if '등록일' in h_map: new_row[h_map['등록일']] = n_reg
                    if '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                    elif '상태' in h_map: new_row[h_map['상태']] = n_status
                    if '사진' in h_map: new_row[h_map['사진']] = p_url
                    ws.append_row(new_row); fetch_sheet_data.clear(); st.success("등록 완료!"); st.rerun()

# ==========================================
# [탭 2, 3] 생일표, 새친구
# ==========================================
with tabs[2]:
    st.subheader("🎂 월별 생일 명단")
    b_map = {i: [] for i in range(1, 13)}
    
    bd_df = df[~df[status_col].isin(INACTIVE_STATUS)].copy()
    bd_df['role'] = bd_df.apply(get_role, axis=1)
    
    for _, r in bd_df.iterrows():
        b = str(r.get('생년월일', ''))
        if '-' in b and len(b.split('-')) == 3:
            try: 
                m, d = int(b.split('-')[1]), int(b.split('-')[2])
                b_map[m].append({"name": r['이름'], "class": r.get(class_col,''), "day": d, "role": r['role']})
            except: pass
            
    for row_idx in range(4):
        cols = st.columns(3)
        for col_idx in range(3):
            m = row_idx * 3 + col_idx + 1
            with cols[col_idx]:
                with st.container(border=True):
                    st.markdown(f"<h4 style='color:#0366d6; margin-bottom:0px;'>📅 {m}월</h4>", unsafe_allow_html=True); st.divider()
                    for p in sorted(b_map[m], key=lambda x: x["day"]):
                        if p['role'] == 'pastor':
                            n_disp = f"<span style='color:#2E7D32;'>✝️ <b>{p['name']}</b></span>"
                        elif p['role'] == 'teacher':
                            n_disp = f"<span style='color:#E91E63;'>🧑‍🏫 <b>{p['name']}</b></span>"
                        else:
                            n_disp = f"<span>🎈 <b>{p['name']}</b></span>"
                        
                        st.markdown(f"<div style='display:flex; justify-content:space-between; margin-bottom:5px;'>{n_disp} <span style='font-size:0.8rem; color:gray;'>({p['class']})</span><strong style='color:#e65100;'>{p['day']}일</strong></div>", unsafe_allow_html=True)

with tabs[3]:
    st.subheader("🌱 최근 등록 새친구")
    news = df[df[status_col] == '새친구']
    if not news.empty: st.dataframe(news[available_cols], use_container_width=True, hide_index=True)
    else: st.info("등록된 새친구가 없습니다.")

# ==========================================
# [탭 4] 행사 기록 관리
# ==========================================
with tabs[4]:
    st.subheader("⚙️ 행사 기록 관리")
    e_mode = st.radio("작업", ["📂 보기", "📝 수정", "🚨 삭제", "➕ 등록"], horizontal=True)
    
    def format_event(row_id):
        if row_id == "행사 선택": return "행사 선택"
        match = df_act[df_act['sheet_row'] == row_id]
        if not match.empty:
            return f"{match.iloc[0].get('날짜','')} | {match.iloc[0].get('활동명','')}"
        return "알 수 없음"

    if e_mode == "📂 보기" and not df_act.empty:
        view_act_df = df_act.copy()
        view_act_df['sort_date'] = pd.to_datetime(view_act_df['날짜'], errors='coerce')
        view_act_df = view_act_df.sort_values(by=['sort_date', 'sheet_row'], ascending=[False, False])
        
        for _, row in view_act_df.iterrows():
            with st.container(border=True):
                st.markdown(f"<h3 style='margin-top:0; color:#0366d6;'>📅 {row.get('날짜', '')} | {row.get('활동명', '')}</h3>", unsafe_allow_html=True)
                st.write(f"**내용:** {row.get('세부내용', '')}")
                if str(row.get('공지사항', '')).strip():
                    st.markdown(f"**<span style='color: #d32f2f;'>공지:</span>** <span style='color: #d32f2f;'>{row.get('공지사항', '')}</span>", unsafe_allow_html=True)
                
                valid_urls = [row.get(f'사진{i}', "") for i in range(1, 11) if str(row.get(f'사진{i}', "")).startswith('http')]
                if valid_urls:
                    st.markdown("---")
                    # [핵심 보완] 1/2 축소를 위해 5열 구조로 변경
                    for i in range(0, len(valid_urls), 5):
                        p_cols = st.columns(5)
                        for j, media_url in enumerate(valid_urls[i:i+5]):
                            with p_cols[j]:
                                # [핵심 보완] 동영상과 사진 분기 처리 (네이티브 확대 적용 위해 링크 삭제)
                                if any(ext in str(media_url).lower() for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv']):
                                    st.video(media_url)
                                else:
                                    st.image(media_url, use_container_width=True)
                    
    elif e_mode == "📝 수정" and not df_act.empty:
        event_options = ["행사 선택"] + df_act['sheet_row'].tolist()
        sel_edit = st.selectbox("수정할 행사 선택", event_options, format_func=format_event)
        
        if sel_edit != "행사 선택":
            target_row_id = int(sel_edit)
            target_event = df_act[df_act['sheet_row'] == target_row_id].iloc[0]
            
            with st.form("edit_event_form"):
                e_d_val = parse_date_safe(target_event.get('날짜', ''))
                e_d = st.date_input("날짜", value=e_d_val)
                e_t = st.text_input("행사명", value=target_event.get('활동명', ''))
                e_c = st.text_area("내용", value=target_event.get('세부내용', ''))
                e_n = st.text_input("공지사항", value=target_event.get('공지사항', ''))
                
                st.write("📸 개별 사진/동영상 수정 (기존 미디어를 삭제하거나 새 미디어로 덮어쓸 수 있습니다)")
                old_urls = [""] * 10
                for i in range(1, 11):
                    url = target_event.get(f'사진{i}', "")
                    old_urls[i-1] = url
                
                new_files = [None] * 10
                delete_flags = [False] * 10
                
                # [핵심 보완] 5열로 변경하여 사진 10장이 2줄로 꽉 차게 나열됨
                for i in range(0, 10, 5):
                    p_cols = st.columns(5)
                    for j in range(5):
                        idx = i + j
                        with p_cols[j]:
                            media_url = old_urls[idx]
                            if media_url and str(media_url).startswith('http'):
                                if any(ext in str(media_url).lower() for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv']):
                                    st.video(media_url)
                                else:
                                    st.image(media_url, use_container_width=True)
                                
                                delete_flags[idx] = st.checkbox(f"[{idx+1}] 삭제", key=f"del_img_{target_row_id}_{idx}")
                                new_files[idx] = st.file_uploader(f"[{idx+1}] 변경", key=f"up_img_{target_row_id}_{idx}", label_visibility="collapsed", type=['png','jpg','jpeg','mp4','mov','avi'])
                            else:
                                st.markdown(f"**[{idx+1}] 빈 칸**")
                                new_files[idx] = st.file_uploader(f"[{idx+1}] 추가", key=f"add_img_{target_row_id}_{idx}", label_visibility="collapsed", type=['png','jpg','jpeg','mp4','mov','avi'])
                
                if st.form_submit_button("📝 행사 수정 저장", type="primary"):
                    with st.spinner("개별 사진 및 내용 수정 중..."):
                        final_urls = old_urls.copy()
                        for k in range(10):
                            if new_files[k] is not None:
                                final_urls[k] = upload_photo(new_files[k], e_t)
                            elif delete_flags[k]:
                                final_urls[k] = ""
                                
                        act_sh_headers = ws_act.row_values(1)
                        missing_act = [col for col in [f"사진{idx}" for idx in range(1, 11)] if col not in act_sh_headers]
                        if missing_act:
                            start_col = len(act_sh_headers) + 1
                            h_cells = []
                            for i, mh in enumerate(missing_act):
                                act_sh_headers.append(mh)
                                h_cells.append(gspread.Cell(1, start_col + i, mh))
                            try:
                                chunked_update(ws_act, h_cells)
                            except Exception:
                                ws_act.add_cols(10)
                                chunked_update(ws_act, h_cells)
                                
                        update_map = {"날짜": str(e_d.strftime("%Y-%m-%d")), "활동명": e_t, "세부내용": e_c, "공지사항": e_n}
                        for k in range(1, 11): update_map[f"사진{k}"] = final_urls[k-1]
                            
                        cells_to_update = []
                        for k, v in update_map.items():
                            if k in act_sh_headers: cells_to_update.append(gspread.Cell(target_row_id, act_sh_headers.index(k)+1, str(v)))
                                
                        if cells_to_update: chunked_update(ws_act, cells_to_update)
                        fetch_sheet_data.clear(); st.success("개별 수정이 완료되었습니다!"); st.rerun()

    elif e_mode == "🚨 삭제" and not df_act.empty:
        event_options = ["행사 선택"] + df_act['sheet_row'].tolist()
        sel_del = st.selectbox("삭제할 행사", event_options, format_func=format_event)
        if st.button("🚨 삭제 실행"): 
            if sel_del != "행사 선택":
                ws_act.delete_rows(int(sel_del))
                fetch_sheet_data.clear(); st.success("삭제되었습니다!"); st.rerun()
        
    elif e_mode == "➕ 등록":
        with st.form("new_e"):
            a_d = st.date_input("날짜"); a_t = st.text_input("행사명"); a_c = st.text_area("내용"); a_n = st.text_input("공지사항")
            a_f = st.file_uploader("사진 및 동영상 (최대 10개)", accept_multiple_files=True, type=['png','jpg','jpeg','mp4','mov','avi'])
            if st.form_submit_button("저장"):
                urls = [""] * 10
                if a_f: 
                    for i, f in enumerate(a_f[:10]): urls[i] = upload_photo(f, a_t)
                
                act_sh_headers = ws_act.row_values(1)
                missing_act = [col for col in [f"사진{idx}" for idx in range(1, 11)] if col not in act_sh_headers]
                if missing_act:
                    start_col = len(act_sh_headers) + 1
                    h_cells = []
                    for i, mh in enumerate(missing_act):
                        act_sh_headers.append(mh)
                        h_cells.append(gspread.Cell(1, start_col + i, mh))
                    try:
                        chunked_update(ws_act, h_cells)
                    except Exception:
                        ws_act.add_cols(10)
                        chunked_update(ws_act, h_cells)
                
                act_sh_headers = ws_act.row_values(1)
                h_map = {str(h): idx for idx, h in enumerate(act_sh_headers)}
                new_row = [""] * len(act_sh_headers)
                
                if "날짜" in h_map: new_row[h_map["날짜"]] = str(a_d.strftime("%Y-%m-%d"))
                if "활동명" in h_map: new_row[h_map["활동명"]] = a_t
                if "세부내용" in h_map: new_row[h_map["세부내용"]] = a_c
                if "공지사항" in h_map: new_row[h_map["공지사항"]] = a_n
                if "등록일" in h_map: new_row[h_map["등록일"]] = str(datetime.datetime.now())
                
                for k in range(1, 11):
                    if f"사진{k}" in h_map: new_row[h_map[f"사진{k}"]] = urls[k-1]
                
                ws_act.append_row(new_row)
                fetch_sheet_data.clear(); st.success("저장 완료!"); st.rerun()

# ==========================================
# [탭 5] 출석
# ==========================================
with tabs[5]:
    st.subheader("📅 주간 출석 현황")
    extended_weeks_list = weeks_list + ["✏️ 직접 입력 (새 날짜)"]
    
    c1, c2 = st.columns(2)
    with c1: 
        sel_w_raw = st.selectbox("출석 주차 / 기준일", extended_weeks_list, index=max(0, min(51, datetime.date.today().isocalendar()[1] - 1)), format_func=lambda x: week_display_map.get(x, x))
        if sel_w_raw == "✏️ 직접 입력 (새 날짜)": 
            target_date = st.date_input("새로운 날짜 선택", datetime.date.today())
            sel_w = target_date.strftime("%Y-%m-%d")
        else: 
            sel_w = sel_w_raw
            w_num = int(sel_w_raw.replace("주", ""))
            target_date = start_date + datetime.timedelta(days=(w_num-1)*7)
            
    with c2: 
        sel_class = st.selectbox("반 필터", ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()], key=class_sort_key))
    
    show_inactive = st.checkbox("👀 강제 전체명단 표시 (등록전/이사후 등 모든 명단 수정용)")
    
    if show_inactive:
        att_df = df.copy()
    else:
        att_df = df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
        
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
    
    att_df['role'] = att_df.apply(get_role, axis=1)
    ui_s_df = att_df[att_df['role'] == 'student']
    ui_t_df = att_df[att_df['role'] == 'teacher']
    
    s_p = len(ui_s_df[ui_s_df[sel_w].astype(str).str.strip() == "1"])
    t_p = len(ui_t_df[ui_t_df[sel_w].astype(str).str.strip() == "1"])
    
    saved_guest = 0; saved_note = ""
    if not df_stat.empty and '주차' in df_stat.columns:
        match = df_stat[df_stat['주차'] == sel_w]
        if not match.empty: 
            try: saved_guest = int(match.iloc[0].get('추가', match.iloc[0].get('새친구/추가예배', 0)))
            except: pass
            saved_note = match.iloc[0].get('내용(비고)', match.iloc[0].get('비고', ''))

    st.markdown("#### 📊 현재 체크 현황 (수정/저장 전)")
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric(f"유년부 출석 (재적 {len(ui_s_df)})", f"{s_p}명")
    cs2.metric(f"선생님 출석 (재적 {len(ui_t_df)})", f"{t_p}명") 
    cs3.metric("유년부 합계 (출석+추가)", f"{s_p + saved_guest}명")
    guest_in = cs4.number_input("🎉 미등록 새친구/추가예배", min_value=0, value=saved_guest)
    
    st.markdown("---")
    col_ex1, col_ex2 = st.columns([1, 3])
    is_skip = col_ex1.toggle("⚠️ 출석체크 쉼 (행사/예외)", value=bool(saved_note))
    note_text = col_ex2.text_input("행사명/내용(비고)", value=saved_note)

    calc_total = guest_in if is_skip else (s_p + t_p + guest_in)
    st.markdown(f"<div class='total-summary'>✅ 저장 시 총합계 (선생님 포함): {calc_total}명</div>", unsafe_allow_html=True)

    with st.form("att_toggle_form"):
        new_att = {}
        if not is_skip:
            grouped = att_df.sort_values(by=['이름']).groupby(class_col)
            for c_name in sorted(grouped.groups.keys(), key=class_sort_key):
                group = grouped.get_group(c_name)
                st.markdown(f"<div class='class-header'>🏷️ {c_name}</div>", unsafe_allow_html=True)
                cols = st.columns(3)
                for i, (idx, row) in enumerate(group.iterrows()):
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    prefix = f"🚫 " if row[status_col] in INACTIVE_STATUS else ("🌱 " if row[status_col] == '새친구' else "✝️ " if row['role'] == 'pastor' else "🧑‍🏫 " if row['role'] == 'teacher' else "👤 ")
                    label = f"{prefix}{row['이름']}"
                    new_att[row['sheet_row']] = cols[i%3].toggle(label, value=is_on, key=f"tgl_{row['sheet_row']}_{sel_w}")
        
        if st.form_submit_button("💾 데이터 저장 (교적부/통계 반영)", type="primary", use_container_width=True):
            with st.spinner("안전하게 일괄 저장 중..."):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: 
                    try:
                        ws.update_cell(1, target_c, sel_w)
                    except Exception:
                        ws.add_cols(10)
                        ws.update_cell(1, target_c, sel_w)
                
                final_s_p = 0; final_t_p = 0; cells_to_update = []
                if not is_skip:
                    for r, v in new_att.items():
                        row_data = att_df[att_df['sheet_row'] == r]
                        is_teacher_person = False; is_pastor_person = False
                        if not row_data.empty:
                            if row_data.iloc[0]['role'] == 'teacher': is_teacher_person = True
                            elif row_data.iloc[0]['role'] == 'pastor': is_pastor_person = True
                        cells_to_update.append(gspread.Cell(int(r), target_c, "1" if v else ""))
                        if v:
                            if is_teacher_person: final_t_p += 1
                            elif not is_pastor_person: final_s_p += 1 
                    if cells_to_update: chunked_update(ws, cells_to_update)
                
                save_s_p = 0 if is_skip else final_s_p
                save_t_p = 0 if is_skip else final_t_p
                
                valid_enrollment_df = df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
                valid_enrollment_df['role'] = valid_enrollment_df.apply(get_role, axis=1)
                
                strict_teacher_df = valid_enrollment_df[valid_enrollment_df['role'] == 'teacher']
                strict_student_df = valid_enrollment_df[valid_enrollment_df['role'] == 'student']
                
                student_count = len(strict_student_df)
                teacher_count = len(strict_teacher_df)
                kids_total = save_s_p + guest_in
                grand_total = kids_total + save_t_p
                
                stat_data = [
                    sel_w, note_text, student_count, save_s_p, guest_in, 
                    kids_total, teacher_count, save_t_p, grand_total, 
                    str(datetime.datetime.now())
                ]
                
                match_stat = df_stat[df_stat['주차'] == sel_w] if not df_stat.empty else pd.DataFrame()
                if not match_stat.empty: ws_stat.update(f"A{match_stat.index[0]+2}:J{match_stat.index[0]+2}", [stat_data])
                else: ws_stat.append_row(stat_data)
                fetch_sheet_data.clear(); st.success(f"[{sel_w}] 동적 재적 기반 데이터 저장 완료!"); st.rerun()

    with st.expander("📊 연간 출석 현황 에디터 (일괄 수정)"):
        week_cols = [c for c in df.columns if c.endswith('주') or (c.count('-')==2 and len(c)>=8)]
        if show_inactive: annual_df = df[[class_col, '이름', '학교상태', 'sheet_row'] + week_cols].copy()
        else: annual_df = df[~df[status_col].isin(INACTIVE_STATUS)][[class_col, '이름', '학교상태', 'sheet_row'] + week_cols].copy()
        for w in week_cols: annual_df[w] = annual_df[w].apply(lambda x: True if str(x).strip() == "1" else False)
        edited_annual = st.data_editor(annual_df, hide_index=True, use_container_width=True, column_config={w: st.column_config.CheckboxColumn(w) for w in week_cols})
        if st.button("📝 연간 데이터 수정사항 서버에 반영"):
            with st.spinner("동기화 중..."):
                cells_to_update = []
                for r in range(len(annual_df)):
                    for w in week_cols:
                        if annual_df.iloc[r][w] != edited_annual.iloc[r][w]:
                            cells_to_update.append(gspread.Cell(int(annual_df.iloc[r]['sheet_row']), headers.index(w) + 1, "1" if edited_annual.iloc[r][w] else ""))
                if cells_to_update: chunked_update(ws, cells_to_update, chunk_size=200)
                fetch_sheet_data.clear(); st.success("업데이트 완료!"); st.rerun()

# ==========================================
# [탭 6] 통계
# ==========================================
def highlight_zero_attendance(row):
    try: att = int(row['출석'])
    except: att = -1
    if att == 0: return ['background-color: #ffebee; color: #d32f2f;' for _ in row.index]
    return ['' for _ in row.index]

with tabs[6]:
    st.subheader("📊 통계")
    show_all_stats = st.checkbox("📥 엑셀/통계 추출 시 비활성 인원 기록 포함하기", value=True)
    week_cols = [c for c in df.columns if c.endswith('주') or (c.count('-')==2 and len(c)>=8)]
    if show_all_stats: report_df = df[[class_col, '이름', '학교상태'] + week_cols].copy()
    else: report_df = df[~df[status_col].isin(INACTIVE_STATUS)][[class_col, '이름', '학교상태'] + week_cols].copy()
    report_df['출석수'] = report_df[week_cols].apply(lambda x: x.astype(str).str.strip().eq('1').sum(), axis=1)
    
    col_stat, col_cumul = st.columns([2, 1])
    
    with col_stat: 
        st.write("📅 **주차별 통계 (시계열 역산 적용)**")
        if not df_stat.empty:
            df_stat_calc = df_stat.copy()
            df_stat_calc['sort_date'] = df_stat_calc['주차'].apply(get_date_from_week_str)
            df_stat_calc = df_stat_calc.sort_values(by='sort_date').drop(columns=['sort_date'])
            
            rename_dict = {'비고': '내용(비고)', '학생재적': '유년부 재적', '학생출석': '출석', '새친구(기타)': '추가', '새친구/추가예배': '추가', '총합계': '총합'}
            df_stat_renamed = df_stat_calc.rename(columns=rename_dict)
            preferred_order = ["주차", "내용(비고)", "유년부 재적", "출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "업데이트일시"]
            
            for idx, row_st in df_stat_renamed.iterrows():
                t_date = get_date_from_week_str(row_st['주차'])
                v_df = df[df.apply(lambda r: is_enrolled_at_date(r, t_date), axis=1)].copy()
                v_df['role'] = v_df.apply(get_role, axis=1)
                s_c = len(v_df[v_df['role'] == 'student'])
                t_c = len(v_df[v_df['role'] == 'teacher'])
                df_stat_renamed.at[idx, '유년부 재적'] = str(s_c)
                df_stat_renamed.at[idx, '교사재적'] = str(t_c)
            
            if '유년부 합계' not in df_stat_renamed.columns:
                try: df_stat_renamed['유년부 합계'] = pd.to_numeric(df_stat_renamed['출석'], errors='coerce').fillna(0) + pd.to_numeric(df_stat_renamed['추가'], errors='coerce').fillna(0)
                except: pass
            else:
                try: df_stat_renamed['유년부 합계'] = pd.to_numeric(df_stat_renamed['출석'], errors='coerce').fillna(0) + pd.to_numeric(df_stat_renamed['추가'], errors='coerce').fillna(0)
                except: pass
                
            actual_order = [c for c in preferred_order if c in df_stat_renamed.columns]
            for c in df_stat_renamed.columns:
                if c not in actual_order and c != '출석률': actual_order.append(c)
                
            df_stat_display = df_stat_renamed[actual_order]
            df_stat_display['주차'] = df_stat_display['주차'].apply(format_week_display)
            
            style_cols = [c for c in ['유년부 합계', '총합'] if c in df_stat_display.columns]
            
            styled_df = df_stat_display.style.apply(highlight_zero_attendance, axis=1)
            if style_cols:
                styled_df = styled_df.set_properties(subset=style_cols, **{'font-weight': 'bold', 'color': '#0366d6'})
                
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            csv_data_weekly = df_stat_calc.to_csv(index=False).encode('utf-8-sig')
        else:
            st.dataframe(df_stat, use_container_width=True, hide_index=True)
            csv_data_weekly = df_stat.to_csv(index=False).encode('utf-8-sig')
        
        st.download_button("📅 주차별 흐름 통계 다운로드 (CSV)", data=csv_data_weekly, file_name=f"주차별통계_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)
            
    with col_cumul: 
        st.write("👤 **개인별 누적 출석**")
        st.dataframe(report_df[[class_col, '이름', '출석수']], use_container_width=True, hide_index=True)
        st.download_button("📊 개인별 누적 통계 다운로드 (CSV)", data=report_df.to_csv(index=False).encode('utf-8-sig'), file_name=f"개인별통계_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)
