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
st.set_page_config(page_title="유년부 통합 관리 v37.6", page_icon="🌱", layout="wide")

INACTIVE_STATUS = ['이사', '비활성', '졸업']
ALL_STATUS_OPTS = ["일반", "새친구", "교사", "교역자", "전도사", "목사", "이사", "비활성", "졸업"]

st.markdown("""
    <style>
    .class-header { background-color: #f1f8ff; padding: 12px 15px; border-radius: 8px; color: #0366d6; font-weight: 800; font-size: 1.1rem; margin-top: 20px; margin-bottom: 15px; border-left: 5px solid #0366d6; }
    div[data-testid="stToggle"] { border: 2px solid #eef2f6; padding: 12px 18px; border-radius: 16px; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.2s ease-in-out; margin-bottom: 10px; }
    div[data-testid="stToggle"]:hover { border-color: #0366d6; background-color: #f8fbff; }
    .total-summary { background-color: #e6f2ff; padding: 15px; border-radius: 10px; text-align: center; color: #005bb5; font-size: 1.2rem; font-weight: bold; margin-bottom: 20px; }
    .event-card { border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin-bottom: 15px; background-color: #fafafa; }
    div[data-testid="stButton"] button { width: 100%; border-radius: 6px; text-align: left; padding: 4px 8px; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 시스템 접근 제어 ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("## 🔒 슈팅스타 시스템 접근 제어")
    pwd = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("로그인"):
        if "admin_password" in st.secrets and pwd == st.secrets["admin_password"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")
    st.stop()

if "GOOGLE_PROXY_URL" in st.secrets: GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else: st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!"); st.stop()

# --- 3. 공통 유틸리티 함수 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        headers = {"Authorization": f"Bearer {st.secrets.get('PROXY_AUTH_KEY', '')}"} if "PROXY_AUTH_KEY" in st.secrets else {}
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}, headers=headers, timeout=10)
        res.raise_for_status()
        return res.json().get("fileUrl", "")
    except Exception as e: return ""

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
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

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
    reg_str = str(row.get('등록일', '')).strip()
    if reg_str:
        reg_date = parse_date_safe(reg_str)
        if reg_date > target_date: return False
    if row.get('학교상태', '일반') in INACTIVE_STATUS:
        change_str = str(row.get('변동일', '')).strip()
        if change_str:
            change_date = parse_date_safe(change_str)
            if change_date <= target_date: return False
        else: return False
    return True

def check_is_staff(row):
    s = str(row.get('학교상태', '')).strip()
    c = str(row.get('학년(담임)', row.get('반', ''))).strip()
    m = str(row.get('비고', '')).strip()
    if s in ['교사', '교역자', '전도사', '목사']: return True
    if s in INACTIVE_STATUS:
        if any(k in c for k in ['교사', '교역자', '전도사', '목사', '임원']): return True
        if any(k in m for k in ['교사', '교역자', '전도사', '목사', '부장', '부감', '총무']): return True
    return False

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
    except: ws_a = sh.add_worksheet("활동간식", 500, 10); ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
    try: ws_s = sh.worksheet("주차별통계")
    except: ws_s = sh.add_worksheet("주차별통계", 200, 10); ws_s.append_row(["주차", "학생재적", "학생출석", "교사재적", "교사출석", "새친구/추가예배", "총합계", "학생출석률", "비고", "업데이트일시"])
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
        
        # 줄 번호를 먼저 부여해야 업데이트 시 위치가 꼬이지 않음
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        # [유령 행 제거 로직] 이름 칸이 비어있는 쓰레기 데이터는 메모리에서 원천 삭제!
        if not df_m.empty and '이름' in df_m.columns:
            df_m = df_m[df_m['이름'].astype(str).str.strip() != '']
            
        if '상태' in df_m.columns and '학교상태' not in df_m.columns: df_m.rename(columns={'상태': '학교상태'}, inplace=True)
        
        df_a = pd.DataFrame(vals_a[1:], columns=vals_a[0]) if len(vals_a) > 1 else pd.DataFrame()
        df_a['sheet_row'] = range(2, len(df_a) + 2)
        df_s = pd.DataFrame(vals_s[1:], columns=vals_s[0]) if len(vals_s) > 1 else pd.DataFrame()
        return ws_m, df_m, vals_m[0], ws_a, df_a, ws_s, df_s
    except Exception as e: return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat = get_all_data()

if df is None or df.empty:
    st.warning("⚠️ 구글 시트 데이터가 비어있습니다. 약 1분 후 새로고침 해주세요.")
    st.stop()

class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')
status_col = '학교상태' if '학교상태' in df.columns else '상태'

# 동명이인 / 중복 등록 자동 탐지기
if '이름' in df.columns:
    valid_names_df = df[df['이름'].astype(str).str.strip() != '']
    dup_names = valid_names_df[valid_names_df.duplicated('이름', keep=False)]['이름'].unique()
    if len(dup_names) > 0:
        dup_details = []
        for n in dup_names:
            rows = valid_names_df[valid_names_df['이름'] == n]['sheet_row'].tolist()
            dup_details.append(f"[{n}: 구글시트 {rows}행]")
        st.error(f"🚨 **더블카운트 원인 발견 (데이터 중복):** 교적부 시트에 똑같은 이름이 2번 이상 등록된 사람이 있습니다! 이 때문에 1명이 2명으로 카운트됩니다. 구글 시트를 열어 중복된 행을 찾아 하나를 삭제해주세요.\n\n**🔍 중복 명단: {', '.join(dup_details)}**")

start_date = datetime.date(2026, 1, 4)
weeks_list = [f"{i}주" for i in range(1, 53)]
week_display_map = {f"{i}주": f"{i}주 ({ (start_date + datetime.timedelta(days=(i-1)*7)).strftime('%m/%d') })" for i in range(1, 53)}

# --- 모달 팝업용 수정 함수 ---
@st.dialog("📝 인원 정보 수정 팝업")
def edit_student_dialog(target_dict):
    st.info(f"💡 **{target_dict.get('이름', '')}** 님의 정보를 수정합니다.")
    with st.form("modal_edit_form"):
        col_i, col_f = st.columns([1, 2])
        if target_dict.get('사진') and str(target_dict['사진']).startswith('http'): 
            col_i.image(target_dict['사진'], use_container_width=True)
        
        c1, c2 = col_f.columns(2)
        e_name = c1.text_input("이름", value=target_dict.get('이름',''))
        e_class = c2.text_input("학년(담임)", value=target_dict.get(class_col,''))
        e_birth = c1.date_input("생년월일", value=parse_date_safe(target_dict.get('생년월일', '')), min_value=datetime.date(1900,1,1)).strftime("%Y-%m-%d")
        e_reg = c1.text_input("등록일 (YYYY-MM-DD)", value=target_dict.get('등록일',''), placeholder="예: 2026-05-10")
        e_change = c2.text_input("변동일 (이사/졸업)", value=target_dict.get('변동일',''), placeholder="이사/졸업 날짜")
        e_school = c1.text_input("학교", value=target_dict.get('학교',''))
        e_phone = c2.text_input("연락처", value=target_dict.get('연락처',''))
        
        curr_s = target_dict.get('학교상태', '일반')
        e_status = col_f.selectbox("구분 (상태)", ALL_STATUS_OPTS, index=ALL_STATUS_OPTS.index(curr_s) if curr_s in ALL_STATUS_OPTS else 0)
        e_parents = col_f.text_input("부모", value=target_dict.get('부모(아빠/엄마)',''))
        e_addr = col_f.text_input("주소", value=target_dict.get('주소',''))
        e_memo = col_f.text_input("비고", value=target_dict.get('비고',''))
        e_photo = col_f.file_uploader("사진변경")
        
        c_btn1, c_btn2 = st.columns(2)
        if c_btn1.form_submit_button("💾 정보 저장"):
            with st.spinner("저장 중..."):
                p_url = upload_photo(e_photo, e_name) if e_photo else target_dict.get('사진','')
                actual_headers = ws.row_values(1)
                r_idx = int(target_dict['sheet_row'])
                update_map = {'이름': e_name, '학년(담임)': e_class, '반': e_class, '생년월일': e_birth, '학교': e_school, '주소': e_addr, '부모(아빠/엄마)': e_parents, '연락처': e_phone, '비고': e_memo, '사진': p_url, '등록일': e_reg, '변동일': e_change}
                
                cells_to_update = []
                for k, v in update_map.items():
                    if k in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index(k)+1, str(v)))
                if '상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('상태')+1, e_status))
                elif '학교상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('학교상태')+1, e_status))
                
                if cells_to_update: chunked_update(ws, cells_to_update)
                fetch_sheet_data.clear(); st.rerun()
                
        if c_btn2.form_submit_button("🚨 비활성화 (오늘 날짜로 이사 처리)"):
            actual_headers = ws.row_values(1)
            status_col_idx = actual_headers.index('학교상태') + 1 if '학교상태' in actual_headers else actual_headers.index('상태') + 1
            change_col_idx = actual_headers.index('변동일') + 1 if '변동일' in actual_headers else None
            
            cells = [gspread.Cell(int(target_dict['sheet_row']), status_col_idx, "이사")]
            if change_col_idx: cells.append(gspread.Cell(int(target_dict['sheet_row']), change_col_idx, datetime.date.today().strftime("%Y-%m-%d")))
            ws.update_cells(cells); fetch_sheet_data.clear(); st.rerun()

# --- 5. 화면(탭) 구성 ---
tabs = st.tabs(["📋 교적부", "🏫 반편성", "🎂 생일표", "🌱 새친구", "✅ 출석/행사", "⚙️ 행사기록", "📊 통합통계"])

# ==========================================
# [탭 0] 교적부 통합 관리 & 대시보드
# ==========================================
with tabs[0]:
    st.subheader("📋 교적부 통합 관리")
    
    st.markdown("##### 👥 전체 인원 현황 (Live)")
    df['is_staff_flag'] = df.apply(check_is_staff, axis=1)
    
    st_count = len(df[(df['is_staff_flag'] == False) & (~df[status_col].isin(INACTIVE_STATUS + ['새친구']))])
    new_count = len(df[df[status_col] == '새친구'])
    tc_count = len(df[df[status_col] == '교사'])
    ps_count = len(df[df[status_col].isin(['교역자', '전도사', '목사'])])
    mv_count = len(df[df[status_col] == '이사'])
    gr_count = len(df[df[status_col] == '졸업'])
    
    dash1, dash2, dash3, dash4 = st.columns(4)
    dash1.metric("총 재적 (학생)", f"{st_count + new_count}명", f"일반 {st_count}명 / 새친구 {new_count}명")
    dash2.metric("사역자 (선생님/교역자)", f"{tc_count + ps_count}명", f"선생님 {tc_count}명 / 교역자 {ps_count}명")
    dash3.metric("비활성 (이사/졸업)", f"{mv_count + gr_count}명", f"이사 {mv_count}명 / 졸업 {gr_count}명")
    dash4.metric("데이터 총합", f"{len(df)}명")
    st.divider()
    
    manage_mode = st.radio("작업 모드", ["👀 전체보기", "📝 수정/비활성", "➕ 인원추가"], horizontal=True)
    req_cols = ['학생ID', '학년(담임)', '이름', '학교상태', '등록일', '변동일', '학교', '부모(아빠/엄마)', '연락처']
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
# [탭 1] 반편성
# ==========================================
with tabs[1]:
    st.subheader("🏫 반별 명단")
    all_classes = sorted([c for c in df[class_col].unique() if str(c).strip()], key=natural_sort_key)
    cols = st.columns(3)
    
    for i, c_name in enumerate(all_classes):
        group = df[df[class_col] == c_name].copy()
        def get_sort_key(row):
            s = row[status_col]
            if s in INACTIVE_STATUS: return 100
            if check_is_staff(row): return get_teacher_rank(row['이름'], row.get('비고', ''))
            if s == '새친구': return 60
            return 80
            
        group['sort_key'] = group.apply(get_sort_key, axis=1)
        group = group.sort_values(by=['sort_key', '이름'])
        active_count = len(group[~group[status_col].isin(INACTIVE_STATUS)])
        
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"<h4 style='color:#0366d6; margin-bottom:10px; border-bottom:1px solid #eee;'>{c_name} ({active_count}명)</h4>", unsafe_allow_html=True)
                btn_cols = st.columns(2)
                for j, (_, r) in enumerate(group.iterrows()):
                    s = r[status_col]
                    n = r['이름']
                    if check_is_staff(r): label = f"🧑‍🏫 {n}"
                    elif s == '새친구': label = f"🔴 {n}"
                    elif s in INACTIVE_STATUS: label = f"🚫 {n} ({s})"
                    else: label = f"👤 {n}"
                    
                    with btn_cols[j % 2]:
                        if st.button(label, key=f"btn_link_{r['sheet_row']}", help="클릭하여 즉시 정보 수정", use_container_width=True):
                            edit_student_dialog(r.to_dict())
                
                with st.expander(f"➕ 새친구 추가"):
                    with st.form(f"qa_{i}"):
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
# [탭 2, 3] 생일표, 새친구
# ==========================================
with tabs[2]:
    st.subheader("🎂 월별 생일 명단")
    b_map = {i: [] for i in range(1, 13)}
    for _, r in df[~df[status_col].isin(INACTIVE_STATUS)].iterrows():
        b = str(r.get('생년월일', ''))
        if '-' in b and len(b.split('-')) == 3:
            try: m, d = int(b.split('-')[1]), int(b.split('-')[2]); b_map[m].append({"name": r['이름'], "class": r.get(class_col,''), "day": d})
            except: pass
    for row_idx in range(4):
        cols = st.columns(3)
        for col_idx in range(3):
            m = row_idx * 3 + col_idx + 1
            with cols[col_idx]:
                with st.container(border=True):
                    st.markdown(f"<h4 style='color:#0366d6; margin-bottom:0px;'>📅 {m}월</h4>", unsafe_allow_html=True); st.divider()
                    for p in sorted(b_map[m], key=lambda x: x["day"]):
                        st.markdown(f"<div style='display:flex; justify-content:space-between; margin-bottom:5px;'><span>🎈 <b>{p['name']}</b> <span style='font-size:0.8rem; color:gray;'>({p['class']})</span></span><strong style='color:#e65100;'>{p['day']}일</strong></div>", unsafe_allow_html=True)

with tabs[3]:
    st.subheader("🌱 최근 등록 새친구")
    news = df[df[status_col] == '새친구']
    if not news.empty: st.dataframe(news[available_cols], use_container_width=True, hide_index=True)
    else: st.info("등록된 새친구가 없습니다.")

# ==========================================
# [탭 4] 출석/행사
# ==========================================
with tabs[4]:
    st.subheader("📅 주간 출석 & 행사 현황")
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    extended_weeks_list = weeks_list + ["✏️ 직접 입력 (새 날짜)"]
    
    c1, c2 = st.columns(2)
    with c1: 
        sel_w_raw = st.selectbox("출석 주차 / 기준일", extended_weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map.get(x, x))
        if sel_w_raw == "✏️ 직접 입력 (새 날짜)": 
            target_date = st.date_input("새로운 날짜 선택", datetime.date.today())
            sel_w = target_date.strftime("%Y-%m-%d")
        else: 
            sel_w = sel_w_raw
            w_num = int(sel_w_raw.replace("주", ""))
            target_date = start_date + datetime.timedelta(days=(w_num-1)*7)
            
    with c2: 
        sel_class = st.selectbox("반 필터", ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()], key=natural_sort_key))
    
    show_inactive = st.checkbox("👀 비활성 명단 포함 (과거 출석 데이터 수정용)")
    
    if show_inactive: att_df = df.copy()
    else: att_df = df[~df[status_col].isin(INACTIVE_STATUS)].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
    
    att_df['is_staff_flag'] = att_df.apply(check_is_staff, axis=1)
    ui_t_df = att_df[att_df['is_staff_flag'] == True]
    ui_s_df = att_df[att_df['is_staff_flag'] == False]
    
    s_p = len(ui_s_df[ui_s_df[sel_w].astype(str).str.strip() == "1"])
    t_p = len(ui_t_df[ui_t_df[sel_w].astype(str).str.strip() == "1"])
    
    saved_guest = 0; saved_note = ""
    if not df_stat.empty and '주차' in df_stat.columns:
        match = df_stat[df_stat['주차'] == sel_w]
        if not match.empty: 
            try: saved_guest = int(match.iloc[0].get('새친구/추가예배', match.iloc[0].get('새친구(기타)', match.iloc[0].get('기타인원', 0))))
            except: pass
            saved_note = match.iloc[0].get('비고', '')

    st.markdown("#### 📊 현재 체크 현황 (수정/저장 전)")
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("학생 출석 체크", f"{s_p}명")
    cs2.metric("선생님 출석 체크", f"{t_p}명") 
    cs3.metric("기존 출석 합계", f"{s_p + t_p}명")
    guest_in = cs4.number_input("🎉 미등록 새친구/추가예배 (명단 체크 외)", min_value=0, value=saved_guest)
    
    st.markdown("---")
    col_ex1, col_ex2 = st.columns([1, 3])
    is_skip = col_ex1.toggle("⚠️ 출석체크 쉼 (행사/예외)", value=bool(saved_note))
    note_text = col_ex2.text_input("행사명/비고 (예: 유년부 쿠킹행사)", value=saved_note)

    with st.form("att_toggle_form"):
        new_att = {}
        if not is_skip:
            grouped = att_df.sort_values(by=['이름']).groupby(class_col)
            for c_name in sorted(grouped.groups.keys(), key=natural_sort_key):
                group = grouped.get_group(c_name)
                st.markdown(f"<div class='class-header'>🏷️ {c_name}</div>", unsafe_allow_html=True)
                cols = st.columns(3)
                for i, (idx, row) in enumerate(group.iterrows()):
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    prefix = f"🚫 " if row[status_col] in INACTIVE_STATUS else ("🌱 " if row[status_col] == '새친구' else "🧑‍🏫 " if row['is_staff_flag'] else "👤 ")
                    label = f"{prefix}{row['이름']}"
                    new_att[row['sheet_row']] = cols[i%3].toggle(label, value=is_on, key=f"tgl_{row['sheet_row']}_{sel_w}")
        
        if st.form_submit_button("💾 데이터 저장 (교적부/통계 반영)", type="primary", use_container_width=True):
            with st.spinner("안전하게 일괄 저장 중..."):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: ws.update_cell(1, target_c, sel_w)
                
                final_s_p = 0; final_t_p = 0; cells_to_update = []
                if not is_skip:
                    for r, v in new_att.items():
                        row_data = att_df[att_df['sheet_row'] == r]
                        is_staff_person = False
                        if not row_data.empty and row_data.iloc[0]['is_staff_flag']: is_staff_person = True
                        cells_to_update.append(gspread.Cell(int(r), target_c, "1" if v else ""))
                        if v:
                            if is_staff_person: final_t_p += 1
                            else: final_s_p += 1
                    if cells_to_update: chunked_update(ws, cells_to_update)
                
                save_s_p = 0 if is_skip else final_s_p
                save_t_p = 0 if is_skip else final_t_p
                
                valid_enrollment_df = df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
                valid_enrollment_df['is_staff_flag'] = valid_enrollment_df.apply(check_is_staff, axis=1)
                
                strict_staff_df = valid_enrollment_df[valid_enrollment_df['is_staff_flag'] == True]
                strict_student_df = valid_enrollment_df[valid_enrollment_df['is_staff_flag'] == False]
                
                student_count = len(strict_student_df)
                staff_count = len(strict_staff_df)
                
                rate_val = 0 if student_count == 0 else int((save_s_p / student_count) * 100)
                save_rate = "0%" if is_skip else f"{rate_val}%"
                
                stat_data = [sel_w, student_count, save_s_p, staff_count, save_t_p, guest_in, save_s_p + save_t_p + guest_in, save_rate, note_text, str(datetime.datetime.now())]
                
                match_stat = df_stat[df_stat['주차'] == sel_w] if not df_stat.empty else pd.DataFrame()
                if not match_stat.empty: ws_stat.update(f"A{match_stat.index[0]+2}:J{match_stat.index[0]+2}", [stat_data])
                else: ws_stat.append_row(stat_data)
                fetch_sheet_data.clear(); st.success(f"[{sel_w}] 동적 재적 기반 데이터 저장 완료!"); st.rerun()

# ==========================================
# [탭 5, 6] 행사기록, 통합통계
# ==========================================
with tabs[5]:
    st.subheader("⚙️ 행사 기록 관리")
    e_mode = st.radio("작업", ["📂 보기", "📝 수정", "🚨 삭제", "➕ 등록"], horizontal=True)
    if e_mode == "📂 보기" and not df_act.empty:
        for _, row in df_act[::-1].iterrows():
            with st.container():
                st.markdown(f"<div class='event-card'><h3 style='margin-top:0;'>📅 {row.get('날짜', '')} | {row.get('활동명', '')}</h3><p><b>내용:</b> {row.get('세부내용', '')}</p><p style='color: #d32f2f;'><b>공지:</b> {row.get('공지사항', '')}</p></div>", unsafe_allow_html=True)
                p_cols = st.columns(4)
                for i in range(1, 5):
                    url = row.get(f'사진{i}', "")
                    if url and str(url).startswith('http'): p_cols[i-1].image(url, use_container_width=True)
    elif e_mode == "📝 수정" and not df_act.empty:
        act_sh_headers = ws_act.row_values(1)
        v_act_cols = [c for c in ["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4"] if c in df_act.columns]
        edited_events = st.data_editor(df_act, use_container_width=True, hide_index=True, column_config={f"사진{i}": st.column_config.ImageColumn() for i in range(1, 5)})
        if st.button("📝 행사 저장"):
            with st.spinner("수정 중..."):
                cells_to_update = []
                for r in range(len(edited_events)):
                    for c in v_act_cols:
                        if str(df_act.iloc[r][c]) != str(edited_events.iloc[r][c]):
                            cells_to_update.append(gspread.Cell(int(df_act.iloc[r]['sheet_row']), act_sh_headers.index(c)+1, str(edited_events.iloc[r][c])))
                if cells_to_update: chunked_update(ws_act, cells_to_update); fetch_sheet_data.clear(); st.success("저장 완료!"); st.rerun()
    elif e_mode == "🚨 삭제" and not df_act.empty:
        sel_del = st.selectbox("삭제할 행사", df_act.apply(lambda r: f"{r['활동명']} | 날짜:{r.get('날짜','')} (ID:{r['sheet_row']})", axis=1).tolist())
        if st.button("🚨 삭제 실행"): ws_act.delete_rows(int(sel_del.split("(ID:")[1].replace(")", ""))); fetch_sheet_data.clear(); st.success("삭제되었습니다!"); st.rerun()
    elif e_mode == "➕ 등록":
        with st.form("new_e"):
            a_d = st.date_input("날짜"); a_t = st.text_input("행사명"); a_c = st.text_area("내용"); a_f = st.file_uploader("사진", accept_multiple_files=True)
            if st.form_submit_button("저장"):
                urls = ["", "", "", ""]; [urls.__setitem__(i, upload_photo(f, a_t)) for i, f in enumerate(a_f[:4])]
                ws_act.append_row([str(a_d), a_t, a_c, "", urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())]); fetch_sheet_data.clear(); st.success("저장 완료!"); st.rerun()

with tabs[6]:
    st.subheader("📊 사역 통합 통계 및 다운로드")
    show_all_stats = st.checkbox("📥 엑셀/통계 추출 시 비활성(이사/졸업) 인원 기록 포함하기", value=True)
    week_cols = [c for c in df.columns if c.endswith('주') or (c.count('-')==2 and len(c)>=8)]
    if show_all_stats: report_df = df[[class_col, '이름', '학교상태'] + week_cols].copy()
    else: report_df = df[~df[status_col].isin(INACTIVE_STATUS)][[class_col, '이름', '학교상태'] + week_cols].copy()
    report_df['출석수'] = report_df[week_cols].apply(lambda x: x.astype(str).str.strip().eq('1').sum(), axis=1)
    report_df['출석률'] = report_df['출석수'].apply(lambda x: f"{int(x/len(week_cols)*100)}%" if len(week_cols)>0 else "0%")
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1: st.write("👤 **개인별 누적 출석 현황**"); st.dataframe(report_df[[class_col, '이름', '학교상태', '출석수', '출석률']], use_container_width=True, hide_index=True)
    with col_dl2: st.write("📅 **주차별 통계 (시계열 역산 적용)**"); st.dataframe(df_stat, use_container_width=True, hide_index=True)
    st.divider()
    c_csv1, c_csv2 = st.columns(2)
    with c_csv1: st.download_button("📊 개인별 누적 통계 다운로드 (CSV)", data=report_df.to_csv(index=False).encode('utf-8-sig'), file_name=f"개인별통계_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)
    with c_csv2: st.download_button("📅 주차별 흐름 통계 다운로드 (CSV)", data=df_stat.to_csv(index=False).encode('utf-8-sig'), file_name=f"주차별통계_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)
