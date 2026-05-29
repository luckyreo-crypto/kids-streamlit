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
st.set_page_config(page_title="26년 슈팅스타 통합관리 V2.0(모바일)", page_icon="🌱", layout="wide")
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

# 모바일 UI 최적화 적용 CSS (버튼 크기 확대, 줄바꿈 강제, 플로팅 버튼 우측 하단 등)
st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 16px !important; }
    .class-header { background-color: #f1f8ff; padding: 15px 20px; border-radius: 10px; color: #0366d6; font-weight: 900; font-size: 1.2rem; margin-top: 25px; margin-bottom: 15px; border-left: 6px solid #0366d6; }
    div[data-testid="stToggle"] { border: 2px solid #eef2f6; padding: 15px 20px; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 12px; }
    div[data-testid="stToggle"]:hover { border-color: #0366d6; background-color: #f8fbff; }
    div[data-testid="stButton"] button { width: 100%; border-radius: 8px; text-align: left; padding: 12px 15px; font-size: 1.05rem; white-space: normal; word-wrap: break-word; word-break: keep-all; min-height: 48px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    input, select, textarea { font-size: 1.05rem !important; min-height: 48px !important; }
    .media-link img:hover { transform: scale(1.02); filter: brightness(0.95); cursor: zoom-in; }
    .small-btn button { padding: 0px 5px !important; font-size: 0.9rem !important; height: auto !important; min-height: 35px !important; margin-top: 0px; text-align: center; }
    div[data-testid="stTabs"] { overflow: visible !important; }
    div[data-testid="stTabs"] > div:first-child { position: -webkit-sticky !important; position: sticky !important; top: 3.5rem !important; background-color: #ffffff !important; z-index: 999990 !important; padding: 10px 0 !important; border-bottom: 2px solid #eef2f6 !important; }
    div[data-baseweb="tab-list"] { display: flex; flex-wrap: wrap !important; gap: 5px; justify-content: flex-start; padding-bottom: 5px; }
    div[data-baseweb="tab"] { flex: 0 0 auto !important; justify-content: center; padding: 10px 15px !important; margin: 2px !important; background-color: #f8f9fa; border-radius: 10px; border: 1px solid #ddd; }
    div[data-baseweb="tab"][aria-selected="true"] { background-color: #0366d6 !important; color: white !important; border: 1px solid #0366d6; }
    div[data-baseweb="tab"] p { font-size: 1.05rem !important; font-weight: 800 !important; white-space: nowrap; margin: 0; }
    .fab-button { position: fixed; bottom: 25px; right: 25px; left: auto; background-color: rgba(3, 102, 214, 0.9); color: white !important; padding: 15px 25px; border-radius: 40px; text-decoration: none; font-weight: 900; font-size: 1.1rem; box-shadow: 0 5px 15px rgba(0,0,0,0.4); z-index: 999999; }
    .fab-button:hover { background-color: rgba(3, 102, 214, 1); transform: translateY(-3px); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 시스템 접근 제어 및 글로벌 상태 초기화 ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if 'privacy_mode' not in st.session_state: st.session_state['privacy_mode'] = True
if 'chongmu_auth' not in st.session_state: st.session_state['chongmu_auth'] = False

if not st.session_state["authenticated"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center; color: #0366d6;'>🌱 슈팅스타 통합관리 V2.0</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray; margin-bottom: 20px;'>안전한 시스템 접근을 위해 관리자 비밀번호를 입력해주세요.</p>", unsafe_allow_html=True)
            pwd = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력", label_visibility="collapsed")
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
        ws_s = sh.add_worksheet("주차별통계", 200, 15); ws_s.append_row(["주차", "행사명", "유년부 재적", "출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"])
        
    try: ws_r = sh.worksheet("영수증")
    except: ws_r = sh.add_worksheet("영수증", 500, 10); ws_r.append_row(["번호", "날짜", "구매처", "내용", "비용", "비고", "영수증사진"])
    
    try: ws_in = sh.worksheet("회비입금")
    except: ws_in = sh.add_worksheet("회비입금", 500, 10); ws_in.append_row(["번호", "날짜", "입금자명", "입금액", "비고"])
    
    try: ws_out = sh.worksheet("회비지출")
    except: ws_out = sh.add_worksheet("회비지출", 500, 10); ws_out.append_row(["번호", "날짜", "내용", "지출액", "비고", "영수증사진"])

    try: ws_p = sh.worksheet("기도순서")
    except: ws_p = sh.add_worksheet("기도순서", 500, 5); ws_p.append_row(["번호", "날짜", "이름", "비고"])
        
    try: ws_b = sh.worksheet("주보관리")
    except: ws_b = sh.add_worksheet("주보관리", 60, 10); ws_b.append_row(["주차", "날짜", "주보이미지1", "주보이미지2", "비고", "업데이트일시"])

    return ws_m, ws_a, ws_s, ws_r, ws_in, ws_out, ws_p, ws_b

@st.cache_data(ttl=600)
def fetch_sheet_data():
    ws_m, ws_a, ws_s, ws_r, ws_in, ws_out, ws_p, ws_b = get_worksheets()
    return ws_m.get_all_values(), ws_a.get_all_values(), ws_s.get_all_values(), ws_r.get_all_values(), ws_in.get_all_values(), ws_out.get_all_values(), ws_p.get_all_values(), ws_b.get_all_values()

def get_all_data():
    try:
        ws_m, ws_a, ws_s, ws_r, ws_in, ws_out, ws_p, ws_b = get_worksheets()
        vals_m, vals_a, vals_s, vals_r, vals_in, vals_out, vals_p, vals_b = fetch_sheet_data()
        
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
        df_p = pd.DataFrame(vals_p[1:], columns=vals_p[0]) if len(vals_p) > 1 else pd.DataFrame()
        if not df_p.empty: df_p['sheet_row'] = range(2, len(df_p) + 2)
        df_b = pd.DataFrame(vals_b[1:], columns=vals_b[0]) if len(vals_b) > 1 else pd.DataFrame()
        if not df_b.empty: df_b['sheet_row'] = range(2, len(df_b) + 2)
        
        return ws_m, df_m, vals_m[0], ws_a, df_a, ws_s, df_s, ws_r, df_r, ws_in, df_in, ws_out, df_out, ws_p, df_p, ws_b, df_b
    except Exception as e: return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat, ws_r, df_r, ws_in, df_in, ws_out, df_out, ws_p, df_p, ws_b, df_b = get_all_data()

if df is None or df.empty:
    st.warning("⚠️ 데이터 로딩 중입니다. 잠시만 기다려주세요.")
    st.stop()

class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')
status_col = '학교상태' if '학교상태' in df.columns else '상태'

weeks_list = [f"{i}주" for i in range(1, 53)]
week_display_map = {f"{i}주": format_week_display(f"{i}주") for i in range(1, 53)}

# --- 다이얼로그 모달: 주보 보기 ---
@st.dialog("📖 주보 보기", width="large")
def view_bulletin_dialog(w_str, d_str, row_data):
    st.markdown(f"<h3 style='color:#0366d6; text-align:center;'>{w_str} ({d_str}) 주보</h3>", unsafe_allow_html=True)
    memo = str(row_data.get('비고', '')).strip()
    if memo: st.info(f"📝 비고: {memo}")
        
    img1, img2 = str(row_data.get('주보이미지1', '')), str(row_data.get('주보이미지2', ''))
    t1, t2 = st.tabs(["앞면 (1쪽)", "뒷면 (2쪽)"])
    with t1:
        if img1 and "http" in img1:
            clean_url = img1.replace("&vid=1", "").replace("?vid=1", "")
            st.markdown(f"<img src='{clean_url}' style='width: 100%; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); display: block; margin: auto;'>", unsafe_allow_html=True)
        else: st.write("등록된 앞면 이미지가 없습니다.")
    with t2:
        if img2 and "http" in img2:
            clean_url = img2.replace("&vid=1", "").replace("?vid=1", "")
            st.markdown(f"<img src='{clean_url}' style='width: 100%; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); display: block; margin: auto;'>", unsafe_allow_html=True)
        else: st.write("등록된 뒷면 이미지가 없습니다.")

# --- 다이얼로그 모달: 주보 관리 ---
@st.dialog("📝 주보 등록/수정 관리")
def manage_bulletin_dialog(w_str, d_str):
    st.markdown(f"<h4 style='color:#0366d6; text-align:center;'>{w_str} ({d_str}) 주보 설정</h4>", unsafe_allow_html=True)
    existing_data = df_b[df_b['주차'] == w_str] if not df_b.empty else pd.DataFrame()
    with st.form(f"bulletin_form_{w_str}"):
        memo = st.text_input("📝 비고", value=existing_data.iloc[0].get('비고', '') if not existing_data.empty else "")
        img1 = st.file_uploader("📷 앞면 (또는 1페이지)", type=['png', 'jpg', 'jpeg'])
        img2 = st.file_uploader("📷 뒷면 (또는 2페이지) - 선택사항", type=['png', 'jpg', 'jpeg'])
        old_img1 = existing_data.iloc[0].get('주보이미지1', '') if not existing_data.empty else ""
        old_img2 = existing_data.iloc[0].get('주보이미지2', '') if not existing_data.empty else ""
        
        if st.form_submit_button("💾 주보 저장", type="primary", use_container_width=True):
            with st.spinner("저장 중..."):
                url1 = upload_photo(img1, f"주보_{w_str}_1") if img1 else old_img1
                url2 = upload_photo(img2, f"주보_{w_str}_2") if img2 else old_img2
                now_str = str(datetime.datetime.now())
                if not existing_data.empty:
                    row_idx = int(existing_data.iloc[0]['sheet_row'])
                    chunked_update(ws_b, [gspread.Cell(row_idx, 3, url1), gspread.Cell(row_idx, 4, url2), gspread.Cell(row_idx, 5, memo), gspread.Cell(row_idx, 6, now_str)])
                else: ws_b.append_row([w_str, d_str, url1, url2, memo, now_str])
                st.success("✅ 저장이 완료되었습니다!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()
    
    if not existing_data.empty:
        if st.button("🚨 이 주차 주보 완전 삭제", use_container_width=True):
            ws_b.delete_rows(int(existing_data.iloc[0]['sheet_row'])); st.success("🗑️ 삭제 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

# --- 다이얼로그 모달: 인원 정보 ---
@st.dialog("👤 인원 정보 상세", width="large")
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
            
        # 모바일 최적화를 위해 세로로 넓게 보이도록 컬럼 제거 후 직접 배치
        st.markdown(f"**이름:** {safe_str(target_dict.get('이름',''))}")
        st.markdown(f"**반(담임):** {safe_str(target_dict.get(class_col,''))}")
        st.markdown(f"**구분:** {safe_str(target_dict.get('학교상태', '일반'))}")
        
        if st.session_state.get('privacy_mode', True):
            st.markdown(f"**생년월일:** 🔒 [보호됨]")
            st.markdown(f"**연락처:** 🔒 [보호됨]")
            st.markdown(f"**부모(아빠/엄마):** 🔒 [보호됨]")
            st.markdown(f"**주소:** 🔒 [보호됨]")
        else:
            st.markdown(f"**생년월일:** {safe_str(target_dict.get('생년월일',''))}")
            st.markdown(f"**연락처:** {safe_str(target_dict.get('연락처',''))}")
            st.markdown(f"**부모(아빠/엄마):** {safe_str(target_dict.get('부모(아빠/엄마)',''))}")
            st.markdown(f"**주소:** {safe_str(target_dict.get('주소',''))}")
            
        st.markdown(f"**학교:** {safe_str(target_dict.get('학교',''))}")
        st.markdown(f"**비고:** {safe_str(target_dict.get('비고',''))}")
        st.caption(f"등록일: {safe_str(target_dict.get('등록일',''))} | 변동일: {safe_str(target_dict.get('변동일',''))}")
        st.divider()
        st.button("✏️ 정보 수정하기", use_container_width=True, on_click=set_edit_true)
            
    else:
        st.warning("⚠️ 현재 정보를 수정 중입니다.")
        with st.form("modal_edit_form"):
            # 모바일 1열 폼 적용
            e_name = st.text_input("이름", value=safe_str(target_dict.get('이름','')))
            e_class = st.text_input("학년(담임)", value=safe_str(target_dict.get(class_col,'')))
            bd_val = parse_date_safe(safe_str(target_dict.get('생년월일', '')))
            e_birth = st.date_input("생년월일", value=bd_val, min_value=datetime.date(1900,1,1)).strftime("%Y-%m-%d")
            e_reg = st.text_input("등록일 (YYYY-MM-DD)", value=safe_str(target_dict.get('등록일','')), placeholder="예: 2026-05-10")
            e_change = st.text_input("변동일 (이사/졸업/타교회 등)", value=safe_str(target_dict.get('변동일','')), placeholder="변동 발생 날짜")
            e_school = st.text_input("학교", value=safe_str(target_dict.get('학교','')))
            e_phone = st.text_input("연락처", value=safe_str(target_dict.get('연락처','')))
            curr_s = safe_str(target_dict.get('학교상태', '일반'))
            e_status = st.selectbox("구분 (상태)", ALL_STATUS_OPTS, index=ALL_STATUS_OPTS.index(curr_s) if curr_s in ALL_STATUS_OPTS else 0)
            e_parents = st.text_input("부모(아빠/엄마)", value=safe_str(target_dict.get('부모(아빠/엄마)','')))
            e_addr = st.text_input("주소", value=safe_str(target_dict.get('주소','')))
            e_memo = st.text_input("비고", value=safe_str(target_dict.get('비고','')))
            e_photo = st.file_uploader("사진변경", type=['png', 'jpg', 'jpeg'])
            
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

# --- 5. 화면(탭) 구성 (교적부 관리가 10번 인덱스 맨 뒤로 이동됨) ---
tabs = st.tabs(["🏫 반별명단", "🎂 생일", "🙏 기도순서", "📝 주보", "🌱 새친구", "⚙️ 행사", "✅ 출석", "📊 통계", "🧾 비용집행", "💰 교사회비", "📋 교적부 관리"])

# ==========================================
# [탭 0] 반별명단 (단일 반 조회 - 메모리/모바일 최적화)
# ==========================================
with tabs[0]:
    st.markdown('<a href="#top-anchor" class="fab-button">⬆ 맨 위로</a>', unsafe_allow_html=True)
    st.subheader("🏫 반별 명단 조회")
    st.info("💡 **아이콘:** 👤 일반 &nbsp; 🌱 새친구 &nbsp; 🧑‍🏫 교사 &nbsp; ✝️ 교역자 &nbsp; 🚫 비활성")
    
    all_classes = sorted([c for c in df[class_col].unique() if str(c).strip()], key=class_sort_key)
    # 한 반씩만 렌더링하도록 selectbox 도입
    selected_class = st.selectbox("👇 조회할 반을 선택하세요", ["반을 선택하세요"] + all_classes)
    
    if selected_class != "반을 선택하세요":
        group = df[df[class_col] == selected_class].copy()
        group['role'] = group.apply(get_role, axis=1)
        
        def get_sort_key(row):
            s = row[status_col]
            if s in INACTIVE_STATUS: return 100
            if row['role'] in ['teacher', 'pastor']: return get_teacher_rank(row['이름'], row.get('비고', ''))
            if s == '새친구': return 60
            return 80
            
        group['sort_key'] = group.apply(get_sort_key, axis=1)
        group = group.sort_values(by=['sort_key', '이름'])
        
        active_count = len(group[~group[status_col].isin(INACTIVE_STATUS)])
        st.markdown(f"<div class='class-header'>🏷️ {selected_class} ({active_count}명)</div>", unsafe_allow_html=True)
        
        for _, r in group.iterrows():
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
            
            with st.container():
                c_img, c_btn = st.columns([1, 4])
                clean_p_url = str(r.get('사진', '')).replace("&vid=1", "").replace("?vid=1", "")
                with c_img:
                    if clean_p_url and str(clean_p_url).startswith('http'):
                        st.markdown(f'<img src="{clean_p_url}" style="width:50px; height:50px; border-radius:50%; object-fit:cover; margin-top:5px; border: 2px solid #ddd;">', unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='font-size:2.2rem; text-align:center;'>👤</div>", unsafe_allow_html=True)
                with c_btn:
                    if st.button(label, key=f"btn_link_{r['sheet_row']}", help="상세정보 확인", use_container_width=True): 
                        edit_student_dialog(r.to_dict())
        
        with st.expander(f"➕ 새친구 추가"):
            with st.form("quick_add"):
                new_n = st.text_input("이름", placeholder="이름 입력")
                if st.form_submit_button("등록", type="primary") and new_n:
                    new_row = [""] * len(headers)
                    h_map = {str(h): idx for idx, h in enumerate(headers)}
                    if '이름' in h_map: new_row[h_map['이름']] = new_n
                    if class_col in h_map: new_row[h_map[class_col]] = selected_class
                    if '학교상태' in h_map: new_row[h_map['학교상태']] = "새친구"
                    ws.append_row(new_row); st.success("✅ 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 1] 생일표 (반 정보 간소화 & 모바일 아코디언)
# ==========================================
with tabs[1]:
    st.subheader("🎂 월별 생일 명단")
    b_map = {i: [] for i in range(1, 13)}
    bd_df = df[~df[status_col].isin(INACTIVE_STATUS)].copy()
    bd_df['role'] = bd_df.apply(get_role, axis=1)
    
    for _, r in bd_df.iterrows():
        b = str(r.get('생년월일', ''))
        if '-' in b and len(b.split('-')) == 3:
            try: 
                m, d = int(b.split('-')[1]), int(b.split('-')[2])
                c_raw = str(r.get(class_col, ''))
                # 괄호 제거 로직 추가 (예: "1학년(김교사)" -> "1학년")
                c_clean = c_raw.split('(')[0].strip() if '(' in c_raw else c_raw
                b_map[m].append({"name": r['이름'], "class": c_clean, "day": d, "role": r['role']})
            except: pass
            
    curr_month = datetime.date.today().month
    for m in range(1, 13):
        is_curr = (m == curr_month)
        if is_curr: st.markdown('<div id="current-month"></div>', unsafe_allow_html=True)
        
        with st.expander(f"📅 {m}월 생일자", expanded=is_curr):
            if b_map[m]:
                for p in sorted(b_map[m], key=lambda x: x["day"]):
                    if p['role'] == 'pastor': n_disp = f"<span style='color:#2E7D32;'>✝️ <b>{p['name']}</b></span>"
                    elif p['role'] == 'teacher': n_disp = f"<span style='color:#E91E63;'>🧑‍🏫 <b>{p['name']}</b></span>"
                    else: n_disp = f"<span>🎈 <b>{p['name']}</b></span>"
                    st.markdown(f"<div style='display:flex; justify-content:space-between; margin-bottom:10px; font-size:1.1rem;'>{n_disp} <span style='color:gray;'>({p['class']})</span><strong style='color:#e65100;'>{p['day']}일</strong></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='text-align:center; color:#ccc; font-size:1rem; padding: 10px 0;'>생일자가 없습니다</div>", unsafe_allow_html=True)
                        
    components.html("""
        <script>
        setTimeout(() => {
            const el = window.parent.document.getElementById('current-month');
            if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
        }, 500);
        </script>
    """, height=0, width=0)

# ==========================================
# [탭 2] 기도순서 (서브 탭 UI)
# ==========================================
with tabs[2]:
    st.subheader("🙏 예배 기도순서 관리")
    t_pray_view, t_pray_add, t_pray_edit, t_pray_del = st.tabs(["👀 일정 보기", "➕ 신규 등록", "📝 내역 수정", "🚨 내역 삭제"])
    
    with t_pray_view:
        if not df_p.empty:
            df_p_calc = df_p.copy()
            df_p_calc['날짜_dt'] = pd.to_datetime(df_p_calc['날짜'], errors='coerce')
            df_p_calc = df_p_calc.sort_values(by='날짜_dt', ascending=True)
            st.dataframe(df_p_calc[['날짜', '이름', '비고']], use_container_width=True, hide_index=True)
        else: st.info("일정이 없습니다.")
        
    with t_pray_add:
        with st.form("add_new_prayer_form"):
            new_p_date = st.date_input("기도 일자", datetime.date.today()).strftime("%Y-%m-%d")
            new_p_name = st.text_input("기도자 이름")
            new_p_memo = st.text_input("비고")
            if st.form_submit_button("💾 기도순서 저장", type="primary", use_container_width=True):
                ws_p.append_row([str(len(df_p) + 1), new_p_date, new_p_name, new_p_memo])
                st.success("저장 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
                
    with t_pray_edit:
        if not df_p.empty:
            p_options = ["선택"] + df_p.apply(lambda r: f"[{r.get('날짜','')}] {r.get('이름','')}", axis=1).tolist()
            sel_p_idx = st.selectbox("수정 대상", range(len(p_options)), format_func=lambda x: p_options[x])
            if sel_p_idx > 0:
                target_p = df_p.iloc[sel_p_idx - 1]
                with st.form("edit_prayer_form"):
                    e_p_date = st.date_input("일자", parse_date_safe(target_p.get('날짜',''))).strftime("%Y-%m-%d")
                    e_p_name = st.text_input("기도자", value=target_p.get('이름',''))
                    e_p_memo = st.text_input("비고", value=target_p.get('비고',''))
                    if st.form_submit_button("수정 반영", type="primary", use_container_width=True):
                        r_idx = int(target_p['sheet_row'])
                        chunked_update(ws_p, [gspread.Cell(r_idx, 2, e_p_date), gspread.Cell(r_idx, 3, e_p_name), gspread.Cell(r_idx, 4, e_p_memo)])
                        st.success("수정 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
                        
    with t_pray_del:
        if not df_p.empty:
            p_options = ["선택"] + df_p.apply(lambda r: f"[{r.get('날짜','')}] {r.get('이름','')}", axis=1).tolist()
            sel_p_idx = st.selectbox("삭제 대상", range(len(p_options)), format_func=lambda x: p_options[x])
            if st.button("🚨 삭제 실행", type="primary", use_container_width=True) and sel_p_idx > 0:
                ws_p.delete_rows(int(df_p.iloc[sel_p_idx - 1]['sheet_row']))
                st.success("삭제 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 3] 주보 (서브 탭 UI & 2열 배치)
# ==========================================
with tabs[3]:
    st.subheader("📝 주보 관리 및 조회")
    t_b_view, t_b_edit = st.tabs(["👀 주보 보기", "⚙️ 설정 및 업로드"])
    
    today_date = datetime.date.today()
    curr_week_idx = next((i for i in range(1, 53) if start_date + datetime.timedelta(days=(i-1)*7) <= today_date < start_date + datetime.timedelta(days=i*7)), 1)
    
    with t_b_view:
        b_cols = st.columns(2)
        for i in range(1, 53):
            w_str, w_date = f"{i}주", start_date + datetime.timedelta(days=(i-1)*7)
            match_b = df_b[df_b['주차'] == w_str] if not df_b.empty else pd.DataFrame()
            is_exist = not match_b.empty and (str(match_b.iloc[0].get('주보이미지1','')).startswith('http'))
            btn_label = f"✅ {w_str}" if is_exist else f"⬜ {w_str}"
            with b_cols[(i-1) % 2]:
                if i == curr_week_idx: st.markdown('<div id="current-week-anchor"></div>', unsafe_allow_html=True)
                if st.button(btn_label, key=f"v_bull_{i}", type="primary" if is_exist else "secondary", use_container_width=True):
                    if is_exist: view_bulletin_dialog(w_str, w_date.strftime("%m/%d"), match_b.iloc[0])
                    else: st.warning("아직 등록되지 않았습니다.")
                    
    with t_b_edit:
        b_cols = st.columns(2)
        for i in range(1, 53):
            w_str, w_date = f"{i}주", start_date + datetime.timedelta(days=(i-1)*7)
            with b_cols[(i-1) % 2]:
                if st.button(f"⚙️ {w_str} 설정", key=f"e_bull_{i}", use_container_width=True):
                    manage_bulletin_dialog(w_str, w_date.strftime("%Y-%m-%d"))
                    
    components.html("<script>setTimeout(()=>document.getElementById('current-week-anchor')?.scrollIntoView({behavior:'smooth', block:'center'}), 500);</script>", height=0)

# ==========================================
# [탭 4] 새친구
# ==========================================
with tabs[4]:
    st.subheader("🌱 최근 등록 새친구")
    news = df[df[status_col] == '새친구'].copy()
    if not news.empty: st.dataframe(news[['이름', class_col, '연락처', '비고']], use_container_width=True, hide_index=True)
    else: st.info("새친구가 없습니다.")

# ==========================================
# [탭 5] 행사 (서브 탭 UI & HTML PDF 보고서 다운로드)
# ==========================================
with tabs[5]:
    st.markdown('<a href="#top-anchor" class="fab-button">⬆ 맨 위로</a>', unsafe_allow_html=True)
    st.subheader("⚙️ 행사 기록 관리")
    
    t_ev_view, t_ev_add, t_ev_edit, t_ev_del = st.tabs(["📂 내용 보기/다운", "➕ 행사 등록", "📝 내용 수정", "🚨 삭제"])
    
    def format_event(row_id):
        if row_id == "선택": return "선택"
        m = df_act[df_act['sheet_row'] == row_id]
        return f"{m.iloc[0].get('날짜','')} | {m.iloc[0].get('활동명','')}" if not m.empty else "알 수 없음"

    with t_ev_view:
        if not df_act.empty:
            view_act_df = df_act.copy().sort_values(by=['날짜'], ascending=False)
            
            # --- 📄 행사 PDF(HTML) 보고서 다운로드 기능 ---
            html_act = """
            <html>
            <head>
                <meta charset="utf-8">
                <title>행사일정 보고서</title>
                <style>
                    body { font-family: 'Malgun Gothic', sans-serif; margin: 40px; color: #333; }
                    h1 { text-align: center; color: #0366d6; }
                    table { width: 100%; border-collapse: collapse; margin-bottom: 30px; }
                    th { background-color: #f1f8ff; padding: 10px; border: 1px solid #ddd; }
                    td { padding: 10px; border: 1px solid #ddd; text-align: center; }
                    .event-page { page-break-before: always; margin-top: 20px; }
                    .img-box { text-align: center; margin: 20px 0; display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; }
                    .img-box img { max-width: 300px; width: 45%; border-radius: 8px; border: 1px solid #ddd; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                </style>
            </head>
            <body>
                <h1>슈팅스타 유년부 행사 요약 보고서</h1>
                <h2>📊 행사 요약표</h2>
                <table>
                    <tr><th>날짜</th><th>행사명</th><th>내용 요약</th></tr>
            """
            for _, row in view_act_df.iterrows():
                summary = str(row.get('세부내용',''))[:30] + "..."
                html_act += f"<tr><td>{row.get('날짜','')}</td><td>{row.get('활동명','')}</td><td style='text-align:left;'>{summary}</td></tr>"
            html_act += "</table>"
            
            for _, row in view_act_df.iterrows():
                html_act += f"<div class='event-page'><h2>📅 {row.get('활동명','')} ({row.get('날짜','')})</h2>"
                html_act += f"<p><strong>상세 내용:</strong><br>{str(row.get('세부내용','')).replace(chr(10), '<br>')}</p>"
                if str(row.get('공지사항', '')).strip(): html_act += f"<p style='color:red;'><strong>공지:</strong> {row.get('공지사항','')}</p>"
                
                valid_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                if valid_urls:
                    html_act += "<h3>📸 첨부 사진</h3><div class='img-box'>"
                    for media_url in valid_urls:
                        clean_url = str(media_url).replace("&vid=1", "").replace("?vid=1", "")
                        if 'vid=1' not in str(media_url).lower():
                            html_act += f"<img src='{clean_url}'>"
                    html_act += "</div>"
                html_act += "</div>"
            html_act += "</body></html>"
            
            st.download_button(
                label="📄 행사일정 보고서 다운로드 (HTML ➔ 인쇄 PDF)",
                data=html_act.encode("utf-8"),
                file_name="유년부_행사보고서.html",
                mime="text/html",
                use_container_width=True,
                type="primary"
            )
            st.divider()

            for _, row in view_act_df.iterrows():
                with st.expander(f"📅 {row.get('날짜', '')} | {row.get('활동명', '')}"):
                    st.write(f"**내용:** {row.get('세부내용', '')}")
                    if str(row.get('공지사항', '')).strip(): st.markdown(f"**공지:** <span style='color:red;'>{row.get('공지사항', '')}</span>", unsafe_allow_html=True)
                    valid_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                    if valid_urls:
                        for media_url in valid_urls:
                            clean_url = str(media_url).replace("&vid=1", "").replace("?vid=1", "")
                            if 'vid=1' in clean_url.lower() or any(ext in clean_url.lower() for ext in ['.mp4', '.mov']):
                                st.video(clean_url)
                            else:
                                st.markdown(f"<img src='{clean_url}' style='width:100%; border-radius:8px; margin-bottom:10px;'>", unsafe_allow_html=True)
                            
    with t_ev_add:
        with st.form("new_e"):
            a_d = st.date_input("날짜"); a_t = st.text_input("행사명"); a_c = st.text_area("내용"); a_n = st.text_input("공지사항")
            a_f = st.file_uploader("사진 (최대15개)", accept_multiple_files=True, type=['png','jpg','jpeg','mp4','mov'])
            if st.form_submit_button("행사 저장", type="primary", use_container_width=True):
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
                        
                    ws_act.append_row(new_row); st.success("✅ 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

    with t_ev_edit:
        if not df_act.empty:
            opts = ["선택"] + df_act['sheet_row'].tolist()
            sel = st.selectbox("수정할 행사", opts, format_func=format_event)
            if sel != "선택":
                target = df_act[df_act['sheet_row'] == int(sel)].iloc[0]
                with st.form("edit_event_form"):
                    e_d = st.date_input("날짜", value=parse_date_safe(target.get('날짜', '')))
                    e_t = st.text_input("행사명", value=target.get('활동명', ''))
                    e_c = st.text_area("내용", value=target.get('세부내용', ''))
                    if st.form_submit_button("📝 텍스트 내용만 수정 저장", type="primary", use_container_width=True):
                        r_idx = int(sel)
                        chunked_update(ws_act, [gspread.Cell(r_idx, 1, str(e_d)), gspread.Cell(r_idx, 2, e_t), gspread.Cell(r_idx, 3, e_c)])
                        st.success("완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
                        
    with t_ev_del:
        if not df_act.empty:
            opts = ["선택"] + df_act['sheet_row'].tolist()
            sel = st.selectbox("삭제할 행사", opts, format_func=format_event)
            if st.button("🚨 삭제 실행", type="primary", use_container_width=True) and sel != "선택":
                ws_act.delete_rows(int(sel)); st.success("삭제 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 6] 출석
# ==========================================
with tabs[6]:
    st.subheader("📅 주간 출석 현황")
    extended_weeks_list = weeks_list + ["✏️ 직접 입력 (새 날짜)"]
    
    with st.container(border=True):
        sel_w_raw = st.selectbox("출석 주차 / 기준일", extended_weeks_list, index=max(0, min(51, datetime.date.today().isocalendar()[1] - 1)), format_func=lambda x: week_display_map.get(x, x))
        if sel_w_raw == "✏️ 직접 입력 (새 날짜)": 
            target_date = st.date_input("새로운 날짜 선택", datetime.date.today())
            sel_w = target_date.strftime("%Y-%m-%d")
        else: 
            sel_w = sel_w_raw
            w_num = int(sel_w_raw.replace("주", ""))
            target_date = start_date + datetime.timedelta(days=(w_num-1)*7)
            
        all_classes_list = sorted([str(c) for c in df[class_col].unique() if str(c).strip()], key=class_sort_key)
        sel_class = st.selectbox("반 필터 (모바일 속도 향상을 위해 반 선택 권장)", ["전체보기(느려질 수 있음)"] + all_classes_list)
    
    att_df = df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
    if sel_class != "전체보기(느려질 수 있음)": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
    att_df['role'] = att_df.apply(get_role, axis=1)
    
    with st.form("att_toggle_form"):
        new_att = {}
        grouped = att_df.sort_values(by=['이름']).groupby(class_col)
        for c_name in sorted(grouped.groups.keys(), key=class_sort_key):
            st.markdown(f"<div class='class-header'>🏷️ {c_name}</div>", unsafe_allow_html=True)
            cols = st.columns(2)  # 모바일 최적화를 위해 2열
            for i, (idx, row) in enumerate(grouped.get_group(c_name).iterrows()):
                is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                prefix = "🚫 " if row[status_col] in INACTIVE_STATUS else ("🌱 " if row[status_col]=='새친구' else "🧑‍🏫 " if row['role'] in ['teacher','pastor'] else "👤 ")
                new_att[row['sheet_row']] = cols[i%2].toggle(f"{prefix}{row['이름']}", value=is_on)
        
        st.divider()
        if st.form_submit_button("💾 데이터 저장", type="primary", use_container_width=True):
            with st.spinner("저장 중..."):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: 
                    try: ws.update_cell(1, target_c, sel_w)
                    except: ws.add_cols(10); ws.update_cell(1, target_c, sel_w)
                
                cells = [gspread.Cell(int(r), target_c, "1" if v else "") for r, v in new_att.items()]
                if cells: chunked_update(ws, cells)
                st.success(f"✅ 저장 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 7] 통계
# ==========================================
with tabs[7]:
    st.subheader("📊 통계")
    if not df_stat.empty:
        st.dataframe(df_stat, use_container_width=True, hide_index=True)

# ==========================================
# [탭 8] 비용집행관리 (서브 탭 UI & CSV 다운로드 번호 리셋)
# ==========================================
with tabs[8]:
    if not st.session_state['chongmu_auth']:
        st.warning("🔒 총무 권한이 필요한 메뉴입니다.")
        cpwd = st.text_input("비밀번호", type="password", key="pwd_receipt")
        if st.button("인증", type="primary", use_container_width=True):
            if cpwd == st.secrets.get("chongmu_password", "admin1234"): st.session_state['chongmu_auth'] = True; st.rerun()
            else: st.error("❌ 비밀번호 오류")
    else:
        st.subheader("🧾 비용집행관리")
        t_exp_view, t_exp_add, t_exp_edit, t_exp_del = st.tabs(["👀 내역 조회", "➕ 등록", "📝 수정", "🚨 삭제"])
        
        with t_exp_view:
            if not df_r.empty:
                df_r_calc = df_r.copy()
                df_r_calc['날짜_dt'] = pd.to_datetime(df_r_calc['날짜'], errors='coerce')
                
                min_date = df_r_calc['날짜_dt'].min().date() if pd.notnull(df_r_calc['날짜_dt'].min()) else datetime.date.today()
                date_range = st.date_input("조회 기간 선택", [min_date, datetime.date.today()])
                
                if len(date_range) == 2: s_date, e_date = date_range
                else: s_date, e_date = date_range[0], date_range[0]
                
                df_r_filtered = df_r_calc[(df_r_calc['날짜_dt'].dt.date >= s_date) & (df_r_calc['날짜_dt'].dt.date <= e_date)].copy()
                
                if not df_r_filtered.empty:
                    display_cols = ['번호', '날짜', '구매처', '내용', '비용', '비고']
                    display_df = df_r_filtered[display_cols].copy()
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # --- 엑셀 다운로드 시 필터링된 결과에도 순번을 1번부터 차례대로 리셋 ---
                    df_csv = display_df.copy()
                    df_csv['번호'] = range(1, len(df_csv) + 1)
                    
                    st.download_button(
                        label="📊 현재 조회 내역 엑셀(CSV) 다운로드",
                        data=df_csv.to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"비용집행내역_{s_date}_{e_date}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        type="primary"
                    )

        with t_exp_add:
            with st.form("new_receipt_form"):
                rc_date = st.date_input("날짜", datetime.date.today()).strftime("%Y-%m-%d")
                rc_vendor = st.text_input("구매처")
                rc_detail = st.text_input("내용")
                rc_cost = st.number_input("비용 (원)", min_value=0, step=1000)
                rc_memo = st.text_input("비고")
                rc_photo = st.file_uploader("영수증 사진", type=['png', 'jpg', 'jpeg'])
                if st.form_submit_button("등록 완료", type="primary", use_container_width=True):
                    with st.spinner("업로드 중..."):
                        p_url = upload_photo(rc_photo, f"영수증_{rc_vendor}") if rc_photo else ""
                        ws_r.append_row([len(df_r) + 1, rc_date, rc_vendor, rc_detail, rc_cost, rc_memo, p_url])
                        st.success("등록됨!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

        with t_exp_edit:
            if not df_r.empty:
                opts = ["선택"] + df_r.apply(lambda r: f"No.{r.get('번호','')} | {r.get('구매처','')}", axis=1).tolist()
                sel = st.selectbox("수정 대상", range(len(opts)), format_func=lambda x: opts[x])
                if sel > 0:
                    t = df_r.iloc[sel - 1]
                    with st.form("edit_receipt_form"):
                        e_cost = st.number_input("비용", value=parse_int_safe(t.get('비용', 0)), step=1000)
                        if st.form_submit_button("수정 저장", type="primary", use_container_width=True):
                            chunked_update(ws_r, [gspread.Cell(int(t['sheet_row']), 5, str(e_cost))])
                            st.success("수정 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
                            
        with t_exp_del:
            if not df_r.empty:
                opts = ["선택"] + df_r.apply(lambda r: f"No.{r.get('번호','')} | {r.get('구매처','')}", axis=1).tolist()
                sel = st.selectbox("삭제 대상", range(len(opts)), format_func=lambda x: opts[x])
                if st.button("🚨 삭제 실행", type="primary", use_container_width=True) and sel > 0:
                    ws_r.delete_rows(int(df_r.iloc[sel-1]['sheet_row'])); st.success("삭제됨!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 9] 교사회비 (서브 탭 UI)
# ==========================================
with tabs[9]:
    if st.session_state['chongmu_auth']:
        st.subheader("💰 교사 회비 관리")
        t_due_view, t_due_in, t_due_out = st.tabs(["👀 장부 조회", "📥 수입 등록", "📤 지출 등록"])
        
        with t_due_view:
            c1, c2 = st.columns(2)
            if not df_in.empty: c1.markdown("##### 📥 수입 내역"); c1.dataframe(df_in[['날짜', '입금자명', '입금액']], hide_index=True)
            if not df_out.empty: c2.markdown("##### 📤 지출 내역"); c2.dataframe(df_out[['날짜', '내용', '지출액']], hide_index=True)
            
        with t_due_in:
            with st.form("new_in_form"):
                d = st.date_input("날짜").strftime("%Y-%m-%d"); n = st.text_input("입금자명"); a = st.number_input("금액", step=1000)
                if st.form_submit_button("수입 등록", type="primary", use_container_width=True):
                    ws_in.append_row([len(df_in)+1, d, n, a, ""]); st.success("저장 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()
                    
        with t_due_out:
            with st.form("new_out_form"):
                d = st.date_input("지출 날짜").strftime("%Y-%m-%d"); c = st.text_input("내용"); a = st.number_input("금액", step=1000)
                if st.form_submit_button("지출 등록", type="primary", use_container_width=True):
                    ws_out.append_row([len(df_out)+1, d, c, a, "", ""]); st.success("저장 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 10] 교적부 통합 관리 (마지막 탭으로 이동 완료)
# ==========================================
with tabs[10]:
    st.subheader("📋 교적부 통합 관리")
    
    t_mem_view, t_mem_add, t_mem_edit = st.tabs(["👀 전체명단 보기", "➕ 신규 인원 등록", "📝 정보 수정/비활성"])
    
    with t_mem_view:
        df_display = df.copy()
        if st.session_state['privacy_mode']:
            for c_priv in ['생년월일', '부모(아빠/엄마)', '연락처', '주소']:
                if c_priv in df_display.columns:
                    df_display[c_priv] = "🔒 [보호됨]"
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
    with t_mem_add:
        with st.form("add_new"):
            n_name = st.text_input("이름 (필수)")
            n_class = st.text_input("학년(담임) (필수)")
            n_status = st.selectbox("구분", ALL_STATUS_OPTS, index=0)
            n_reg = st.date_input("등록일자", value=datetime.date.today()).strftime("%Y-%m-%d")
            n_photo = st.file_uploader("사진 첨부", type=['png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("✨ 등록하기", type="primary", use_container_width=True):
                if n_name and n_class:
                    with st.spinner("등록 중..."):
                        p_url = upload_photo(n_photo, n_name)
                        new_row = [""] * len(headers)
                        h_map = {str(h): i for i, h in enumerate(headers)}
                        if '이름' in h_map: new_row[h_map['이름']] = n_name
                        if class_col in h_map: new_row[h_map[class_col]] = n_class
                        if '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                        if '등록일' in h_map: new_row[h_map['등록일']] = n_reg
                        if '사진' in h_map: new_row[h_map['사진']] = p_url
                        ws.append_row(new_row); st.success("✅ 등록 완료!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
                else:
                    st.warning("이름과 반 정보는 필수입니다.")

    with t_mem_edit:
        search_list = ["학생 선택"] + df.apply(lambda r: f"{r['이름']} | {r.get(class_col,'')} ({r.get('학교상태','일반')})", axis=1).tolist()
        sel_idx = st.selectbox("수정할 인원 선택", range(len(search_list)), format_func=lambda x: search_list[x])
        if sel_idx > 0:
            target = df.iloc[sel_idx - 1]
            edit_student_dialog(target.to_dict())
