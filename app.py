import streamlit as st
import streamlit.components.v1 as components
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime
import uuid
import re
import time

# --- 1. 전역 설정 및 상수 ---
st.set_page_config(page_title="26년 슈팅스타 통합관리 V1.9", page_icon="🌱", layout="wide")
st.markdown('<div id="top-anchor"></div>', unsafe_allow_html=True)

components.html(
    """
    <script>
    window.history.pushState(null, "", window.location.href);
    window.onpopstate = function() {
        window.history.pushState(null, "", window.location.href);
    };
    </script>
    """,
    height=0, width=0
)

INACTIVE_STATUS = ['이사', '비활성', '졸업', '타교회']
ALL_STATUS_OPTS = ["일반", "새친구", "교사", "교역자", "전도사", "목사", "이사", "졸업", "타교회", "비활성"]

st.markdown("""
    <style>
    .class-header { background-color: #f1f8ff; padding: 12px 15px; border-radius: 8px; color: #0366d6; font-weight: 800; font-size: 1.1rem; margin-top: 20px; margin-bottom: 15px; border-left: 5px solid #0366d6; }
    div[data-testid="stToggle"] { border: 2px solid #eef2f6; padding: 12px 18px; border-radius: 16px; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.2s ease-in-out; margin-bottom: 10px; }
    div[data-testid="stToggle"]:hover { border-color: #0366d6; background-color: #f8fbff; }
    .event-card { border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin-bottom: 15px; background-color: #fafafa; }
    div[data-testid="stButton"] button { width: 100%; border-radius: 6px; text-align: left; padding: 4px 8px; font-size: 0.9rem; }
    
    .media-link img:hover { transform: scale(1.02); filter: brightness(0.95); cursor: zoom-in; }
    .small-btn button { padding: 0px 5px !important; font-size: 0.8rem !important; height: auto !important; min-height: 28px !important; margin-top: 0px; }
    
    div[data-testid="stTabs"] { overflow: visible !important; }
    div[data-testid="stTabs"] > div:first-child {
        position: -webkit-sticky !important;
        position: sticky !important;
        top: 3.5rem !important; 
        background-color: #ffffff !important;
        z-index: 999990 !important;
        padding-top: 10px !important;
        padding-bottom: 10px !important;
        border-bottom: 2px solid #eef2f6 !important;
    }
    
    div[data-baseweb="tab-list"] {
        display: flex; flex-wrap: wrap !important; gap: 5px;
        justify-content: flex-start; padding-bottom: 5px;
    }
    div[data-baseweb="tab"] {
        flex: 0 0 auto !important; 
        justify-content: center; padding: 8px 12px !important; margin: 0 !important;
        background-color: #f8f9fa; border-radius: 8px; border: 1px solid #eee;
    }
    div[data-baseweb="tab"][aria-selected="true"] {
        background-color: #0366d6 !important; color: white !important; border: 1px solid #0366d6;
    }
    div[data-baseweb="tab"] p { font-size: 0.9rem !important; font-weight: 700 !important; white-space: nowrap; margin: 0; }
    
    .fab-button {
        position: fixed; bottom: 30px; left: 30px; background-color: rgba(3, 102, 214, 0.85);
        color: white !important; padding: 12px 20px; border-radius: 30px; text-decoration: none;
        font-weight: bold; font-size: 0.9rem; box-shadow: 0 4px 10px rgba(0,0,0,0.3); z-index: 999999;
    }
    .fab-button:hover { background-color: rgba(3, 102, 214, 1); transform: translateY(-3px); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 시스템 접근 제어 및 글로벌 상태 초기화 ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if 'privacy_mode' not in st.session_state: st.session_state['privacy_mode'] = True
if 'chongmu_auth' not in st.session_state: st.session_state['chongmu_auth'] = False

if not st.session_state["authenticated"]:
    # UI 개선 #1: 로그인 화면 친절한 안내 및 중앙 정렬 배치
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center; color: #0366d6;'>🌱 26년 슈팅스타 통합관리</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray; margin-bottom: 20px;'>안전한 시스템 접근을 위해 관리자 비밀번호를 입력해주세요.</p>", unsafe_allow_html=True)
            pwd = st.text_input("비밀번호 (특수문자 포함)", type="password", placeholder="비밀번호 입력", label_visibility="collapsed")
            if st.button("🚀 시스템 로그인", use_container_width=True, type="primary"):
                if "admin_password" in st.secrets and pwd == st.secrets["admin_password"]:
                    st.session_state["authenticated"] = True; st.rerun()
                else: st.error("❌ 비밀번호가 일치하지 않습니다.")
    st.stop()

if "GOOGLE_PROXY_URL" in st.secrets: GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else: st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!"); st.stop()

start_date = datetime.date(2026, 1, 4)

# --- 3. 공통 유틸리티 함수 ---
def safe_str(val):
    if pd.isna(val) or str(val).strip() in ['None', 'nan', 'NaT', '']: return ''
    return str(val).strip()

# 에러 원천 차단: 안전한 정수 변환 함수
def parse_int_safe(val):
    if pd.isna(val) or str(val).strip() == '': return 0
    try: return int(float(str(val).replace(',', '')))
    except: return 0

def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        headers = {"Authorization": f"Bearer {st.secrets.get('PROXY_AUTH_KEY', '')}"} if "PROXY_AUTH_KEY" in st.secrets else {}
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}, headers=headers, timeout=120)
        res.raise_for_status()
        url = res.json().get("fileUrl", "")
        if file.type and file.type.startswith('video/') and "vid=1" not in url: url += "&vid=1" if "?" in url else "?vid=1"
        return url
    except Exception as e: return ""

def chunked_update(worksheet, cells, chunk_size=200):
    for i in range(0, len(cells), chunk_size):
        worksheet.update_cells(cells[i:i + chunk_size])
        time.sleep(0.5)

def parse_date_safe(date_str):
    if not date_str: return datetime.date(2015, 1, 1)
    try:
        clean_str = str(date_str).replace(" ", "").strip().rstrip('.').replace('.', '-').replace('/', '-')
        if len(clean_str) == 8 and clean_str.count('-') == 2:
            parts = clean_str.split('-')
            if len(parts[0]) == 2: clean_str = f"20{parts[0]}-{parts[1]}-{parts[2]}"
        if len(clean_str) == 8 and clean_str.count('-') == 0: return datetime.datetime.strptime(clean_str, "%Y%m%d").date()
        return datetime.datetime.strptime(clean_str, "%Y-%m-%d").date()
    except: return datetime.date(2015, 1, 1)

def natural_sort_key(s): return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', str(s).replace(" ", ""))]
def class_sort_key(c):
    c_str = str(c).replace(" ", "")
    priority = 1
    if any(k in c_str for k in ['교역자', '전도사', '목사']): priority = 3
    elif any(k in c_str for k in ['선생님', '교사']): priority = 2
    return (priority, natural_sort_key(c_str))

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
    if reg_str and parse_date_safe(reg_str) > target_date: return False
    s = safe_str(row.get('학교상태', '일반'))
    if s in INACTIVE_STATUS:
        change_str = safe_str(row.get('변동일', ''))
        if change_str and parse_date_safe(change_str) <= target_date: return False
        elif not change_str: return False
    return True

def get_role(row):
    s, c, m = safe_str(row.get('학교상태', '')), safe_str(row.get('학년(담임)', row.get('반', ''))), safe_str(row.get('비고', ''))
    if s in ['교역자', '전도사', '목사'] or any(k in m for k in ['전도사', '목사', '교역자']) or any(k in c for k in ['교역자', '전도사', '목사']): return 'pastor'
    if s == '교사' or any(k in c for k in ['교사', '임원', '선생님']) or any(k in m for k in ['교사', '부장', '부감', '총무', '회계', '선생님']): return 'teacher'
    return 'student'

def get_date_from_week_str(w_str):
    w_str = str(w_str).strip()
    if w_str.endswith('주'):
        try: return start_date + datetime.timedelta(days=(int(w_str.replace('주', ''))-1)*7)
        except: pass
    return parse_date_safe(w_str)

def format_week_display(w_str):
    w_str = str(w_str).strip()
    if w_str.endswith('주'): return f"{w_str} ({get_date_from_week_str(w_str).strftime('%m/%d')})"
    return w_str

def check_is_staff(row):
    s = safe_str(row.get('학교상태', ''))
    c = safe_str(row.get('학년(담임)', row.get('반', '')))
    m = safe_str(row.get('비고', ''))
    if s in ['교사', '교역자', '전도사', '목사']: return True
    if s in INACTIVE_STATUS and (any(k in c for k in ['교사', '교역자', '전도사', '목사', '임원', '선생님']) or any(k in m for k in ['교사', '교역자', '전도사', '목사', '부장', '부감', '총무', '선생님'])): return True
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
    except: ws_a = sh.add_worksheet("활동간식", 500, 20); ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항"] + [f"사진{i}" for i in range(1, 16)] + ["등록일"])
    
    try: ws_s = sh.worksheet("주차별통계")
    except: 
        ws_s = sh.add_worksheet("주차별통계", 200, 15)
        ws_s.append_row(["주차", "행사명", "유년부 재적", "출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"])
        
    try: ws_r = sh.worksheet("영수증")
    except: ws_r = sh.add_worksheet("영수증", 500, 10); ws_r.append_row(["번호", "날짜", "구매처", "내용", "비용", "비고", "영수증사진"])
    
    try: ws_in = sh.worksheet("회비입금")
    except: ws_in = sh.add_worksheet("회비입금", 500, 10); ws_in.append_row(["번호", "날짜", "입금자명", "입금액", "비고"])
    
    try: ws_out = sh.worksheet("회비지출")
    except: ws_out = sh.add_worksheet("회비지출", 500, 10); ws_out.append_row(["번호", "날짜", "내용", "지출액", "비고", "영수증사진"])

    return ws_m, ws_a, ws_s, ws_r, ws_in, ws_out

@st.cache_data(ttl=600)
def fetch_sheet_data():
    ws_m, ws_a, ws_s, ws_r, ws_in, ws_out = get_worksheets()
    return ws_m.get_all_values(), ws_a.get_all_values(), ws_s.get_all_values(), ws_r.get_all_values(), ws_in.get_all_values(), ws_out.get_all_values()

def get_all_data():
    try:
        ws_m, ws_a, ws_s, ws_r, ws_in, ws_out = get_worksheets()
        vals_m, vals_a, vals_s, vals_r, vals_in, vals_out = fetch_sheet_data()
        
        df_m = pd.DataFrame(vals_m[1:], columns=vals_m[0]) if len(vals_m) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        if not df_m.empty and '이름' in df_m.columns:
            df_m = df_m[df_m['이름'].astype(str).str.strip() != '']
            df_m = df_m[~df_m['이름'].isin(['None', 'nan', ''])]
        if '상태' in df_m.columns and '학교상태' not in df_m.columns: df_m.rename(columns={'상태': '학교상태'}, inplace=True)
        
        df_a = pd.DataFrame(vals_a[1:], columns=vals_a[0]) if len(vals_a) > 1 else pd.DataFrame()
        df_a['sheet_row'] = range(2, len(df_a) + 2)
        df_s = pd.DataFrame(vals_s[1:], columns=vals_s[0]) if len(vals_s) > 1 else pd.DataFrame()
        
        df_r = pd.DataFrame(vals_r[1:], columns=vals_r[0]) if len(vals_r) > 1 else pd.DataFrame()
        if not df_r.empty: df_r['sheet_row'] = range(2, len(df_r) + 2)
        
        df_in = pd.DataFrame(vals_in[1:], columns=vals_in[0]) if len(vals_in) > 1 else pd.DataFrame()
        if not df_in.empty: df_in['sheet_row'] = range(2, len(df_in) + 2)
            
        df_out = pd.DataFrame(vals_out[1:], columns=vals_out[0]) if len(vals_out) > 1 else pd.DataFrame()
        if not df_out.empty: df_out['sheet_row'] = range(2, len(df_out) + 2)
        
        return ws_m, df_m, vals_m[0], ws_a, df_a, ws_s, df_s, ws_r, df_r, ws_in, df_in, ws_out, df_out
    except Exception as e: return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat, ws_r, df_r, ws_in, df_in, ws_out, df_out = get_all_data()

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
        st.error(f"🚨 **더블카운트 원인 발견 (데이터 중복):** 교적부 시트에 똑같은 이름이 2번 이상 등록된 사람이 있습니다!\n\n**🔍 중복 명단: {', '.join(dup_details)}**")

weeks_list = [f"{i}주" for i in range(1, 53)]
week_display_map = {f"{i}주": format_week_display(f"{i}주") for i in range(1, 53)}

@st.dialog("👤 인원 정보 상세")
def edit_student_dialog(target_dict):
    row_id = target_dict['sheet_row']
    edit_key = f"edit_mode_{row_id}"
    if edit_key not in st.session_state: st.session_state[edit_key] = False
    def set_edit_true(): st.session_state[edit_key] = True
    def set_edit_false(): st.session_state[edit_key] = False
        
    if not st.session_state[edit_key]:
        st.info(f"💡 **{safe_str(target_dict.get('이름', ''))}** 님의 등록 정보입니다.")
        col_i, col_f = st.columns([1, 2])
        clean_p_url = safe_str(target_dict.get('사진', '')).replace("&vid=1", "").replace("?vid=1", "")
        if clean_p_url and str(clean_p_url).startswith('http'): col_i.markdown(f'<img src="{clean_p_url}" style="width:100%; border-radius:8px;">', unsafe_allow_html=True)
        else: col_i.info("등록된 사진이 없습니다.")
            
        c1, c2 = col_f.columns(2)
        c1.markdown(f"**이름:** {safe_str(target_dict.get('이름',''))}")
        c2.markdown(f"**반(담임):** {safe_str(target_dict.get(class_col,''))}")
        
        if st.session_state.get('privacy_mode', True):
            p_phone = "🔒 [보호됨]" if safe_str(target_dict.get('연락처','')) else ""
            p_parent = "🔒 [보호됨]" if safe_str(target_dict.get('부모(아빠/엄마)','')) else ""
            p_addr = "🔒 [보호됨]" if safe_str(target_dict.get('주소','')) else ""
            p_birth = "🔒 [보호됨]" if safe_str(target_dict.get('생년월일','')) else ""
        else:
            p_phone = safe_str(target_dict.get('연락처',''))
            p_parent = safe_str(target_dict.get('부모(아빠/엄마)',''))
            p_addr = safe_str(target_dict.get('주소',''))
            p_birth = safe_str(target_dict.get('생년월일',''))
            
        c1.markdown(f"**생년월일:** {p_birth}")
        c2.markdown(f"**구분:** {safe_str(target_dict.get('학교상태', '일반'))}")
        c1.markdown(f"**학교:** {safe_str(target_dict.get('학교',''))}")
        c2.markdown(f"**연락처:** {p_phone}")
        st.markdown(f"**부모(아빠/엄마):** {p_parent}")
        st.markdown(f"**주소:** {p_addr}")
        st.markdown(f"**비고:** {safe_str(target_dict.get('비고',''))}")
        st.caption(f"등록일: {safe_str(target_dict.get('등록일',''))} | 변동일: {safe_str(target_dict.get('변동일',''))}")
        st.divider()
        st.button("✏️ 정보 수정하기", use_container_width=True, on_click=set_edit_true)
            
    else:
        st.warning("⚠️ 현재 정보를 수정 중입니다.")
        with st.form("modal_edit_form"):
            col_i, col_f = st.columns([1, 2])
            clean_p_url = safe_str(target_dict.get('사진', '')).replace("&vid=1", "").replace("?vid=1", "")
            if clean_p_url and str(clean_p_url).startswith('http'): col_i.markdown(f'<img src="{clean_p_url}" style="width:100%; border-radius:8px;">', unsafe_allow_html=True)
            
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
                        h_cells = [gspread.Cell(1, start_col + i, mh) for i, mh in enumerate(missing_headers)]
                        for mh in missing_headers: actual_headers.append(mh)
                        try: chunked_update(ws, h_cells)
                        except: ws.add_cols(15); chunked_update(ws, h_cells)
                    
                    r_idx = int(target_dict['sheet_row'])
                    update_map = {'이름': e_name, '학년(담임)': e_class, '반': e_class, '생년월일': e_birth, '학교': e_school, '주소': e_addr, '부모(아빠/엄마)': e_parents, '연락처': e_phone, '비고': e_memo, '사진': p_url, '등록일': e_reg, '변동일': e_change}
                    
                    cells_to_update = []
                    for k, v in update_map.items():
                        if k in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index(k)+1, str(v)))
                    if '상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('상태')+1, e_status))
                    elif '학교상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('학교상태')+1, e_status))
                    
                    if cells_to_update: chunked_update(ws, cells_to_update)
                    
                    st.session_state[edit_key] = False
                    st.success("✅ 저장이 완료되었습니다!")
                    time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
        st.button("❌ 수정 취소", use_container_width=True, on_click=set_edit_false)

# --- 5. 화면(탭) 구성 ---
tabs = st.tabs(["🏫 반", "📋 교적부", "🎂 생일", "🌱 새친구", "⚙️ 행사", "✅ 출석", "📊 통계", "🧾 비용집행관리", "💰 회비관리"])

# ==========================================
# [탭 0] 반편성 (UI 개선 #2, #3 적용)
# ==========================================
with tabs[0]:
    st.markdown('<a href="#top-anchor" class="fab-button">⬆ 맨 위로</a>', unsafe_allow_html=True)
    st.subheader("🏫 반별 명단")
    st.info("💡 **아이콘 안내** &nbsp;|&nbsp; 👤 일반 &nbsp;&nbsp; 🌱 새친구 &nbsp;&nbsp; 🧑‍🏫 교사 &nbsp;&nbsp; ✝️ 교역자 &nbsp;&nbsp; 🚫 비활성(이사/졸업 등)")
    
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
                if is_teacher_grp: active_count = len(group[~group[status_col].isin(INACTIVE_STATUS) & (group['role'] == 'teacher')]); header_title = f"{c_name} ({active_count}명)"
                elif is_pastor_grp: active_count = len(group[~group[status_col].isin(INACTIVE_STATUS) & (group['role'] == 'pastor')]); header_title = f"{c_name} ({active_count}명)"
                else: active_count = len(group[~group[status_col].isin(INACTIVE_STATUS) & (group['role'] == 'student')]); header_title = f"{c_name} (학생 {active_count}명)"
                
                with cols[j]:
                    with st.container(border=True):
                        st.markdown(f"<h4 style='color:#0366d6; margin-bottom:10px; border-bottom:1px solid #eee;'>{header_title}</h4>", unsafe_allow_html=True)
                        btn_cols = st.columns(2)
                        for idx_j, (_, r) in enumerate(group.iterrows()):
                            s, n = r[status_col], r['이름']
                            b_str, bd_disp = str(r.get('생년월일', '')), ""
                            if '-' in b_str and len(b_str.split('-')) == 3:
                                try: bd_disp = f" 🎂{int(b_str.split('-')[1]):02d}/{int(b_str.split('-')[2]):02d}"
                                except: pass
                            
                            prefix = "🚫 " if s in INACTIVE_STATUS else ""
                            suffix = f" ({s})" if s in INACTIVE_STATUS else ""
                            if r['role'] == 'pastor': label = f"{prefix}✝️ {n}{suffix}{bd_disp}"
                            elif r['role'] == 'teacher': label = f"{prefix}🧑‍🏫 {n}{suffix}{bd_disp}"
                            elif s == '새친구': label = f"{prefix}🔴 {n}{suffix}{bd_disp}"
                            else: label = f"{prefix}👤 {n}{suffix}{bd_disp}"
                            
                            with btn_cols[idx_j % 2]:
                                if st.button(label, key=f"btn_link_{r['sheet_row']}", help="상세정보 확인", use_container_width=True): edit_student_dialog(r.to_dict())
                        
                        with st.expander(f"➕ 새친구 추가"):
                            with st.form(f"qa_{i+j}"):
                                col_n, col_btn = st.columns([3, 1])
                                new_n = col_n.text_input("이름", placeholder="이름 입력", label_visibility="collapsed")
                                if col_btn.form_submit_button("등록") and new_n:
                                    new_row = [""] * len(headers)
                                    h_map = {str(h): idx for idx, h in enumerate(headers)}
                                    if '학생ID' in h_map: new_row[h_map['학생ID']] = f"S-{datetime.datetime.now().strftime('%y%m')}-{str(uuid.uuid4())[:4].upper()}"
                                    if '이름' in h_map: new_row[h_map['이름']] = new_n
                                    if class_col in h_map: new_row[h_map[class_col]] = c_name
                                    if '생년월일' in h_map: new_row[h_map['생년월일']] = datetime.date.today().strftime("%Y-%m-%d")
                                    if '학교상태' in h_map: new_row[h_map['학교상태']] = "새친구"
                                    elif '상태' in h_map: new_row[h_map['상태']] = "새친구"
                                    ws.append_row(new_row); st.success("✅ 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 1] 교적부 통합 관리 (UI 개선 #4 적용)
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
    
    col_dash1, col_dash2 = st.columns([8.5, 1.5])
    with col_dash1: st.markdown("##### 👥 전체 인원 현황 (Live)")
    with col_dash2:
        st.markdown('<div class="small-btn">', unsafe_allow_html=True)
        if st.button("🔄 새로고침", use_container_width=True, key="refresh_tab1"):
            fetch_sheet_data.clear(); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    active_sum_calc = len(df) - total_inact
    tt_st = f"일반 {st_count}명, 새친구 {new_count}명"
    tt_tc = f"선생님 {tc_count}명, 교역자 {ps_count}명"
    tt_inact = f"이사 {mv_count}명, 졸업 {gr_count}명, 타교회 {other_ch_count}명, 비활성화 {inact_count}명"
    tt_total = f"유년부({st_count+new_count}) + 사역자({tc_count+ps_count}) = {active_sum_calc}명"
    
    html_dashboard = f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 15px 5px; background-color:#f1f8ff; border-radius:10px; border: 1px solid #cce5ff; overflow: hidden;">
        <div style="text-align: center; flex: 1; padding: 0 5px;" title="{tt_st}">
            <div style="font-size: clamp(0.9rem, 2.5vw, 1.4rem); font-weight: 800; color: #0366d6; margin-bottom: 4px; white-space: nowrap; cursor: help;">총 재적</div>
            <div style="font-size: clamp(1.2rem, 3vw, 1.8rem); font-weight: 700; color: #333; white-space: nowrap; cursor: help;">{st_count + new_count}명</div>
        </div>
        <div style="text-align: center; flex: 1; padding: 0 5px;" title="{tt_tc}">
            <div style="font-size: clamp(0.9rem, 2.5vw, 1.4rem); font-weight: 800; color: #0366d6; margin-bottom: 4px; white-space: nowrap; cursor: help;">사역자</div>
            <div style="font-size: clamp(1.2rem, 3vw, 1.8rem); font-weight: 700; color: #333; white-space: nowrap; cursor: help;">{tc_count + ps_count}명</div>
        </div>
        <div style="text-align: center; flex: 1; padding: 0 5px;" title="{tt_inact}">
            <div style="font-size: clamp(0.9rem, 2.5vw, 1.4rem); font-weight: 800; color: #0366d6; margin-bottom: 4px; white-space: nowrap; cursor: help;">비활성</div>
            <div style="font-size: clamp(1.2rem, 3vw, 1.8rem); font-weight: 700; color: #333; white-space: nowrap; cursor: help;">{total_inact}명</div>
        </div>
        <div style="text-align: center; flex: 1; padding: 0 5px;" title="{tt_total}">
            <div style="font-size: clamp(0.9rem, 2.5vw, 1.4rem); font-weight: 800; color: #0366d6; margin-bottom: 4px; white-space: nowrap; cursor: help;">총합</div>
            <div style="font-size: clamp(1.2rem, 3vw, 1.8rem); font-weight: 700; color: #333; white-space: nowrap; cursor: help;">{active_sum_calc}명</div>
        </div>
    </div>
    """
    st.markdown(html_dashboard, unsafe_allow_html=True)
    
    with st.container(border=True):
        st.markdown("##### 🔐 개인정보 열람 보안 설정")
        if st.session_state['privacy_mode']:
            st.markdown("현재 생년월일, 연락처, 주소 정보가 **블라인드(마스킹)** 처리되어 있습니다.")
            c_p1, c_p2 = st.columns([3, 1])
            priv_pwd = c_p1.text_input("시스템 비밀번호 입력", type="password", key="priv_pwd_input", label_visibility="collapsed", placeholder="비밀번호 입력")
            if c_p2.button("🔓 블라인드 해제", use_container_width=True):
                if priv_pwd == st.secrets.get("admin_password", ""):
                    st.session_state['privacy_mode'] = False; st.rerun()
                else: st.error("비밀번호가 일치하지 않습니다.")
        else:
            st.success("🔓 개인정보 열람 모드가 활성화되었습니다.")
            if st.button("🔒 다시 블라인드 처리하기"):
                st.session_state['privacy_mode'] = True; st.rerun()

    st.divider()
    manage_mode = st.radio("작업 모드", ["👀 전체보기", "📝 수정/비활성", "➕ 인원추가"], horizontal=True)
    req_cols = ['학생ID', '학년(담임)', '이름', '생년월일', '학교상태', '등록일', '변동일', '학교', '부모(아빠/엄마)', '연락처', '주소', '비고']
    available_cols = [c for c in req_cols if c in df.columns]
    
    if manage_mode == "👀 전체보기":
        df_display = df[available_cols].copy()
        if st.session_state['privacy_mode']:
            for c_priv in ['생년월일', '부모(아빠/엄마)', '연락처', '주소']:
                if c_priv in df_display.columns: df_display[c_priv] = df_display[c_priv].apply(lambda x: "🔒 [보호됨]" if str(x).strip() else "")
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
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
                    ws.append_row(new_row)
                    st.success("✅ 등록 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 2] 생일표 (UI 개선 #5 적용)
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
                    month_data = b_map[m]
                    if month_data:
                        for p in sorted(month_data, key=lambda x: x["day"]):
                            if p['role'] == 'pastor': n_disp = f"<span style='color:#2E7D32;'>✝️ <b>{p['name']}</b></span>"
                            elif p['role'] == 'teacher': n_disp = f"<span style='color:#E91E63;'>🧑‍🏫 <b>{p['name']}</b></span>"
                            else: n_disp = f"<span>🎈 <b>{p['name']}</b></span>"
                            st.markdown(f"<div style='display:flex; justify-content:space-between; margin-bottom:5px;'>{n_disp} <span style='font-size:0.8rem; color:gray;'>({p['class']})</span><strong style='color:#e65100;'>{p['day']}일</strong></div>", unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='text-align:center; color:#ccc; font-size:0.9rem; padding: 10px 0;'>생일자가 없습니다</div>", unsafe_allow_html=True)

# ==========================================
# [탭 3] 새친구
# ==========================================
with tabs[3]:
    st.subheader("🌱 최근 등록 새친구")
    news = df[df[status_col] == '새친구'].copy()
    if not news.empty: 
        news_display = news[available_cols].copy()
        if st.session_state.get('privacy_mode', True):
            for c_priv in ['생년월일', '부모(아빠/엄마)', '연락처', '주소']:
                if c_priv in news_display.columns:
                    news_display[c_priv] = news_display[c_priv].apply(lambda x: "🔒 [보호됨]" if str(x).strip() else "")
        st.dataframe(news_display, use_container_width=True, hide_index=True)
    else: 
        st.info("등록된 새친구가 없습니다.")

# ==========================================
# [탭 4] 행사 기록 관리 (UI 개선 #6 적용)
# ==========================================
with tabs[4]:
    st.markdown('<a href="#top-anchor" class="fab-button">⬆ 맨 위로</a>', unsafe_allow_html=True)
    st.subheader("⚙️ 행사 기록 관리")
    
    with st.container(border=True):
        e_mode = st.radio("🛠️ 작업 모드 선택", ["📂 보기", "📝 수정", "🚨 삭제", "➕ 등록"], horizontal=True)
    st.divider()
    
    def format_event(row_id):
        if row_id == "행사 선택": return "행사 선택"
        match = df_act[df_act['sheet_row'] == row_id]
        if not match.empty: return f"{match.iloc[0].get('날짜','')} | {match.iloc[0].get('활동명','')}"
        return "알 수 없음"

    if e_mode == "📂 보기" and not df_act.empty:
        view_act_df = df_act.copy()
        view_act_df['sort_date'] = pd.to_datetime(view_act_df['날짜'], errors='coerce')
        view_act_df = view_act_df.sort_values(by=['sort_date', 'sheet_row'], ascending=[False, False])
        
        for _, row in view_act_df.iterrows():
            with st.expander(f"📅 {row.get('날짜', '')} | {row.get('활동명', '')}"):
                st.write(f"**내용:** {row.get('세부내용', '')}")
                if str(row.get('공지사항', '')).strip(): st.markdown(f"**<span style='color: #d32f2f;'>공지:</span>** <span style='color: #d32f2f;'>{row.get('공지사항', '')}</span>", unsafe_allow_html=True)
                
                valid_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                if valid_urls:
                    st.markdown("---")
                    gallery_html = '<div style="display: flex; flex-direction: column; gap: 15px; width: 100%;">'
                    for media_url in valid_urls:
                        clean_url = str(media_url).replace("&vid=1", "").replace("?vid=1", "")
                        is_vid = 'vid=1' in str(media_url).lower() or any(ext in str(media_url).lower() for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv'])
                        if is_vid:
                            file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', clean_url) or re.search(r'id=([a-zA-Z0-9_-]+)', clean_url)
                            if file_id_match:
                                f_id = file_id_match.group(1)
                                gallery_html += f'''
                                <div style="width: 100%; max-width: 800px; margin-bottom: 10px;">
                                    <iframe src="https://drive.google.com/file/d/{f_id}/preview" width="100%" height="500" style="border: none; border-radius: 8px; background-color: black; box-shadow: 0 2px 4px rgba(0,0,0,0.1);" allow="autoplay; fullscreen" playsinline webkitallowfullscreen mozallowfullscreen></iframe>
                                    <div style="text-align: right; padding-top: 5px;"><a href="https://drive.google.com/file/d/{f_id}/view" target="_blank" style="color: #bbb; font-size: 0.8rem; text-decoration: none; font-weight: bold;">⚙️ 원본 열기</a></div>
                                </div>'''
                            else:
                                gallery_html += f'''
                                <div style="width: 100%; max-width: 800px; margin-bottom: 10px;">
                                    <video src="{clean_url}" controls playsinline preload="metadata" style="width: 100%; height: 515px; object-fit: contain; border-radius: 8px; background-color: black; display: block;"></video>
                                </div>'''
                        else:
                            gallery_html += f'''
                            <div style="width: 100%; margin-bottom: 5px;">
                                <a href="{clean_url}" target="_blank" title="클릭하여 원본 크게 보기" style="display: block;">
                                    <img src="{clean_url}" loading="lazy" style="width: 100%; height: auto; object-fit: contain; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); background-color: #f8f9fa; display: block;">
                                </a>
                            </div>'''
                    gallery_html += '</div>'
                    st.markdown(gallery_html, unsafe_allow_html=True)
                    
    elif e_mode == "📝 수정" and not df_act.empty:
        sort_act = df_act.copy()
        sort_act['sort_date'] = pd.to_datetime(sort_act['날짜'], errors='coerce')
        sort_act = sort_act.sort_values(by=['sort_date', 'sheet_row'], ascending=[False, False])
        event_options = ["행사 선택"] + sort_act['sheet_row'].tolist()
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
                bulk_files = st.file_uploader("🔄 일괄 덮어쓰기 (기존 미디어를 모두 지우고 최대 15개까지 새로 올립니다)", accept_multiple_files=True, type=['png','jpg','jpeg','mp4','mov','avi'])
                st.markdown("---")
                st.write("📸 개별 사진/동영상 수정")
                old_urls = [target_event.get(f'사진{i}', "") for i in range(1, 16)]
                new_files, delete_flags = [None] * 15, [False] * 15
                
                for i in range(0, 15, 2):
                    p_cols = st.columns(2)
                    for j in range(2):
                        idx = i + j
                        if idx >= 15: break
                        with p_cols[j]:
                            media_url = old_urls[idx]
                            if media_url and str(media_url).startswith('http'):
                                clean_url = str(media_url).replace("&vid=1", "").replace("?vid=1", "")
                                is_vid = 'vid=1' in str(media_url).lower() or any(ext in str(media_url).lower() for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv'])
                                if is_vid:
                                    file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', clean_url) or re.search(r'id=([a-zA-Z0-9_-]+)', clean_url)
                                    if file_id_match:
                                        f_id = file_id_match.group(1)
                                        st.markdown(f'<div style="width: 100%; max-width: 560px; margin-bottom: 10px;"><iframe src="https://drive.google.com/file/d/{f_id}/preview" width="100%" height="315" style="border: none; border-radius: 8px; background-color: black;" allow="autoplay; fullscreen" playsinline webkitallowfullscreen mozallowfullscreen></iframe></div>', unsafe_allow_html=True)
                                    else:
                                        st.markdown(f'<div style="width: 100%; max-width: 560px; margin-bottom: 10px;"><video src="{clean_url}" controls playsinline preload="metadata" style="width: 100%; height: 315px; object-fit: contain; border-radius: 8px; background-color: black; display: block;"></video></div>', unsafe_allow_html=True)
                                else:
                                    st.markdown(f'<div style="width: 100%; margin-bottom: 10px;"><a href="{clean_url}" target="_blank"><img src="{clean_url}" loading="lazy" style="width: 100%; height: auto; object-fit: contain; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: block;"></a></div>', unsafe_allow_html=True)
                                delete_flags[idx] = st.checkbox(f"[{idx+1}] 삭제", key=f"del_img_{target_row_id}_{idx}")
                                new_files[idx] = st.file_uploader(f"[{idx+1}] 변경", key=f"up_img_{target_row_id}_{idx}", label_visibility="collapsed", type=['png','jpg','jpeg','mp4','mov','avi'])
                            else:
                                st.markdown(f"**[{idx+1}] 빈 칸**")
                                new_files[idx] = st.file_uploader(f"[{idx+1}] 추가", key=f"add_img_{target_row_id}_{idx}", label_visibility="collapsed", type=['png','jpg','jpeg','mp4','mov','avi'])
                
                if st.form_submit_button("📝 행사 수정 저장", type="primary"):
                    with st.spinner("미디어 반영 중..."):
                        final_urls = old_urls.copy()
                        if bulk_files:
                            final_urls = [""] * 15
                            for k, f in enumerate(bulk_files[:15]): final_urls[k] = upload_photo(f, e_t)
                        else:
                            for k in range(15):
                                if new_files[k] is not None: final_urls[k] = upload_photo(new_files[k], e_t)
                                elif delete_flags[k]: final_urls[k] = ""
                        
                        act_sh_headers = ws_act.row_values(1)
                        missing_act = [col for col in [f"사진{idx}" for idx in range(1, 16)] if col not in act_sh_headers]
                        if missing_act:
                            start_col = len(act_sh_headers) + 1
                            h_cells = [gspread.Cell(1, start_col + i, mh) for i, mh in enumerate(missing_act)]
                            for mh in missing_act: act_sh_headers.append(mh)
                            try: chunked_update(ws_act, h_cells)
                            except: ws_act.add_cols(15); chunked_update(ws_act, h_cells)
                        
                        update_map = {"날짜": str(e_d.strftime("%Y-%m-%d")), "활동명": e_t, "세부내용": e_c, "공지사항": e_n}
                        for k in range(1, 16): update_map[f"사진{k}"] = final_urls[k-1]
                        
                        cells_to_update = [gspread.Cell(target_row_id, act_sh_headers.index(k)+1, str(v)) for k, v in update_map.items() if k in act_sh_headers]
                        if cells_to_update: chunked_update(ws_act, cells_to_update)
                        st.success("✅ 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

    elif e_mode == "🚨 삭제" and not df_act.empty:
        sort_act = df_act.copy()
        sort_act['sort_date'] = pd.to_datetime(sort_act['날짜'], errors='coerce')
        sort_act = sort_act.sort_values(by=['sort_date', 'sheet_row'], ascending=[False, False])
        event_options = ["행사 선택"] + sort_act['sheet_row'].tolist()
        sel_del = st.selectbox("삭제할 행사", event_options, format_func=format_event)
        if st.button("🚨 삭제 실행") and sel_del != "행사 선택": 
            ws_act.delete_rows(int(sel_del)); st.success("✅ 삭제 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
        
    elif e_mode == "➕ 등록":
        with st.form("new_e"):
            a_d = st.date_input("날짜"); a_t = st.text_input("행사명"); a_c = st.text_area("내용"); a_n = st.text_input("공지사항")
            a_f = st.file_uploader("사진/영상 (최대15개)", accept_multiple_files=True, type=['png','jpg','jpeg','mp4','mov','avi'])
            if st.form_submit_button("저장"):
                with st.spinner("저장 중..."):
                    urls = [""] * 15
                    if a_f: 
                        for i, f in enumerate(a_f[:15]): urls[i] = upload_photo(f, a_t)
                    act_sh_headers = ws_act.row_values(1)
                    missing_act = [col for col in [f"사진{idx}" for idx in range(1, 16)] if col not in act_sh_headers]
                    if missing_act:
                        start_col = len(act_sh_headers) + 1
                        h_cells = [gspread.Cell(1, start_col + idx_h, mh) for idx_h, mh in enumerate(missing_act)]
                        for mh in missing_act: act_sh_headers.append(mh)
                        try: chunked_update(ws_act, h_cells)
                        except: ws_act.add_cols(15); chunked_update(ws_act, h_cells)
                    
                    h_map = {str(h): idx for idx, h in enumerate(act_sh_headers)}
                    new_row = [""] * len(act_sh_headers)
                    if "날짜" in h_map: new_row[h_map["날짜"]] = str(a_d.strftime("%Y-%m-%d"))
                    if "활동명" in h_map: new_row[h_map["활동명"]] = a_t
                    if "세부내용" in h_map: new_row[h_map["세부내용"]] = a_c
                    if "공지사항" in h_map: new_row[h_map["공지사항"]] = a_n
                    if "등록일" in h_map: new_row[h_map["등록일"]] = str(datetime.datetime.now())
                    for k in range(1, 16):
                        if f"사진{k}" in h_map: new_row[h_map[f"사진{k}"]] = urls[k-1]
                    ws_act.append_row(new_row)
                    st.success("✅ 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 5] 출석 (UI 개선 #7, #8 적용)
# ==========================================
with tabs[5]:
    st.subheader("📅 주간 출석 현황")
    extended_weeks_list = weeks_list + ["✏️ 직접 입력 (새 날짜)"]
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1: 
            sel_w_raw = st.selectbox("출석 주차 / 기준일", extended_weeks_list, index=max(0, min(51, datetime.date.today().isocalendar()[1] - 1)), format_func=lambda x: week_display_map.get(x, x))
            if sel_w_raw == "✏️ 직접 입력 (새 날짜)": target_date = st.date_input("새로운 날짜 선택", datetime.date.today()); sel_w = target_date.strftime("%Y-%m-%d")
            else: sel_w = sel_w_raw; w_num = int(sel_w_raw.replace("주", "")); target_date = start_date + datetime.timedelta(days=(w_num-1)*7)
        with c2: sel_class = st.selectbox("반 필터", ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()], key=class_sort_key))
        show_inactive = st.checkbox("👀 강제 전체명단 표시 (이사/졸업 포함)")
    
    att_df = df.copy() if show_inactive else df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
    att_df['role'] = att_df.apply(get_role, axis=1)
    ui_s_df, ui_t_df = att_df[att_df['role'] == 'student'], att_df[att_df['role'] == 'teacher']
    s_p, t_p = len(ui_s_df[ui_s_df[sel_w].astype(str).str.strip() == "1"]), len(ui_t_df[ui_t_df[sel_w].astype(str).str.strip() == "1"])
    
    saved_guest = 0; saved_note = ""; saved_event = ""
    if not df_stat.empty and '주차' in df_stat.columns:
        match = df_stat[df_stat['주차'] == sel_w]
        if not match.empty: 
            try: saved_guest = int(match.iloc[0].get('추가', match.iloc[0].get('새친구/추가예배', 0)))
            except: pass
            saved_event = str(match.iloc[0].get('행사명', ''))
            saved_note = str(match.iloc[0].get('비고', match.iloc[0].get('내용(비고)', match.iloc[0].get('추가입력(비고)', ''))))

    st.markdown("#### 📊 실시간 체크 현황")
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric(f"유년부 출석 (재적 {len(ui_s_df)})", f"{s_p}명"); cs2.metric(f"선생님 출석 (재적 {len(ui_t_df)})", f"{t_p}명") 
    cs3.metric("유년부 합계 (출석+추가)", f"{s_p + saved_guest}명")
    
    with st.expander("🛠️ 추가 설정 (행사명 / 새친구 / 예외결석 입력)", expanded=bool(saved_event or saved_note or saved_guest)):
        c_e1, c_e2, c_e3 = st.columns([1, 2, 2])
        guest_in = c_e1.number_input("🎉 새친구/추가", min_value=0, value=saved_guest)
        event_text = c_e2.text_input("📢 행사명", value=saved_event, placeholder="예: 여름성경학교")
        custom_note = c_e3.text_input("📝 비고 (통계관리용)", value=saved_note, placeholder="예: 전원 야외 예배 등")
        is_skip = st.toggle("⚠️ 출석체크 쉼 (명단 전체를 결석 처리)")

    calc_total = guest_in if is_skip else (s_p + t_p + guest_in)
    st.markdown(f"<div class='total-summary'>✅ 저장 시 총합계 (전도사 제외, 유년부+교사): {calc_total}명</div>", unsafe_allow_html=True)

    with st.form("att_toggle_form"):
        new_att = {}
        if not is_skip:
            grouped = att_df.sort_values(by=['이름']).groupby(class_col)
            for c_name in sorted(grouped.groups.keys(), key=class_sort_key):
                st.markdown(f"<div class='class-header'>🏷️ {c_name}</div>", unsafe_allow_html=True)
                cols = st.columns(3)
                for i, (idx, row) in enumerate(grouped.get_group(c_name).iterrows()):
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    prefix = f"🚫 " if row[status_col] in INACTIVE_STATUS else ("🌱 " if row[status_col] == '새친구' else "✝️ " if row['role'] == 'pastor' else "🧑‍🏫 " if row['role'] == 'teacher' else "👤 ")
                    new_att[row['sheet_row']] = cols[i%3].toggle(f"{prefix}{row['이름']}", value=is_on, key=f"tgl_{row['sheet_row']}_{sel_w}")
        
        if st.form_submit_button("💾 데이터 저장 (교적부/통계 반영)", type="primary", use_container_width=True):
            with st.spinner("저장 중..."):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: 
                    try: ws.update_cell(1, target_c, sel_w)
                    except: ws.add_cols(10); ws.update_cell(1, target_c, sel_w)
                
                final_s_p = 0; final_t_p = 0; cells_to_update = []
                if not is_skip:
                    for r, v in new_att.items():
                        row_data = att_df[att_df['sheet_row'] == r]
                        if not row_data.empty and v:
                            role = row_data.iloc[0]['role']
                            if role == 'student': final_s_p += 1
                            elif role == 'teacher': final_t_p += 1 
                    for r, v in new_att.items():
                        cells_to_update.append(gspread.Cell(int(r), target_c, "1" if v else ""))
                    if cells_to_update: chunked_update(ws, cells_to_update)
                
                save_s_p = 0 if is_skip else final_s_p
                save_t_p = 0 if is_skip else final_t_p
                valid_enrollment_df = df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
                valid_enrollment_df['role'] = valid_enrollment_df.apply(get_role, axis=1)
                student_count, teacher_count = len(valid_enrollment_df[valid_enrollment_df['role'] == 'student']), len(valid_enrollment_df[valid_enrollment_df['role'] == 'teacher'])
                
                kids_total = save_s_p + guest_in
                grand_total = kids_total + save_t_p
                
                stat_headers = [str(h).strip() for h in ws_stat.row_values(1)]
                
                def norm_text(t): return re.sub(r'\s+', '', str(t))
                h_map = {norm_text(h): idx for idx, h in enumerate(stat_headers)}
                
                req_headers_order = ["주차", "행사명", "유년부 재적", "출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"]
                
                missing_headers = [h for h in req_headers_order if norm_text(h) not in h_map]
                if missing_headers:
                    try: ws_stat.add_cols(len(missing_headers) + 5)
                    except: pass
                    
                    start_col = len(stat_headers) + 1
                    h_cells = []
                    for i, mh in enumerate(missing_headers):
                        stat_headers.append(mh)
                        h_map[norm_text(mh)] = len(stat_headers) - 1
                        h_cells.append(gspread.Cell(1, start_col + i, mh))
                    chunked_update(ws_stat, h_cells)
                
                new_row = [""] * len(stat_headers)
                val_map = {
                    norm_text("주차"): sel_w,
                    norm_text("행사명"): event_text,
                    norm_text("유년부 재적"): student_count,
                    norm_text("출석"): save_s_p,
                    norm_text("추가"): guest_in,
                    norm_text("유년부 합계"): kids_total,
                    norm_text("교사재적"): teacher_count,
                    norm_text("교사출석"): save_t_p,
                    norm_text("총합"): grand_total,
                    norm_text("비고"): custom_note,
                    norm_text("업데이트일시"): str(datetime.datetime.now())
                }
                
                for key_norm, value in val_map.items():
                    if key_norm in h_map:
                        new_row[h_map[key_norm]] = value
                        
                match_stat = df_stat[df_stat['주차'] == sel_w] if not df_stat.empty else pd.DataFrame()
                if not match_stat.empty: 
                    row_idx = match_stat.index[0] + 2
                    end_col = chr(65 + len(stat_headers) - 1) if len(stat_headers) <= 26 else 'Z'
                    ws_stat.update(f"A{row_idx}:{end_col}{row_idx}", [new_row])
                else: 
                    ws_stat.append_row(new_row)
                
                st.success(f"✅ [{sel_w}] 기존 데이터 위치에 정확히 오버라이드 저장 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 6] 통계
# ==========================================
with tabs[6]:
    st.subheader("📊 통계")
    col_stat, col_cumul = st.columns([2, 1])
    with col_stat: 
        st.write("📅 **주차별 흐름 통계 (지정 순서 고정)**")
        st.caption("💡 **색상 안내:** 🟥 **붉은색 행** = 전체 결석(0명) 행 &nbsp;|&nbsp; 🟦 **푸른색 텍스트** = 핵심 지표(유년부 합계, 총합)")
        
        if not df_stat.empty:
            df_stat_calc = df_stat.copy()
            df_stat_calc['sort_date'] = df_stat_calc['주차'].apply(get_date_from_week_str)
            df_stat_calc = df_stat_calc.sort_values(by='sort_date', ascending=False).drop(columns=['sort_date'])
            
            rename_dict = {'학생재적': '유년부 재적', '학생출석': '출석', '새친구/추가예배': '추가', '총합계': '총합', '유년부합계': '유년부 합계', '추가입력(비고)': '비고', '내용(비고)': '행사명'}
            df_stat_renamed = df_stat_calc.rename(columns=rename_dict)
            df_stat_renamed.columns = [str(c).strip() for c in df_stat_renamed.columns]
            df_stat_renamed = df_stat_renamed.loc[:, ~df_stat_renamed.columns.duplicated()]
            
            preferred_order = ["주차", "행사명", "유년부 재적", "출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"]
            actual_order = [c for c in preferred_order if c in df_stat_renamed.columns]
            for c in df_stat_renamed.columns:
                if c not in actual_order: actual_order.append(c)
                
            df_stat_display = df_stat_renamed[actual_order]
            
            def highlight_stat_cells(row):
                try: att = int(row['출석'])
                except: att = -1
                if att == 0:
                    return ['background-color: #ffebee; color: #d32f2f; font-weight: bold;' for _ in row.index]
                
                styles = ['' for _ in row.index]
                for target_col in ['유년부 합계', '총합']:
                    if target_col in row.index:
                        col_idx = row.index.get_loc(target_col)
                        styles[col_idx] = 'background-color: #e3f2fd; color: #0366d6; font-weight: 800;'
                return styles
            
            styled_df = df_stat_display.style.apply(highlight_stat_cells, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

    with col_cumul: 
        st.write("👤 **개인별 누적 출석**")
        report_df = df[~df[status_col].isin(INACTIVE_STATUS)].copy()
        week_cols = [c for c in report_df.columns if c.endswith('주')]
        report_df['출석수'] = report_df[week_cols].apply(lambda x: x.astype(str).str.strip().eq('1').sum(), axis=1)
        
        student_report = report_df[report_df.apply(get_role, axis=1) == 'student']
        student_report = student_report[student_report['출석수'] > 0]
        if not student_report.empty:
            unique_scores = sorted(student_report['출석수'].unique(), reverse=True)[:3]
            if unique_scores:
                st.markdown("<div style='background-color:#f1f8ff; padding:15px; border-radius:10px; margin-bottom:15px; border:1px solid #cce5ff;'><h5 style='color:#0366d6; margin-top:0;'>🏆 누적 출석 TOP 3</h5>", unsafe_allow_html=True)
                medals = ["🥇", "🥈", "🥉"]
                for i, score in enumerate(unique_scores):
                    group = student_report[student_report['출석수'] == score]
                    names = ", ".join([f"{row['이름']}" for _, row in group.iterrows()])
                    st.markdown(f"**{medals[i]} {score}회** : {names}")
                st.markdown("</div>", unsafe_allow_html=True)
                
        st.dataframe(report_df[[class_col, '이름', '출석수']], use_container_width=True, hide_index=True)

# ==========================================
# [탭 7] 총무 전용 - 비용집행관리 (비밀번호 시크릿 보안 적용)
# ==========================================
with tabs[7]:
    if not st.session_state['chongmu_auth']:
        st.warning("🔒 총무 권한이 필요한 메뉴입니다.")
        cpwd = st.text_input("총무 전용 비밀번호를 입력하세요", type="password", key="pwd_receipt")
        if st.button("인증", key="btn_auth_receipt"):
            if cpwd == st.secrets.get("chongmu_password", "admin1234"): 
                st.session_state['chongmu_auth'] = True; st.rerun()
            else: st.error("❌ 비밀번호가 일치하지 않습니다.")
    else:
        st.subheader("🧾 비용집행관리")
        
        if not df_r.empty:
            df_r_calc = df_r.copy()
            df_r_calc['날짜_dt'] = pd.to_datetime(df_r_calc['날짜'], errors='coerce')
            curr_month = datetime.date.today().replace(day=1)
            this_month_df = df_r_calc[df_r_calc['날짜_dt'].dt.date >= curr_month]
            monthly_cost = pd.to_numeric(this_month_df['비용'], errors='coerce').sum()
            total_cost = pd.to_numeric(df_r_calc['비용'], errors='coerce').sum()
            
            mc1, mc2 = st.columns(2)
            mc1.metric(f"이번 달 ({curr_month.month}월) 집행액", f"{int(monthly_cost):,}원")
            mc2.metric("전체 누적 집행액", f"{int(total_cost):,}원")
            
            st.markdown("---")
            with st.expander("📅 월별 진행 현황 요약 (결산 추이)", expanded=True):
                df_r_calc['집행월'] = df_r_calc['날짜_dt'].dt.strftime('%Y-%m')
                df_r_calc['비용_num'] = pd.to_numeric(df_r_calc['비용'], errors='coerce').fillna(0)
                monthly_status = df_r_calc.groupby('집행월')['비용_num'].sum().reset_index()
                monthly_status.columns = ['지출 결산 월', '총 집행 금액']
                monthly_status['총 집행 금액'] = monthly_status['총 집행 금액'].apply(lambda x: f"{int(x):,}원")
                st.dataframe(monthly_status, use_container_width=True, hide_index=True)
                
        st.divider()

        mode_r = st.radio("메뉴 선택", ["👀 조회 및 출력", "➕ 신규 등록", "📝 내역 수정", "🚨 내역 삭제"], horizontal=True)
        
        if mode_r == "👀 조회 및 출력":
            if not df_r.empty:
                with st.container(border=True):
                    col_f1, col_f2 = st.columns(2)
                    min_d, max_d = df_r_calc['날짜_dt'].min(), df_r_calc['날짜_dt'].max()
                    min_date = min_d.date() if pd.notnull(min_d) else datetime.date.today()
                    max_date = max_d.date() if pd.notnull(max_d) else datetime.date.today()
                    
                    date_range = col_f1.date_input("조회 기간 선택", [min_date, max_date])
                    keyword = col_f2.text_input("검색어 (상호명 또는 내용)", placeholder="검색어를 입력하세요")
                
                if len(date_range) == 2: s_date, e_date = date_range
                else: s_date, e_date = min_date, max_date
                
                df_r_filtered = df_r_calc[(df_r_calc['날짜_dt'].dt.date >= s_date) & (df_r_calc['날짜_dt'].dt.date <= e_date)].copy()
                if keyword:
                    df_r_filtered = df_r_filtered[df_r_filtered.apply(lambda row: keyword in str(row.get('구매처','')) or keyword in str(row.get('내용','')), axis=1)]
                
                if not df_r_filtered.empty:
                    display_cols = ['번호', '날짜', '구매처', '내용', '비용', '비고']
                    st.dataframe(df_r_filtered[display_cols], use_container_width=True, hide_index=True, column_config={
                        "비용": st.column_config.NumberColumn("비용", format="%d원")
                    })
                    
                    total_filtered_cost = pd.to_numeric(df_r_filtered['비용'], errors='coerce').sum()
                    
                    st.download_button(
                        label="📊 현재 조회 내역 엑셀(CSV) 다운로드",
                        data=df_r_filtered[display_cols].to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"비용집행내역_{s_date}_{e_date}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    st.info("💡 아래 버튼을 눌러 인쇄용 문서를 다운로드한 후 브라우저에서 열고 `Ctrl + P` (PDF로 저장)를 진행하세요.")
                    
                    # 에러 원천 차단: parse_int_safe 함수 활용 HTML 리포트 생성
                    html_content = f"""
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>비용집행 보고서</title>
                        <style>
                            body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; margin: 40px; color: #333; }}
                            h1, h2 {{ text-align: center; color: #0366d6; }}
                            table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; page-break-inside: auto; }}
                            tr {{ page-break-inside: avoid; page-break-after: auto; }}
                            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: center; font-size: 14px; }}
                            th {{ background-color: #f1f8ff; }}
                            .summary {{ font-size: 18px; font-weight: bold; text-align: right; margin-bottom: 20px; border-bottom: 2px solid #0366d6; padding-bottom: 10px; }}
                            .receipt-section {{ page-break-before: always; }}
                            .receipt-box {{ margin-bottom: 20px; page-break-inside: avoid; border: 1px solid #eee; padding: 15px; border-radius: 8px; background-color: #fafafa; }}
                            .receipt-box img {{ max-width: 100%; max-height: 420px; display: block; margin: 10px auto; object-fit: contain; }}
                            @media print {{ body {{ margin: 0; }} }}
                        </style>
                    </head>
                    <body>
                        <h1>비용집행 장부 보고서 (요약본)</h1>
                        <div class="summary">
                            조회 기간: {s_date} ~ {e_date} &nbsp;&nbsp;|&nbsp;&nbsp; 기간 내 총합계금액: {int(total_filtered_cost):,}원
                        </div>
                        
                        <h2>📊 지출 내역 요약 일람표</h2>
                        <table>
                            <thead>
                                <tr><th>번호</th><th>날짜</th><th>구매처</th><th>내용</th><th>비용(원)</th><th>비고</th></tr>
                            </thead>
                            <tbody>
                    """
                    for _, row in df_r_filtered.iterrows():
                        html_content += f"<tr><td>{row.get('번호','')}</td><td>{row.get('날짜','')}</td><td>{row.get('구매처','')}</td><td>{row.get('내용','')}</td><td>{parse_int_safe(row.get('비용', 0)):,}</td><td>{row.get('비고','')}</td></tr>"
                    html_content += "</tbody></table>"
                    
                    html_content += "<div class='receipt-section'><h2>📸 지출 증빙 영수증 사본 첨부 (순차 정렬)</h2>"
                    for _, row in df_r_filtered.iterrows():
                        img_url = str(row.get('영수증사진',''))
                        if img_url and str(img_url).startswith('http'):
                            clean_url = img_url.replace("&vid=1", "").replace("?vid=1", "")
                            html_content += f"""
                            <div class="receipt-box">
                                <strong>[순번 No.{row.get('번호','')}] {row.get('날짜','')} - {row.get('구매처','')} ({parse_int_safe(row.get('비용', 0)):,}원)</strong>
                                <br><small>지출내역: {row.get('내용','')} | 비고: {row.get('비고','')}</small>
                                <img src="{clean_url}" alt="영수증 사본">
                            </div>
                            """
                    html_content += "</div></body></html>"
                    
                    st.download_button(
                        label="📄 PDF/인쇄용 보고서 다운로드 (HTML)",
                        data=html_content.encode("utf-8"),
                        file_name=f"비용집행보고서_{s_date}_{e_date}.html",
                        mime="text/html",
                        use_container_width=True
                    )
                else:
                    st.warning("조건에 맞는 내역이 없습니다.")
            else:
                st.info("등록된 비용 집행 내역이 없습니다.")
                
        elif mode_r == "➕ 신규 등록":
            with st.form("new_receipt_form"):
                rc_date = st.date_input("날짜", datetime.date.today()).strftime("%Y-%m-%d")
                rc_vendor = st.text_input("구매처 (상호명)")
                rc_detail = st.text_input("내용 (품목)")
                rc_cost = st.number_input("비용 (원)", min_value=0, step=1000)
                rc_memo = st.text_input("비고")
                rc_photo = st.file_uploader("영수증 사진 업로드", type=['png', 'jpg', 'jpeg'])
                
                if st.form_submit_button("등록 완료", type="primary"):
                    with st.spinner("업로드 및 저장 중..."):
                        p_url = upload_photo(rc_photo, f"영수증_{rc_vendor}") if rc_photo else ""
                        new_num = len(df_r) + 1 if not df_r.empty else 1
                        ws_r.append_row([new_num, rc_date, rc_vendor, rc_detail, rc_cost, rc_memo, p_url])
                        st.success("등록되었습니다!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

        elif mode_r == "📝 내역 수정" and not df_r.empty:
            options = ["내역 선택"] + df_r.apply(lambda r: f"No.{r.get('번호','')} | {r.get('날짜','')} | {r.get('구매처','')} | {r.get('비용','')}원", axis=1).tolist()
            sel_idx = st.selectbox("수정할 내역", range(len(options)), format_func=lambda x: options[x])
            if sel_idx > 0:
                target = df_r.iloc[sel_idx - 1]
                with st.form("edit_receipt_form"):
                    e_date = st.date_input("날짜", parse_date_safe(target.get('날짜',''))).strftime("%Y-%m-%d")
                    e_vendor = st.text_input("구매처 (상호명)", value=target.get('구매처',''))
                    e_detail = st.text_input("내용 (품목)", value=target.get('내용',''))
                    e_cost = st.number_input("비용 (원)", value=parse_int_safe(target.get('비용', 0)), step=1000)
                    e_memo = st.text_input("비고", value=target.get('비고',''))
                    e_photo = st.file_uploader("영수증 사진 변경 (새로 올리면 기존 사진 대체)", type=['png', 'jpg', 'jpeg'])
                    
                    if st.form_submit_button("수정 저장", type="primary"):
                        with st.spinner("저장 중..."):
                            p_url = upload_photo(e_photo, f"영수증_{e_vendor}") if e_photo else target.get('영수증사진','')
                            r_idx = int(target['sheet_row'])
                            
                            cells = [
                                gspread.Cell(r_idx, 2, e_date),
                                gspread.Cell(r_idx, 3, e_vendor),
                                gspread.Cell(r_idx, 4, e_detail),
                                gspread.Cell(r_idx, 5, str(e_cost)),
                                gspread.Cell(r_idx, 6, e_memo),
                                gspread.Cell(r_idx, 7, p_url)
                            ]
                            chunked_update(ws_r, cells)
                            st.success("수정 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

        elif mode_r == "🚨 내역 삭제" and not df_r.empty:
            options = ["내역 선택"] + df_r.apply(lambda r: f"No.{r.get('번호','')} | {r.get('날짜','')} | {r.get('구매처','')} | {r.get('비용','')}원", axis=1).tolist()
            sel_idx = st.selectbox("삭제할 내역", range(len(options)), format_func=lambda x: options[x])
            if st.button("🚨 삭제 실행") and sel_idx > 0:
                target = df_r.iloc[sel_idx - 1]
                ws_r.delete_rows(int(target['sheet_row']))
                st.success("삭제되었습니다!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 8] 총무 전용 - 회비관리 (비밀번호 시크릿 보안 적용)
# ==========================================
with tabs[8]:
    if not st.session_state['chongmu_auth']:
        st.warning("🔒 총무 권한이 필요한 메뉴입니다.")
        cpwd2 = st.text_input("총무 전용 비밀번호를 입력하세요", type="password", key="pwd_ledger")
        if st.button("인증", key="btn_auth_ledger"):
            if cpwd2 == st.secrets.get("chongmu_password", "admin1234"): 
                st.session_state['chongmu_auth'] = True; st.rerun()
            else: st.error("❌ 비밀번호가 일치하지 않습니다.")
    else:
        st.subheader("💰 회비관리 장부")
        
        with st.container(border=True):
            total_in = pd.to_numeric(df_in['입금액'], errors='coerce').sum() if not df_in.empty else 0
            total_out = pd.to_numeric(df_out['지출액'], errors='coerce').sum() if not df_out.empty else 0
            balance = total_in - total_out
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("🟢 누적 수입 (입금액)", f"{int(total_in):,}원")
            col_m2.metric("🔴 누적 지출 (지출액)", f"{int(total_out):,}원")
            col_m3.metric("💲 현재 잔액 (총 합계)", f"{int(balance):,}원")
        st.divider()
        
        mode_l = st.radio("메뉴 선택", ["👀 전체 장부 조회", "➕ 내역 등록(입금/지출)", "📝 내역 수정", "🚨 내역 삭제"], horizontal=True)
        
        if mode_l == "👀 전체 장부 조회":
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                st.markdown("##### 📥 수입 (입금 내역)")
                if not df_in.empty: 
                    st.dataframe(df_in[['날짜', '입금자명', '입금액', '비고']], use_container_width=True, hide_index=True)
                    st.download_button("📥 수입내역 엑셀 다운로드", data=df_in.to_csv(index=False).encode('utf-8-sig'), file_name="회비_수입내역.csv", mime="text/csv", use_container_width=True)
                else: st.info("수입 내역이 없습니다.")
            with col_l2:
                st.markdown("##### 📤 지출 (집행 내역)")
                if not df_out.empty: 
                    st.dataframe(df_out[['날짜', '내용', '지출액', '비고']], use_container_width=True, hide_index=True)
                    st.download_button("📤 지출내역 엑셀 다운로드", data=df_out.to_csv(index=False).encode('utf-8-sig'), file_name="회비_지출내역.csv", mime="text/csv", use_container_width=True)
                else: st.info("지출 내역이 없습니다.")
            
            st.markdown("---")
            st.markdown("##### 📄 회비관리 전체 보고서 출력 (인쇄/PDF 저장)")
            
            # 에러 원천 차단된 parse_int_safe 함수 활용 HTML 리포트 생성
            html_ledger = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>회비 관리 보고서</title>
                <style>
                    body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; margin: 40px; color: #333; }}
                    h1, h2 {{ text-align: center; color: #0366d6; }}
                    .summary-box {{ padding: 15px; background-color: #f1f8ff; border: 1px solid #cce5ff; border-radius: 8px; margin-bottom: 25px; font-size: 15px; font-weight: bold; text-align: center; }}
                    table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; page-break-inside: auto; }}
                    tr {{ page-break-inside: avoid; page-break-after: auto; }}
                    th, td {{ border: 1px solid #ddd; padding: 10px; text-align: center; font-size: 13px; }}
                    th {{ background-color: #f1f8ff; }}
                    .receipt-section {{ page-break-before: always; }}
                    .receipt-box {{ margin-bottom: 20px; page-break-inside: avoid; border: 1px solid #eee; padding: 15px; border-radius: 8px; background-color: #fbfbfb; }}
                    .receipt-box img {{ max-width: 100%; max-height: 400px; display: block; margin: 10px auto; object-fit: contain; }}
                </style>
            </head>
            <body>
                <h1>교회 회비 결산 결재 보고서</h1>
                <div class="summary-box">
                    보고서 출력일: {datetime.date.today().strftime('%Y-%m-%d')} &nbsp;&nbsp;|&nbsp;&nbsp; 🟢 누적 수입: {int(total_in):,}원 &nbsp;&nbsp;|&nbsp;&nbsp; 🔴 누적 지출: {int(total_out):,}원 &nbsp;&nbsp;|&nbsp;&nbsp; 💲 현재 잔액: {int(balance):,}원
                </div>
                
                <h2>📥 1. 회비 입금 내역 요약표</h2>
                <table>
                    <thead>
                        <tr><th>번호</th><th>날짜</th><th>입금자명</th><th>입금액(원)</th><th>비고</th></tr>
                    </thead>
                    <tbody>
            """
            if not df_in.empty:
                for _, row in df_in.iterrows():
                    html_ledger += f"<tr><td>{row.get('번호','')}</td><td>{row.get('날짜','')}</td><td>{row.get('입금자명','')}</td><td>{parse_int_safe(row.get('입금액', 0)):,}</td><td>{row.get('비고','')}</td></tr>"
            else:
                html_ledger += "<tr><td colspan='5'>입금 내역이 존재하지 않습니다.</td></tr>"
                
            html_ledger += """
                    </tbody>
                </table>
                
                <h2>📤 2. 회비 지출 내역 요약표</h2>
                <table>
                    <thead>
                        <tr><th>번호</th><th>날짜</th><th>내용</th><th>지출액(원)</th><th>비고</th></tr>
                    </thead>
                    <tbody>
            """
            if not df_out.empty:
                for _, row in df_out.iterrows():
                    html_ledger += f"<tr><td>{row.get('번호','')}</td><td>{row.get('날짜','')}</td><td>{row.get('내용','')}</td><td>{parse_int_safe(row.get('지출액', 0)):,}</td><td>{row.get('비고','')}</td></tr>"
            else:
                html_ledger += "<tr><td colspan='5'>지출 내역이 존재하지 않습니다.</td></tr>"
                
            html_ledger += """
                    </tbody>
                </table>
                
                <div class="receipt-section">
                    <h2>📸 3. 회비 지출 증빙 영수증 사본 목록</h2>
            """
            if not df_out.empty:
                for _, row in df_out.iterrows():
                    img_url = str(row.get('영수증사진',''))
                    if img_url and img_url.startswith('http'):
                        clean_url = img_url.replace("&vid=1", "").replace("?vid=1", "")
                        html_ledger += f"""
                        <div class="receipt-box">
                            <strong>[지출 No.{row.get('번호','').strip()}] {row.get('날짜','')} - {row.get('내용','')} ({parse_int_safe(row.get('지출액', 0)):,}원)</strong>
                            <br><small>비고 내역: {row.get('비고','')}</small>
                            <img src="{clean_url}" alt="회비 영수증">
                        </div>
                        """
            else:
                html_ledger += "<p style='text-align:center; color:gray;'>증빙된 영수증 사본이 존재하지 않습니다.</p>"
                
            html_ledger += """
                </div>
            </body>
            </html>
            """
            
            st.download_button(
                label="📄 회비장부 전체 PDF 인쇄용 다운로드 (HTML 형식)",
                data=html_ledger.encode("utf-8"),
                file_name=f"회비결산보고서_{datetime.date.today()}.html",
                mime="text/html",
                use_container_width=True
            )

        elif mode_l == "➕ 내역 등록(입금/지출)":
            tab_in, tab_out = st.tabs(["📥 회비 입금 등록", "📤 회비 지출 등록"])
            with tab_in:
                with st.form("new_income_form"):
                    col_i1, col_i2 = st.columns(2)
                    in_date = col_i1.date_input("입금 일자", datetime.date.today()).strftime("%Y-%m-%d")
                    in_name = col_i2.text_input("입금자명")
                    in_amount = col_i1.number_input("입금액 (원)", min_value=0, step=1000)
                    in_memo = col_i2.text_input("비고")
                    if st.form_submit_button("입금 내역 추가", type="primary"):
                        new_num = len(df_in) + 1 if not df_in.empty else 1
                        ws_in.append_row([new_num, in_date, in_name, in_amount, in_memo])
                        st.success("입금 등록 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
            with tab_out:
                with st.form("new_expense_form"):
                    col_o1, col_o2 = st.columns(2)
                    out_date = col_o1.date_input("지출 일자", datetime.date.today()).strftime("%Y-%m-%d")
                    out_detail = col_o2.text_input("내용")
                    out_amount = col_o1.number_input("지출액 (원)", min_value=0, step=1000)
                    out_memo = col_o2.text_input("비고")
                    out_photo = st.file_uploader("지출 증빙(영수증) 업로드", type=['png', 'jpg', 'jpeg'])
                    if st.form_submit_button("지출 내역 추가", type="primary"):
                        with st.spinner("업로드 중..."):
                            p_url = upload_photo(out_photo, f"회비지출_{out_detail}") if out_photo else ""
                            new_num = len(df_out) + 1 if not df_out.empty else 1
                            ws_out.append_row([new_num, out_date, out_detail, out_amount, out_memo, p_url])
                            st.success("지출 등록 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
        
        elif mode_l == "📝 내역 수정":
            e_type = st.radio("수정할 장부", ["입금 장부", "지출 장부"], horizontal=True)
            if e_type == "입금 장부" and not df_in.empty:
                opts = ["내역 선택"] + df_in.apply(lambda r: f"[{r.get('날짜','')} | {r.get('입금자명','')} | {r.get('입금액','')}원", axis=1).tolist()
                idx = st.selectbox("수정할 입금 내역", range(len(opts)), format_func=lambda x: opts[x])
                if idx > 0:
                    t = df_in.iloc[idx - 1]
                    with st.form("edit_in_form"):
                        e_d = st.date_input("날짜", parse_date_safe(t.get('날짜',''))).strftime("%Y-%m-%d")
                        e_n = st.text_input("입금자명", value=t.get('입금자명',''))
                        e_a = st.number_input("입금액", value=parse_int_safe(t.get('입금액', 0)), step=1000)
                        e_m = st.text_input("비고", value=t.get('비고',''))
                        if st.form_submit_button("수정 저장", type="primary"):
                            r_idx = int(t['sheet_row'])
                            chunked_update(ws_in, [gspread.Cell(r_idx, 2, e_d), gspread.Cell(r_idx, 3, e_n), gspread.Cell(r_idx, 4, str(e_a)), gspread.Cell(r_idx, 5, e_m)])
                            st.success("수정 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
            elif e_type == "지출 장부" and not df_out.empty:
                opts = ["내역 선택"] + df_out.apply(lambda r: f"[{r.get('날짜','')} | {r.get('내용','')} | {r.get('지출액','')}원", axis=1).tolist()
                idx = st.selectbox("수정할 지출 내역", range(len(opts)), format_func=lambda x: opts[x])
                if idx > 0:
                    t = df_out.iloc[idx - 1]
                    with st.form("edit_out_form"):
                        e_d = st.date_input("날짜", parse_date_safe(t.get('날짜',''))).strftime("%Y-%m-%d")
                        e_c = st.text_input("내용", value=t.get('내용',''))
                        e_a = st.number_input("지출액", value=parse_int_safe(t.get('지출액', 0)), step=1000)
                        e_m = st.text_input("비고", value=t.get('비고',''))
                        e_p = st.file_uploader("영수증 변경", type=['png', 'jpg', 'jpeg'])
                        if st.form_submit_button("수정 저장", type="primary"):
                            with st.spinner("업로드 중..."):
                                p_url = upload_photo(e_p, f"회비지출_{e_c}") if e_p else t.get('영수증사진','')
                                r_idx = int(t['sheet_row'])
                                chunked_update(ws_out, [gspread.Cell(r_idx, 2, e_d), gspread.Cell(r_idx, 3, e_c), gspread.Cell(r_idx, 4, str(e_a)), gspread.Cell(r_idx, 5, e_m), gspread.Cell(r_idx, 6, p_url)])
                                st.success("수정 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

        elif mode_l == "🚨 내역 삭제":
            d_type = st.radio("삭제할 장부", ["입금 장부", "지출 장부"], horizontal=True)
            if d_type == "입금 장부" and not df_in.empty:
                opts = ["내역 선택"] + df_in.apply(lambda r: f"[{r.get('날짜','')} | {r.get('입금자명','')} | {r.get('입금액','')}원", axis=1).tolist()
                idx = st.selectbox("삭제할 내역", range(len(opts)), format_func=lambda x: opts[x])
                if st.button("🚨 입금 삭제 실행") and idx > 0:
                    ws_in.delete_rows(int(df_in.iloc[idx-1]['sheet_row']))
                    st.success("삭제 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
            elif d_type == "지출 장부" and not df_out.empty:
                opts = ["내역 선택"] + df_out.apply(lambda r: f"[{r.get('날짜','')} | {r.get('내용','')} | {r.get('지출액','')}원", axis=1).tolist()
                idx = st.selectbox("삭제할 내역", range(len(opts)), format_func=lambda x: opts[x])
                if st.button("🚨 지출 삭제 실행") and idx > 0:
                    ws_out.delete_rows(int(df_out.iloc[idx-1]['sheet_row']))
                    st.success("삭제 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
