import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime
import uuid
import re
import time
import io
import gc

# ==========================================
# 1. 전역 설정 및 글로벌 상태 초기화
# ==========================================
st.set_page_config(page_title="26년 슈팅스타 통합관리 V1.0", page_icon="🌱", layout="wide")

# 우측 하단 고정형 "맨 위로" 버튼
st.markdown('<div id="top-anchor"></div><a href="#top-anchor" class="fab-button">⬆ 맨 위로</a>', unsafe_allow_html=True)

# 모바일 화면 확대/축소 허용 및 최적화
st.html(
    """
    <script>
    const parentDoc = window.parent.document;
    let metaViewport = parentDoc.querySelector('meta[name="viewport"]');
    if (!metaViewport) {
        metaViewport = parentDoc.createElement('meta');
        metaViewport.name = 'viewport';
        parentDoc.head.appendChild(metaViewport);
    }
    metaViewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes';
    window.history.pushState(null, "", window.location.href);
    window.onpopstate = function() { window.history.pushState(null, "", window.location.href); };
    </script>
    """
)

INACTIVE_STATUS = ['이사', '비활성', '졸업', '타교회']
ALL_STATUS_OPTS = ["일반", "새친구", "교사", "교역자", "전도사", "목사", "이사", "졸업", "타교회", "비활성"]

if "base_font_size" not in st.session_state: st.session_state["base_font_size"] = 16
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if 'privacy_mode' not in st.session_state: st.session_state['privacy_mode'] = True
if 'chongmu_auth' not in st.session_state: st.session_state['chongmu_auth'] = False
if "current_menu" not in st.session_state: st.session_state["current_menu"] = "🏫 반"

# 글로벌 CSS (모바일 최적화 및 카드 뷰)
st.markdown(f"""
    <style>
    html {{ font-size: {st.session_state["base_font_size"]}px !important; scroll-behavior: smooth; }}
    button, input, select, textarea, div[data-testid="stToggle"] {{ touch-action: manipulation !important; font-size: 16px !important; }}
    input[type="text"], input[type="password"], input[type="number"], textarea, div[data-baseweb="select"] {{ min-height: 50px !important; border-radius: 8px !important; }}
    div[data-testid="stButton"] button {{ min-height: 50px !important; font-size: 1.1rem !important; font-weight: 700 !important; border-radius: 8px !important; }}
    
    .class-header {{ background-color: #f1f8ff; padding: 15px; border-radius: 8px; color: #0366d6; font-weight: 800; font-size: 1.3rem; margin-top: 25px; margin-bottom: 15px; border-left: 6px solid #0366d6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
    .fab-button {{ position: fixed; bottom: 25px; right: 25px; left: auto; background-color: rgba(3, 102, 214, 0.9); color: white !important; padding: 15px 20px; border-radius: 30px; text-decoration: none; font-weight: 800; font-size: 1.1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999999; backdrop-filter: blur(5px); }}
    
    .keep-row, .attendance-card-container {{ display: none; }}
    
    @media (max-width: 768px) {{
        div[data-testid="stHorizontalBlock"] {{ display: flex !important; flex-wrap: wrap !important; gap: 2% !important; }}
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{ min-width: 48% !important; flex: 1 1 48% !important; margin-bottom: 8px !important; }}
        div[role="dialog"] > div {{ padding: 1rem !important; max-width:100% !important; }} 
        div[data-testid="stMetricValue"] {{ font-size: 1.8rem !important; }} 
    }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 로그인 제어
# ==========================================
if not st.session_state["authenticated"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center; color: #0366d6;'>🌱 슈팅스타 관리 로그인</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>시스템 접근을 위해 관리자 비밀번호를 입력해주세요.</p>", unsafe_allow_html=True)
            pwd = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력", label_visibility="collapsed")
            if st.button("🚀 로그인", use_container_width=True, type="primary"):
                if "admin_password" in st.secrets and pwd == st.secrets["admin_password"]:
                    st.session_state["authenticated"] = True; st.rerun()
                else: st.error("❌ 비밀번호가 일치하지 않습니다.")
    st.stop()

if "GOOGLE_PROXY_URL" in st.secrets: GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else: st.error("Secrets 누락!"); st.stop()

start_date = datetime.date(2026, 1, 4)

# ==========================================
# 3. 공통 유틸리티 함수
# ==========================================
def change_menu(menu_name): st.session_state["current_menu"] = menu_name

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
        st.toast(f"⏳ '{file.name}' 전송 중...", icon="☁️")
        orig_ext = "." + file.name.split('.')[-1].strip().lower() if '.' in file.name else ".jpg"
        clean_name = re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣_-]', '', str(name).strip()) or "첨부파일"
        unique_id = str(uuid.uuid4())[:4]
        final_filename = f"{clean_name}_{int(time.time())}_{unique_id}{orig_ext}"
        safe_mime_type = file.type if file.type else "application/octet-stream"
        file_data = file.getvalue()

        if any(ext in orig_ext for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            try:
                from PIL import Image, ImageOps
                img = Image.open(io.BytesIO(file_data))
                try: img = ImageOps.exif_transpose(img)
                except: pass
                if img.mode != 'RGB': img = img.convert('RGB')
                img.thumbnail((1024, 1024))
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                file_data = buf.getvalue(); safe_mime_type = "image/jpeg"
                final_filename = final_filename.rsplit('.', 1)[0] + ".jpg"
                img.close(); del img, buf
            except: pass
        
        b64 = base64.b64encode(file_data).decode('utf-8')
        del file_data 
        headers_req = {"Content-Type": "application/json"}
        if "PROXY_AUTH_KEY" in st.secrets: headers_req["Authorization"] = f"Bearer {st.secrets['PROXY_AUTH_KEY']}"
        payload = {"fileName": final_filename, "mimeType": safe_mime_type, "base64Data": b64}
        
        res_url = ""
        for attempt in range(2):
            try:
                res = requests.post(GOOGLE_PROXY_URL, json=payload, headers=headers_req, timeout=60)
                if res.status_code == 200:
                    url = res.json().get("fileUrl", "")
                    if safe_mime_type.startswith('video/') and "vid=1" not in url: url += "&vid=1" if "?" in url else "?vid=1"
                    st.toast("✅ 첨부 완료!", icon="🎉"); res_url = url; break
            except: time.sleep(1)
        del payload, b64; gc.collect()
        return res_url
    except Exception as e: 
        st.error(f"❌ 전송 오류: {str(e)}"); return ""

def chunked_update(worksheet, cells, chunk_size=200):
    if not cells: return
    for i in range(0, len(cells), chunk_size):
        worksheet.update_cells(cells[i:i + chunk_size]); time.sleep(0.5)

def parse_date_safe(date_str):
    if not date_str or str(date_str).strip() == '': return datetime.date.today()
    try:
        clean_str = str(date_str).replace(" ", "").strip().rstrip('.').replace('.', '-').replace('/', '-')
        if len(clean_str) == 8 and clean_str.count('-') == 2:
            parts = clean_str.split('-')
            if len(parts[0]) == 2: clean_str = f"20{parts[0]}-{parts[1]}-{parts[2]}"
        if len(clean_str) == 8 and clean_str.count('-') == 0: return datetime.datetime.strptime(clean_str, "%Y%m%d").date()
        return datetime.datetime.strptime(clean_str, "%Y-%m-%d").date()
    except: return datetime.date.today()

def natural_sort_key(s): return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', str(s).replace(" ", ""))]
def class_sort_key(c):
    c_str = str(c).replace(" ", ""); priority = 1
    if any(k in c_str for k in ['교역자', '전도사', '목사']): priority = 3
    elif any(k in c_str for k in ['선생님', '교사']): priority = 2
    return (priority, natural_sort_key(c_str))

def get_teacher_rank(name, memo):
    text = str(name) + " " + str(memo); match = re.search(r'\[(\d+)\]', text)
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
        if parse_date_safe(reg_str) > target_date: return False
    s = safe_str(row.get('학교상태', '일반'))
    if s in INACTIVE_STATUS:
        change_str = safe_str(row.get('변동일', ''))
        if change_str:
            if parse_date_safe(change_str) <= target_date: return False
        else: return False
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
    s, c, m = safe_str(row.get('학교상태', '')), safe_str(row.get('학년(담임)', row.get('반', ''))), safe_str(row.get('비고', ''))
    if s in ['교사', '교역자', '전도사', '목사']: return True
    if s in INACTIVE_STATUS and (any(k in c for k in ['교사', '교역자', '전도사', '목사', '임원', '선생님']) or any(k in m for k in ['교사', '교역자', '전도사', '목사', '부장', '부감', '총무', '선생님'])): return True
    return False

# ==========================================
# 4. 데이터 연동
# ==========================================
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource
def get_worksheets():
    client = init_connection()
    sh = client.open_by_key("1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q")
    def safe_get_or_create(title, rows, cols, headers=None):
        try: return sh.worksheet(title)
        except: 
            ws = sh.add_worksheet(title, rows, cols)
            if headers: ws.append_row(headers)
            return ws
    ws_m = sh.worksheet("교적부")
    ws_a = safe_get_or_create("활동간식", 500, 20, ["날짜", "활동명", "세부내용", "공지사항"] + [f"사진{i}" for i in range(1, 16)] + ["등록일"])
    ws_s = safe_get_or_create("주차별통계", 200, 15, ["주차", "행사명", "유년부 재적", "유년부 출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"])
    ws_r = safe_get_or_create("영수증", 500, 10, ["번호", "날짜", "구매처", "내용", "비용", "비고", "영수증사진"])
    ws_in = safe_get_or_create("회비입금", 500, 10, ["번호", "날짜", "입금자명", "입금액", "비고"])
    ws_out = safe_get_or_create("회비지출", 500, 10, ["번호", "날짜", "내용", "지출액", "비고", "영수증사진"])
    ws_p = safe_get_or_create("기도순서", 500, 5, ["번호", "날짜", "이름", "비고"])
    ws_b = safe_get_or_create("주보관리", 60, 10, ["주차", "날짜", "주보이미지1", "주보이미지2", "비고", "업데이트일시"])
    return ws_m, ws_a, ws_s, ws_r, ws_in, ws_out, ws_p, ws_b

@st.cache_data(ttl=600, max_entries=1)
def fetch_sheet_data():
    return [ws.get_all_values() for ws in get_worksheets()]

def get_all_data():
    try:
        worksheets = get_worksheets()
        values_list = fetch_sheet_data()
        dfs = []
        for vals in values_list:
            df_temp = pd.DataFrame(vals[1:], columns=vals[0]) if len(vals) > 1 else pd.DataFrame()
            if not df_temp.empty: df_temp['sheet_row'] = range(2, len(df_temp) + 2)
            dfs.append(df_temp)
        df_m, df_a, df_s, df_r, df_in, df_out, df_p, df_b = dfs
        
        if not df_m.empty and '이름' in df_m.columns:
            df_m = df_m[df_m['이름'].astype(str).str.strip() != '']
            df_m = df_m[~df_m['이름'].isin(['None', 'nan', ''])]
        if '상태' in df_m.columns and '학교상태' not in df_m.columns: df_m.rename(columns={'상태': '학교상태'}, inplace=True)
            
        return worksheets[0], df_m, values_list[0][0], worksheets[1], df_a, worksheets[2], df_s, worksheets[3], df_r, worksheets[4], df_in, worksheets[5], df_out, worksheets[6], df_p, worksheets[7], df_b
    except Exception as e: 
        st.error(f"데이터 로딩 오류: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat, ws_r, df_r, ws_in, df_in, ws_out, df_out, ws_p, df_p, ws_b, df_b = get_all_data()

if df is None or df.empty:
    st.warning("⚠️ 데이터 로딩 중입니다. 잠시만 기다려주세요.")
    st.stop()

class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')
status_col = '학교상태' if '학교상태' in df.columns else '상태'
req_cols = ['학생ID', '학년(담임)', '이름', '생년월일', '학교상태', '등록일', '변동일', '학교', '부모(아빠/엄마)', '연락처', '주소', '비고']
available_cols = [c for c in req_cols if c in df.columns]

if '이름' in df.columns:
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
    active_sum_calc = len(df) - total_inact

weeks_list = [f"{i}주" for i in range(1, 53)]
custom_dates_list = [str(h) for h in headers if re.match(r'^\d{4}-\d{2}-\d{2}$', str(h))]
week_display_map = {f"{i}주": format_week_display(f"{i}주") for i in range(1, 53)}
for cd in custom_dates_list: week_display_map[cd] = f"📅 {cd} (수기입력)"
extended_weeks_list = weeks_list + sorted(custom_dates_list, reverse=True) + ["✏️ 직접 입력 (새 날짜)"]

# ==========================================
# 5. 다이얼로그 (모달) 함수
# ==========================================
@st.dialog("📖 주보 보기", width="large")
def view_bulletin_dialog(w_str, d_str, row_data):
    st.markdown(f"<h3 style='color:#0366d6; text-align:center;'>{w_str} ({d_str}) 주보</h3>", unsafe_allow_html=True)
    memo = str(row_data.get('비고', '')).strip()
    if memo: st.info(f"📝 비고: {memo}")
    img1, img2 = str(row_data.get('주보이미지1', '')), str(row_data.get('주보이미지2', ''))
    t1, t2 = st.tabs(["앞면 (1쪽)", "뒷면 (2쪽)"])
    with t1:
        if img1 and "http" in img1: st.markdown(f"<img src='{img1.replace('&vid=1', '').replace('?vid=1', '')}' style='max-width: 100%; border-radius: 8px; display: block; margin: auto;'>", unsafe_allow_html=True)
        else: st.write("등록된 앞면 이미지가 없습니다.")
    with t2:
        if img2 and "http" in img2: st.markdown(f"<img src='{img2.replace('&vid=1', '').replace('?vid=1', '')}' style='max-width: 100%; border-radius: 8px; display: block; margin: auto;'>", unsafe_allow_html=True)
        else: st.write("등록된 뒷면 이미지가 없습니다.")

@st.dialog("📝 주보 등록/수정 관리")
def manage_bulletin_dialog(w_str, d_str):
    st.markdown(f"<h4 style='color:#0366d6; text-align:center;'>{w_str} ({d_str}) 주보 설정</h4>", unsafe_allow_html=True)
    existing_data = df_b[df_b['주차'] == w_str] if not df_b.empty else pd.DataFrame()
    with st.form(f"bulletin_form_{w_str}"):
        memo = st.text_input("📝 비고", value=existing_data.iloc[0].get('비고', '') if not existing_data.empty else "")
        img1 = st.file_uploader("📷 주보 앞면 (1페이지)", type=['png', 'jpg', 'jpeg', 'webp'])
        img2 = st.file_uploader("📷 주보 뒷면 (2페이지)", type=['png', 'jpg', 'jpeg', 'webp'])
        
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
                st.success("✅ 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()
    
    if not existing_data.empty:
        if st.button("🚨 데이터 완전 삭제", use_container_width=True):
            ws_b.delete_rows(int(existing_data.iloc[0]['sheet_row'])); st.success("🗑️ 삭제 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

@st.dialog("👤 인원 정보 상세 / 수정")
def edit_student_dialog(target_dict):
    tab_info, tab_edit = st.tabs(["📄 정보 보기", "✏️ 내역 수정"])
    with tab_info:
        col_i, col_f = st.columns([1, 2])
        clean_p_url = safe_str(target_dict.get('사진', '')).replace("&vid=1", "").replace("?vid=1", "")
        if clean_p_url and clean_p_url.startswith('http'): col_i.markdown(f'<img src="{clean_p_url}" style="width:100%; border-radius:8px;">', unsafe_allow_html=True)
        else: col_i.info("등록된 사진이 없습니다.")
            
        c1, c2 = col_f.columns(2)
        c1.markdown(f"**이름:** {safe_str(target_dict.get('이름',''))}")
        c2.markdown(f"**반(담임):** {safe_str(target_dict.get(class_col,''))}")
        c1.markdown(f"**생년월일:** {safe_str(target_dict.get('생년월일',''))}")
        c2.markdown(f"**구분:** {safe_str(target_dict.get('학교상태', '일반'))}")
        c1.markdown(f"**학교:** {safe_str(target_dict.get('학교',''))}")
        c2.markdown(f"**연락처:** {safe_str(target_dict.get('연락처',''))}")
        st.markdown(f"**부모:** {safe_str(target_dict.get('부모(아빠/엄마)',''))}")
        st.markdown(f"**주소:** {safe_str(target_dict.get('주소',''))}")
        st.markdown(f"**비고:** {safe_str(target_dict.get('비고',''))}")
        
        if st.button("✅ 이 인원 출석체크 가기", use_container_width=True): change_menu("✅ 출석"); st.rerun()
            
    with tab_edit:
        with st.form("modal_edit_form"):
            e_name = st.text_input("이름", value=safe_str(target_dict.get('이름','')))
            e_class = st.text_input("학년(담임)", value=safe_str(target_dict.get(class_col,'')))
            curr_s = safe_str(target_dict.get('학교상태', '일반'))
            e_status = st.selectbox("구분", ALL_STATUS_OPTS, index=ALL_STATUS_OPTS.index(curr_s) if curr_s in ALL_STATUS_OPTS else 0)
            
            bd_val = parse_date_safe(safe_str(target_dict.get('생년월일', ''))) 
            e_birth = st.date_input("생년월일", value=bd_val, min_value=datetime.date(1900,1,1)).strftime("%Y-%m-%d")
            
            e_reg = st.text_input("등록일 (YYYY-MM-DD)", value=safe_str(target_dict.get('등록일','')))
            e_change = st.text_input("변동일", value=safe_str(target_dict.get('변동일','')))
            e_phone = st.text_input("연락처", value=safe_str(target_dict.get('연락처','')))
            e_parents = st.text_input("부모", value=safe_str(target_dict.get('부모(아빠/엄마)','')))
            e_addr = st.text_input("주소", value=safe_str(target_dict.get('주소','')))
            e_memo = st.text_input("비고", value=safe_str(target_dict.get('비고','')))
            e_photo = st.file_uploader("사진변경", type=['png', 'jpg', 'jpeg', 'webp'])
            
            if st.form_submit_button("💾 정보 저장", type="primary", use_container_width=True):
                with st.spinner("저장 중..."):
                    p_url = upload_photo(e_photo, e_name) if e_photo else safe_str(target_dict.get('사진',''))
                    r_idx = int(target_dict['sheet_row'])
                    update_map = {'이름': e_name, '학년(담임)': e_class, '반': e_class, '생년월일': e_birth, '주소': e_addr, '부모(아빠/엄마)': e_parents, '연락처': e_phone, '비고': e_memo, '사진': p_url, '등록일': e_reg, '변동일': e_change}
                    actual_headers = ws.row_values(1)
                    cells_to_update = [gspread.Cell(r_idx, actual_headers.index(k)+1, str(v)) for k, v in update_map.items() if k in actual_headers]
                    if '학교상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('학교상태')+1, e_status))
                    if cells_to_update: chunked_update(ws, cells_to_update)
                    st.success("✅ 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

# ==========================================
# 6. 사이드바 (메뉴 연동)
# ==========================================
menu_options = ["🏫 반", "✅ 출석", "📋 교적부 관리", "🌱 새친구", "🎂 생일", "🙏 기도순서", "📝 주보", "⚙️ 행사", "📊 통계", "🧾 비용집행관리", "💰 교사 회비 사용내역"]

with st.sidebar:
    st.markdown("### 🌱 유년부 통합 시스템")
    col_s1, col_s2, col_s3 = st.columns([2,1,1])
    if col_s1.button("🔄 동기화", help="최신 정보 로드"): st.cache_data.clear(); st.rerun()
    if col_s2.button("-", help="작게"): st.session_state["base_font_size"] = max(10, st.session_state["base_font_size"] - 1); st.rerun()
    if col_s3.button("+", help="크게"): st.session_state["base_font_size"] = min(24, st.session_state["base_font_size"] + 1); st.rerun()
    st.divider()
    st.radio("📌 메뉴 선택", menu_options, key="current_menu")

selected_menu = st.session_state["current_menu"]

# ==========================================
# 7. 메인 렌더링 (모든 탭 기능 100% 복구 적용)
# ==========================================
if selected_menu == "🏫 반":
    st.markdown(f"""
    <div style="font-size: 1.05rem; color: #444; background-color: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 25px; display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;">
        <strong style="color:#0366d6;">📊 유년부 현황</strong>
        <span>재적: <b>{st_count + new_count}</b>명</span> |
        <span>사역자: <b>{tc_count + ps_count}</b>명</span> |
        <span>비활성: <b>{total_inact}</b>명</span> |
        <strong style="color:#d32f2f;">총합계: {active_sum_calc}명</strong>
    </div>
    """, unsafe_allow_html=True)
    col_hdr1, col_hdr2 = st.columns([3, 1])
    col_hdr1.subheader("🏫 반별 명단")
    if col_hdr2.button("✅ 출석체크 가기", type="primary", use_container_width=True): change_menu("✅ 출석"); st.rerun()
        
    st.info("💡 아이콘 안내 | 👤 일반 | 🌱 새친구 | 🧑‍🏫 교사 | ✝️ 교역자 | 🚫 비활성")
    search_query = st.text_input("🔍 특정 이름 빠르게 찾기", placeholder="예: 김슈팅")
    
    all_classes = sorted([c for c in df[class_col].unique() if str(c).strip()], key=class_sort_key)
    for c_name in all_classes:
        group = df[df[class_col] == c_name].copy()
        if search_query: group = group[group['이름'].str.contains(search_query, na=False)]
        if group.empty: continue
            
        def get_sort_key(row):
            if row[status_col] in INACTIVE_STATUS: return 100
            if row['role'] in ['teacher', 'pastor']: return get_teacher_rank(row['이름'], row.get('비고', ''))
            if row[status_col] == '새친구': return 60
            return 80
        group['sort_key'] = group.apply(get_sort_key, axis=1); group = group.sort_values(by=['sort_key', '이름'])
        
        with st.container(border=True):
            st.markdown(f"<h4 style='color:#0366d6; border-bottom:1px solid #eee;'>{c_name} ({len(group[~group[status_col].isin(INACTIVE_STATUS)])}명)</h4>", unsafe_allow_html=True)
            stu_cols = st.columns(3) 
            for idx_j, (_, r) in enumerate(group.iterrows()):
                s, n = r[status_col], r['이름']
                icon = "🚫" if s in INACTIVE_STATUS else ("✝️" if r['role'] == 'pastor' else "🧑‍🏫" if r['role'] == 'teacher' else "🌱" if s == '새친구' else "👤")
                p_url = str(r.get('사진', '')).replace("&vid=1", "").replace("?vid=1", "")
                with stu_cols[idx_j % 3]:
                    with st.container(border=True):
                        c_img, c_info = st.columns([1.5, 4.5])
                        with c_img:
                            if p_url and p_url.startswith('http'): st.markdown(f'<img src="{p_url}" style="width:50px; height:50px; border-radius:50%; object-fit:cover;">', unsafe_allow_html=True)
                            else: st.markdown(f'<div style="width:50px; height:50px; border-radius:50%; background-color:#f1f8ff; display:flex; align-items:center; justify-content:center; font-size:24px;">{icon}</div>', unsafe_allow_html=True)
                        with c_info:
                            st.markdown(f"**{n}** <span style='font-size:0.8rem; color:gray;'>{s if s in INACTIVE_STATUS else ''}</span>", unsafe_allow_html=True)
                            if st.button("상세", key=f"btn_link_{r['sheet_row']}", help="수정"): edit_student_dialog(r.to_dict())

elif selected_menu == "✅ 출석":
    st.subheader("📅 주간 출석 체크")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1: 
            sel_w_raw = st.selectbox("출석 주차 / 기준일", extended_weeks_list, index=max(0, min(51, datetime.date.today().isocalendar()[1] - 1)), format_func=lambda x: week_display_map.get(x, x))
            if sel_w_raw == "✏️ 직접 입력 (새 날짜)": 
                target_date = st.date_input("새로운 날짜 선택", datetime.date.today())
                sel_w = target_date.strftime("%Y-%m-%d")
            else: 
                sel_w = sel_w_raw
                target_date = get_date_from_week_str(sel_w)
        with c2: 
            sel_class = st.selectbox("반 필터", ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()], key=class_sort_key))
            show_inactive = st.checkbox("👀 강제 전체명단 표시 (이사/졸업 포함)")

    att_df = df.copy() if show_inactive else df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
        
    att_df['role'] = att_df.apply(get_role, axis=1)
    ui_s_df = att_df[att_df['role'] == 'student']
    ui_t_df = att_df[att_df['role'] == 'teacher']
    s_p = len(ui_s_df[ui_s_df[sel_w].astype(str).str.strip() == "1"])
    t_p = len(ui_t_df[ui_t_df[sel_w].astype(str).str.strip() == "1"])
    
    saved_guest, saved_note, saved_event = 0, "", ""
    if not df_stat.empty and '주차' in df_stat.columns:
        match = df_stat[df_stat['주차'] == sel_w]
        if not match.empty: 
            try: saved_guest = int(float(match.iloc[0].get('추가', match.iloc[0].get('새친구/추가예배', 0))))
            except: saved_guest = 0
            saved_event = str(match.iloc[0].get('행사명', ''))
            saved_note = str(match.iloc[0].get('비고', match.iloc[0].get('내용(비고)', match.iloc[0].get('추가입력(비고)', ''))))

    st.markdown("#### 📊 실시간 체크 현황")
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric(f"유년부 (재적 {len(ui_s_df)})", f"{s_p}명")
    cs2.metric(f"교사 (재적 {len(ui_t_df)})", f"{t_p}명") 
    cs3.metric("유년부 합계", f"{s_p + saved_guest}명")
    cs4.metric("총합계", f"{s_p + saved_guest + t_p}명")

    with st.expander("🛠️ 추가 설정 (행사명 / 새친구 / 예외결석 입력)", expanded=bool(saved_event or saved_note or saved_guest)):
        c_e1, c_e2, c_e3 = st.columns([1, 2, 2])
        guest_in = c_e1.number_input("🎉 새친구/추가", min_value=0, value=saved_guest)
        event_text = c_e2.text_input("📢 행사명", value=saved_event, placeholder="예: 여름성경학교")
        custom_note = c_e3.text_input("📝 비고", value=saved_note)
        is_skip = st.toggle("⚠️ 출석체크 쉼 (전체 결석 처리)")

    with st.form("att_toggle_form"):
        new_att = {}
        if not is_skip:
            grouped = att_df.sort_values(by=['이름']).groupby(class_col)
            for c_name in sorted(grouped.groups.keys(), key=class_sort_key):
                st.markdown(f"<div class='class-header'>🏷️ {c_name}</div>", unsafe_allow_html=True)
                cols = st.columns(3)
                for i, (idx, row) in enumerate(grouped.get_group(c_name).iterrows()):
                    with cols[i % 3]:
                        is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                        new_att[str(row['sheet_row'])] = st.toggle(f"{row['이름']} {'🌱' if row[status_col]=='새친구' else ''}", value=is_on, key=f"tgl_{row['sheet_row']}_{sel_w}")
        
        if st.form_submit_button("💾 데이터 저장 (교적부/통계 반영)", type="primary", use_container_width=True):
            with st.spinner("저장 중..."):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: 
                    try: ws.update_cell(1, target_c, sel_w)
                    except: ws.add_cols(10); ws.update_cell(1, target_c, sel_w)
                
                final_s_p, final_t_p = 0, 0; cells_to_update = []
                if not is_skip:
                    for r, v in new_att.items():
                        row_data = att_df[att_df['sheet_row'] == int(r)]
                        if not row_data.empty and v:
                            if row_data.iloc[0]['role'] == 'student': final_s_p += 1
                            elif row_data.iloc[0]['role'] == 'teacher': final_t_p += 1 
                    for r, v in new_att.items(): cells_to_update.append(gspread.Cell(int(r), target_c, "1" if v else ""))
                    if cells_to_update: chunked_update(ws, cells_to_update)
                
                save_s_p, save_t_p = (0, 0) if is_skip else (final_s_p, final_t_p)
                valid_df = df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
                valid_df['role'] = valid_df.apply(get_role, axis=1)
                student_count = len(valid_df[valid_df['role'] == 'student'])
                teacher_count = len(valid_df[valid_df['role'] == 'teacher'])
                
                stat_headers = [str(h).strip() for h in ws_stat.row_values(1)]
                def norm(t): return re.sub(r'\s+', '', str(t))
                h_map = {norm(h): idx for idx, h in enumerate(stat_headers)}
                
                req_h = ["주차", "행사명", "유년부 재적", "유년부 출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"]
                missing = [h for h in req_h if norm(h) not in h_map]
                if missing:
                    start_col = len(stat_headers) + 1; h_cells = []
                    for i, mh in enumerate(missing): stat_headers.append(mh); h_map[norm(mh)] = len(stat_headers) - 1; h_cells.append(gspread.Cell(1, start_col + i, mh))
                    chunked_update(ws_stat, h_cells)
                
                new_row = [""] * len(stat_headers)
                val_map = {norm("주차"): sel_w, norm("행사명"): event_text, norm("유년부 재적"): student_count, norm("유년부 출석"): save_s_p, norm("추가"): guest_in, norm("유년부 합계"): save_s_p + guest_in, norm("교사재적"): teacher_count, norm("교사출석"): save_t_p, norm("총합"): save_s_p + guest_in + save_t_p, norm("비고"): custom_note, norm("업데이트일시"): str(datetime.datetime.now())}
                for k, v in val_map.items(): 
                    if k in h_map: new_row[h_map[k]] = v
                        
                match_stat = df_stat[df_stat['주차'] == sel_w] if not df_stat.empty else pd.DataFrame()
                if not match_stat.empty: 
                    row_idx = match_stat.index[0] + 2; end_col = chr(65 + len(stat_headers) - 1) if len(stat_headers) <= 26 else 'Z'
                    ws_stat.update(f"A{row_idx}:{end_col}{row_idx}", [new_row])
                else: ws_stat.append_row(new_row)
                st.success("✅ 저장 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

elif selected_menu == "📋 교적부 관리":
    st.subheader("📋 전체 교적부 데이터 관리")
    m_tabs = st.tabs(["👀 전체보기", "➕ 인원추가"])
    with m_tabs[0]:
        df_display = df[available_cols].copy()
        if st.session_state['privacy_mode']:
            for c_priv in ['생년월일', '부모(아빠/엄마)', '연락처', '주소']:
                if c_priv in df_display.columns: df_display[c_priv] = "🔒 [보호됨]"
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        if st.session_state['privacy_mode']:
            priv_pwd = st.text_input("열람 비밀번호", type="password")
            if st.button("🔓 블라인드 해제"):
                if priv_pwd == st.secrets.get("admin_password", ""): st.session_state['privacy_mode'] = False; st.rerun()
                else: st.error("불일치")
        else:
            if st.button("🔒 다시 숨기기"): st.session_state['privacy_mode'] = True; st.rerun()

    with m_tabs[1]:
        with st.form("add_new"):
            col1, col2 = st.columns(2)
            n_name = col1.text_input("이름 (필수)")
            n_class = col1.text_input("학년(담임) (필수)")
            n_status = col2.selectbox("구분", ALL_STATUS_OPTS, index=1)
            n_reg = col1.date_input("등록일자", value=datetime.date.today()).strftime("%Y-%m-%d")
            n_photo = st.file_uploader("사진 첨부 (5MB 이하 권장)", type=['png', 'jpg', 'jpeg'])
            if st.form_submit_button("✨ 등록하기", type="primary"):
                if not n_name or not n_class: st.error("이름과 반을 입력하세요")
                else:
                    p_url = upload_photo(n_photo, n_name)
                    new_row = [""] * len(headers)
                    h_map = {str(h): idx for idx, h in enumerate(headers)}
                    if '학생ID' in h_map: new_row[h_map['학생ID']] = f"S-{datetime.datetime.now().strftime('%y%m')}-{str(uuid.uuid4())[:4].upper()}"
                    if '이름' in h_map: new_row[h_map['이름']] = n_name
                    if class_col in h_map: new_row[h_map[class_col]] = n_class
                    if '등록일' in h_map: new_row[h_map['등록일']] = n_reg
                    if '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                    elif '상태' in h_map: new_row[h_map['상태']] = n_status
                    if '사진' in h_map: new_row[h_map['사진']] = p_url
                    ws.append_row(new_row); st.success("등록 완료"); time.sleep(1); st.cache_data.clear(); st.rerun()

elif selected_menu == "🌱 새친구":
    st.subheader("🌱 최근 등록 새친구")
    news = df[df[status_col] == '새친구'].copy()
    if not news.empty: 
        news_display = news[available_cols].copy()
        if st.session_state.get('privacy_mode', True):
            for c_priv in ['생년월일', '부모(아빠/엄마)', '연락처', '주소']:
                if c_priv in news_display.columns: news_display[c_priv] = news_display[c_priv].apply(lambda x: "🔒 [보호됨]" if str(x).strip() else "")
        st.dataframe(news_display, use_container_width=True, hide_index=True)
    else: st.info("등록된 새친구가 없습니다.")

elif selected_menu == "🎂 생일":
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
            
    curr_month = datetime.date.today().month
    for row_idx in range(4):
        cols = st.columns(3)
        for col_idx in range(3):
            m = row_idx * 3 + col_idx + 1
            with cols[col_idx]:
                if m == curr_month: st.markdown('<div id="current-month-anchor" style="position:relative; top:-80px;"></div>', unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown(f"<h4 style='color:#0366d6; margin-bottom:0px;'>📅 {m}월</h4>", unsafe_allow_html=True); st.divider()
                    month_data = b_map[m]
                    if month_data:
                        for p in sorted(month_data, key=lambda x: x["day"]):
                            if p['role'] == 'pastor': n_disp = f"<span style='color:#2E7D32;'>✝️ <b>{p['name']}</b></span>"
                            elif p['role'] == 'teacher': n_disp = f"<span style='color:#E91E63;'>🧑‍🏫 <b>{p['name']}</b></span>"
                            else: n_disp = f"<span>🎈 <b>{p['name']}</b></span>"
                            c_only = str(p['class']).split('(')[0].strip()
                            st.markdown(f"<div style='display:flex; justify-content:space-between; margin-bottom:5px;'>{n_disp} <span style='font-size:0.8rem; color:gray;'>({c_only})</span><strong style='color:#e65100;'>{p['day']}일</strong></div>", unsafe_allow_html=True)
                    else: st.markdown("<div style='text-align:center; color:#ccc; font-size:0.9rem; padding: 10px 0;'>생일자가 없습니다</div>", unsafe_allow_html=True)

    st.html("""<script>try { let scrollDoneMonth = false; setInterval(() => { const parentEl = window.parent.document; if (!parentEl) return; const el = parentEl.getElementById('current-month-anchor'); if (el && el.offsetParent !== null && !scrollDoneMonth) { el.scrollIntoView({behavior: 'smooth', block: 'center'}); scrollDoneMonth = true; } else if (el && el.offsetParent === null) { scrollDoneMonth = false; } }, 500); } catch(e) {}</script>""")

elif selected_menu == "🙏 기도순서":
    st.subheader("🙏 예배 기도순서 관리")
    if not df_p.empty:
        df_p_calc = df_p.copy(); df_p_calc['날짜_dt'] = pd.to_datetime(df_p_calc['날짜'], errors='coerce')
        df_p_calc = df_p_calc.sort_values(by='날짜_dt', ascending=True)
        class_mapping = {}
        if not df.empty and '이름' in df.columns:
            for _, row_m in df.iterrows(): class_mapping[str(row_m['이름']).replace(" ", "")] = str(row_m.get(class_col, ''))
        df_p_calc['반'] = df_p_calc['이름'].apply(lambda x: class_mapping.get(str(x).replace(" ", ""), "교역자/미등록"))
        df_p_calc['월그룹'] = df_p_calc['날짜_dt'].dt.strftime('%m월')
        
        st.markdown("##### 📅 월별 배치 현황")
        unique_months = df_p_calc['월그룹'].dropna().unique()
        p_grid = st.columns(len(unique_months) if len(unique_months) > 0 else 1)
        for idx_m, m_val in enumerate(unique_months):
            with p_grid[idx_m % len(p_grid)]:
                with st.container(border=True):
                    st.markdown(f"<h4 style='color:#0366d6; margin-top:0;'>✨ {m_val}</h4>", unsafe_allow_html=True); st.divider()
                    sub_m_df = df_p_calc[df_p_calc['월그룹'] == m_val]
                    for _, r_p in sub_m_df.iterrows():
                        d_text = f"{r_p['날짜_dt'].day}일" if pd.notnull(r_p['날짜_dt']) else str(r_p['날짜'])
                        st.markdown(f"**{d_text}** : {r_p['이름']} <span style='font-size:0.8rem; color:gray;'>({r_p['반']})</span>", unsafe_allow_html=True)
    else: st.info("등록된 기도순서 일정이 없습니다.")
        
    st.divider()
    p_tabs = st.tabs(["👀 보기", "➕ 등록", "📝 수정", "🚨 삭제"])
    with p_tabs[0]:
        if not df_p.empty: st.dataframe(df_p_calc[['날짜', '이름', '반', '비고']], use_container_width=True, hide_index=True)
    with p_tabs[1]:
        with st.form("add_new_prayer_form"):
            new_p_date = st.date_input("기도 일자", datetime.date.today()).strftime("%Y-%m-%d")
            registered_names = sorted(list(df['이름'].dropna().unique())) if '이름' in df.columns else []
            if registered_names: new_p_name = st.selectbox("기도자 선출", registered_names)
            else: new_p_name = st.text_input("기도자 이름")
            new_p_memo = st.text_input("비고")
            if st.form_submit_button("💾 저장", type="primary"):
                ws_p.append_row([str(len(df_p) + 1), new_p_date, new_p_name, new_p_memo]); st.success("기록 완료"); time.sleep(1); st.cache_data.clear(); st.rerun()
    with p_tabs[2]:
        if not df_p.empty:
            p_options = ["선택"] + df_p.apply(lambda r: f"[{r.get('날짜','')}] {r.get('이름','')}", axis=1).tolist()
            sel_p_idx = st.selectbox("수정 대상", range(len(p_options)), format_func=lambda x: p_options[x])
            if sel_p_idx > 0:
                target_p = df_p.iloc[sel_p_idx - 1]
                with st.form("edit_prayer_form"):
                    e_p_date = st.date_input("일자 수정", parse_date_safe(target_p.get('날짜',''))).strftime("%Y-%m-%d")
                    e_p_name = st.text_input("기도자 수정", value=str(target_p.get('이름','')).strip())
                    e_p_memo = st.text_input("비고", value=target_p.get('비고',''))
                    if st.form_submit_button("수정", type="primary"):
                        r_idx = int(target_p['sheet_row']); ws_p.update_cell(r_idx, 2, e_p_date); ws_p.update_cell(r_idx, 3, e_p_name); ws_p.update_cell(r_idx, 4, e_p_memo); st.success("수정 완료"); time.sleep(1); st.cache_data.clear(); st.rerun()
    with p_tabs[3]:
        if not df_p.empty:
            sel_p_idx = st.selectbox("삭제 대상", range(len(p_options)), format_func=lambda x: p_options[x], key="del_p")
            if st.button("🚨 삭제 실행") and sel_p_idx > 0:
                ws_p.delete_rows(int(df_p.iloc[sel_p_idx - 1]['sheet_row'])); st.success("삭제 완료"); time.sleep(1); st.cache_data.clear(); st.rerun()

elif selected_menu == "📝 주보":
    st.subheader("📝 주보 관리 및 조회")
    b_mode = st.radio("작업 모드 선택", ["👀 보기", "⚙️ 등록/수정"], horizontal=True)
    st.divider()
    today_date = datetime.date.today(); curr_week_idx = 1
    for i in range(1, 53):
        w_date = start_date + datetime.timedelta(days=(i-1)*7)
        if w_date <= today_date < w_date + datetime.timedelta(days=7): curr_week_idx = i; break
            
    for row_idx in range(0, 52, 4):
        b_cols = st.columns(4)
        for col_idx in range(4):
            week_num = row_idx + col_idx + 1
            if week_num > 52: break
            w_str = f"{week_num}주"; w_date = start_date + datetime.timedelta(days=(week_num-1)*7); d_str = w_date.strftime("%m/%d")
            
            is_bulletin_exist = False
            match_b = df_b[df_b['주차'] == w_str] if not df_b.empty else pd.DataFrame()
            if not match_b.empty and (str(match_b.iloc[0].get('주보이미지1','')).startswith('http') or str(match_b.iloc[0].get('주보이미지2','')).startswith('http')): is_bulletin_exist = True
            
            btn_type = "primary" if is_bulletin_exist else "secondary"
            btn_label = f"✅ {w_str} ({d_str})" if is_bulletin_exist else f"⬜ {w_str} ({d_str})"
            
            with b_cols[col_idx]:
                if week_num == curr_week_idx: st.markdown('<div id="current-week-anchor" style="position:relative; top:-80px;"></div>', unsafe_allow_html=True)
                if st.button(btn_label, key=f"btn_bulletin_{week_num}", use_container_width=True, type=btn_type):
                    if b_mode == "👀 보기":
                        if is_bulletin_exist: view_bulletin_dialog(w_str, d_str, match_b.iloc[0])
                        else: st.warning("아직 등록되지 않았습니다.")
                    else: manage_bulletin_dialog(w_str, w_date.strftime("%Y-%m-%d"))
    st.html("""<script>try { let scrollDoneWeek = false; setInterval(() => { const parentEl = window.parent.document; if (!parentEl) return; const el = parentEl.getElementById('current-week-anchor'); if (el && el.offsetParent !== null && !scrollDoneWeek) { el.scrollIntoView({behavior: 'smooth', block: 'center'}); scrollDoneWeek = true; } else if (el && el.offsetParent === null) { scrollDoneWeek = false; } }, 500); } catch(e) {}</script>""")

elif selected_menu == "⚙️ 행사":
    st.subheader("⚙️ 행사 기록 관리")
    e_tabs = st.tabs(["📂 보기 및 PDF", "➕ 등록", "📝 수정", "🚨 삭제"])
    
    def format_event(row_id):
        if row_id == "선택": return "선택"
        match = df_act[df_act['sheet_row'] == row_id]
        if not match.empty: return f"{match.iloc[0].get('날짜','')} | {match.iloc[0].get('활동명','')}"
        return "알 수 없음"

    with e_tabs[0]:
        if not df_act.empty:
            view_act_df = df_act.copy(); view_act_df['sort_date'] = pd.to_datetime(view_act_df['날짜'], errors='coerce')
            view_act_df = view_act_df.sort_values(by=['sort_date', 'sheet_row'], ascending=[False, False])
            
            html_event = """<html><head><meta charset="utf-8"><style>body { font-family: sans-serif; } table { width: 100%; border-collapse: collapse; } th, td { border: 1px solid #ddd; padding: 8px; } th { background-color: #f1f8ff; } .pb { page-break-before: always; } .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; } img { width: 100%; height: 100%; object-fit: cover; }</style></head><body>"""
            html_event += "<h1>행사 일정 요약표</h1><table><tr><th>날짜</th><th>행사명</th><th>세부 내용</th></tr>"
            for _, row in view_act_df.iterrows(): html_event += f"<tr><td>{row.get('날짜','')}</td><td>{row.get('활동명','')}</td><td>{str(row.get('세부내용',''))[:50]}...</td></tr>"
            html_event += "</table>"
            for _, row in view_act_df.iterrows():
                html_event += f"<div class='pb'></div><h2>{row.get('날짜','')} - {row.get('활동명','')}</h2><p><strong>내용:</strong> {row.get('세부내용','')}</p>"
                v_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                if v_urls:
                    html_event += "<div class='grid'>"
                    for url in v_urls:
                        cl_url = str(url).replace("&vid=1", "").replace("?vid=1", "")
                        if not any(ext in cl_url.lower() for ext in ['vid=1', '.mp4', '.mov']): html_event += f"<div><img src='{cl_url}'></div>"
                    html_event += "</div>"
            html_event += "</body></html>"
            st.download_button(label="📄 전체 행사일정 PDF 다운로드", data=html_event.encode('utf-8'), file_name="행사일정보고서.html", mime="text/html", use_container_width=True)
            st.divider()

            for _, row in view_act_df.iterrows():
                with st.expander(f"📅 {row.get('날짜', '')} | {row.get('활동명', '')}"):
                    st.write(f"**내용:** {row.get('세부내용', '')}")
                    if str(row.get('공지사항', '')).strip(): st.markdown(f"**<span style='color:red;'>공지:</span>** {row.get('공지사항', '')}", unsafe_allow_html=True)
                    v_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                    if v_urls:
                        gallery_html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; width: 100%;">'
                        for media_url in v_urls:
                            clean_url = str(media_url).replace("&vid=1", "").replace("?vid=1", "")
                            if 'vid=1' in str(media_url).lower() or any(ext in str(media_url).lower() for ext in ['.mp4', '.mov']):
                                file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', clean_url) or re.search(r'id=([a-zA-Z0-9_-]+)', clean_url)
                                if file_id_match:
                                    f_id = file_id_match.group(1)
                                    gallery_html += f'''<div style="grid-column: 1 / -1; width: 100%; margin-bottom: 10px;"><iframe src="https://drive.google.com/file/d/{f_id}/preview" width="100%" height="250" style="border:none; border-radius:8px; background:black;"></iframe></div>'''
                                else:
                                    gallery_html += f'''<div style="grid-column: 1 / -1; width: 100%; margin-bottom: 10px;"><video src="{clean_url}" controls playsinline style="width: 100%; height: 250px; border-radius: 8px; background: black; display: block;"></video></div>'''
                            else:
                                gallery_html += f'''<a href="{clean_url}" target="_blank" style="display: block; width: 100%; aspect-ratio: 1/1;"><img src="{clean_url}" loading="lazy" style="width: 100%; height: 100%; object-fit: cover; border-radius: 8px;"></a>'''
                        gallery_html += '</div>'
                        st.markdown(gallery_html, unsafe_allow_html=True)

    with e_tabs[1]:
        with st.form("new_e"):
            a_d = st.date_input("날짜"); a_t = st.text_input("행사명 (필수)"); a_c = st.text_area("내용"); a_n = st.text_input("공지사항")
            a_f = st.file_uploader("미디어 (최대15개)", accept_multiple_files=True, type=['png','jpg','jpeg','webp','mp4','mov'])
            if st.form_submit_button("저장", type="primary"):
                if not a_t.strip(): st.error("행사명을 입력하세요.")
                else:
                    with st.spinner("저장 중..."):
                        urls = [""] * 15
                        if a_f: 
                            for i, f in enumerate(a_f[:15]): urls[i] = upload_photo(f, a_t)
                        act_h = ws_act.row_values(1)
                        missing = [col for col in [f"사진{idx}" for idx in range(1, 16)] if col not in act_h]
                        if missing:
                            start_col = len(act_h) + 1; h_cells = [gspread.Cell(1, start_col + idx_h, mh) for idx_h, mh in enumerate(missing)]
                            for mh in missing: act_h.append(mh)
                            try: chunked_update(ws_act, h_cells)
                            except: ws_act.add_cols(15); chunked_update(ws_act, h_cells)
                        h_map = {str(h): idx for idx, h in enumerate(act_h)}; new_row = [""] * len(act_h)
                        if "날짜" in h_map: new_row[h_map["날짜"]] = str(a_d.strftime("%Y-%m-%d"))
                        if "활동명" in h_map: new_row[h_map["활동명"]] = a_t
                        if "세부내용" in h_map: new_row[h_map["세부내용"]] = a_c
                        if "등록일" in h_map: new_row[h_map["등록일"]] = str(datetime.datetime.now())
                        for k in range(1, 16): 
                            if f"사진{k}" in h_map: new_row[h_map[f"사진{k}"]] = urls[k-1]
                        ws_act.append_row(new_row); st.success("저장 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

    with e_tabs[2]:
        if not df_act.empty:
            sort_act = df_act.copy(); sort_act['sort_date'] = pd.to_datetime(sort_act['날짜'], errors='coerce')
            sort_act = sort_act.sort_values(by=['sort_date', 'sheet_row'], ascending=[False, False])
            event_options = ["선택"] + sort_act['sheet_row'].tolist()
            sel_edit = st.selectbox("수정할 행사", event_options, format_func=format_event)
            if sel_edit != "선택":
                t_row_id = int(sel_edit); t_event = df_act[df_act['sheet_row'] == t_row_id].iloc[0]
                with st.form("edit_event_form"):
                    e_d = st.date_input("날짜", value=parse_date_safe(t_event.get('날짜', ''))); e_t = st.text_input("행사명", value=t_event.get('활동명', ''))
                    e_c = st.text_area("내용", value=t_event.get('세부내용', '')); e_n = st.text_input("공지", value=t_event.get('공지사항', ''))
                    bulk_files = st.file_uploader("일괄 덮어쓰기", accept_multiple_files=True, type=['png','jpg','jpeg','webp','mp4','mov'])
                    old_urls = [t_event.get(f'사진{i}', "") for i in range(1, 16)]; new_files, delete_flags = [None] * 15, [False] * 15
                    for i in range(0, 15, 2):
                        p_cols = st.columns(2)
                        for j in range(2):
                            idx = i + j
                            if idx >= 15: break
                            with p_cols[j]:
                                if old_urls[idx] and str(old_urls[idx]).startswith('http'):
                                    delete_flags[idx] = st.checkbox(f"[{idx+1}] 삭제", key=f"del_{t_row_id}_{idx}")
                                    new_files[idx] = st.file_uploader(f"[{idx+1}] 변경", key=f"up_{t_row_id}_{idx}", label_visibility="collapsed")
                                else: new_files[idx] = st.file_uploader(f"[{idx+1}] 추가", key=f"add_{t_row_id}_{idx}", label_visibility="collapsed")
                    if st.form_submit_button("📝 저장", type="primary"):
                        with st.spinner("저장 중..."):
                            final_urls = old_urls.copy()
                            if bulk_files:
                                final_urls = [""] * 15
                                for k, f in enumerate(bulk_files[:15]): final_urls[k] = upload_photo(f, e_t)
                            else:
                                for k in range(15):
                                    if new_files[k] is not None: final_urls[k] = upload_photo(new_files[k], e_t)
                                    elif delete_flags[k]: final_urls[k] = ""
                            act_h = ws_act.row_values(1)
                            update_map = {"날짜": str(e_d.strftime("%Y-%m-%d")), "활동명": e_t, "세부내용": e_c, "공지사항": e_n}
                            for k in range(1, 16): update_map[f"사진{k}"] = final_urls[k-1]
                            cells_to_update = [gspread.Cell(t_row_id, act_h.index(k)+1, str(v)) for k, v in update_map.items() if k in act_h]
                            if cells_to_update: chunked_update(ws_act, cells_to_update)
                            st.success("수정 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

    with e_tabs[3]:
        if not df_act.empty:
            sel_del = st.selectbox("삭제할 행사", event_options, format_func=format_event, key="del_e")
            if st.button("🚨 삭제 실행") and sel_del != "선택": 
                ws_act.delete_rows(int(sel_del)); st.success("삭제 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

elif selected_menu == "📊 통계":
    st.subheader("📊 통계 흐름 및 개인 누적 출석")
    if not df_stat.empty:
        df_stat_calc = df_stat.copy()
        df_stat_calc['sort_date'] = df_stat_calc['주차'].apply(get_date_from_week_str)
        df_stat_calc = df_stat_calc.sort_values(by='sort_date', ascending=False).drop(columns=['sort_date'])
        
        rename_dict = {'학생재적': '유년부 재적', '학생출석': '유년부 출석', '출석': '유년부 출석', '새친구/추가예배': '추가', '총합계': '총합', '유년부합계': '유년부 합계', '추가입력(비고)': '비고', '내용(비고)': '행사명'}
        df_stat_renamed = df_stat_calc.rename(columns=rename_dict)
        df_stat_renamed.columns = [str(c).strip() for c in df_stat_renamed.columns]
        df_stat_renamed = df_stat_renamed.loc[:, ~df_stat_renamed.columns.duplicated()]
        
        numeric_cols = ['유년부 재적', '유년부 출석', '추가', '유년부 합계', '교사재적', '교사출석', '총합']
        for col in numeric_cols:
            if col in df_stat_renamed.columns: df_stat_renamed[col] = pd.to_numeric(df_stat_renamed[col], errors='coerce').fillna(0).astype(int)
        
        preferred_order = ["주차", "행사명", "유년부 재적", "유년부 출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"]
        actual_order = [c for c in preferred_order if c in df_stat_renamed.columns]
        for c in df_stat_renamed.columns:
            if c not in actual_order: actual_order.append(c)
            
        df_stat_display = df_stat_renamed[actual_order]
        def highlight_stat_cells(row):
            try: att = int(row['유년부 출석']) 
            except: att = -1
            if att == 0: return ['background-color: #ffebee; color: #d32f2f; font-weight: bold;' for _ in row.index]
            styles = ['' for _ in row.index]
            for target_col in ['유년부 합계', '총합']:
                if target_col in row.index:
                    col_idx = row.index.get_loc(target_col)
                    styles[col_idx] = 'background-color: #e3f2fd; color: #0366d6; font-weight: 800;'
            return styles
        styled_df = df_stat_display.style.apply(highlight_stat_cells, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.divider()
    st.write("👤 **개인별 누적 출석**")
    report_df = df[~df[status_col].isin(INACTIVE_STATUS)].copy()
    week_cols = [c for c in report_df.columns if c.endswith('주') or re.match(r'^\d{4}-\d{2}-\d{2}$', str(c))]
    report_df['출석수'] = report_df[week_cols].apply(lambda x: x.astype(str).str.strip().eq('1').sum(), axis=1)
    student_report = report_df[report_df.apply(get_role, axis=1) == 'student']
    student_report = student_report[student_report['출석수'] > 0]
    if not student_report.empty:
        unique_scores = sorted(student_report['출석수'].unique(), reverse=True)[:3]
        if unique_scores:
            st.markdown("<div style='background-color:#f1f8ff; padding:15px; border-radius:10px; margin-bottom:15px;'><h5 style='color:#0366d6; margin-top:0;'>🏆 누적 출석 TOP 3</h5>", unsafe_allow_html=True)
            medals = ["🥇", "🥈", "🥉"]
            for i, score in enumerate(unique_scores):
                group = student_report[student_report['출석수'] == score]
                names = ", ".join([f"{row['이름']}" for _, row in group.iterrows()])
                st.markdown(f"**{medals[i]} {score}회** : {names}")
            st.markdown("</div>", unsafe_allow_html=True)
    st.dataframe(report_df[[class_col, '이름', '출석수']], use_container_width=True, hide_index=True)

elif selected_menu == "🧾 비용집행관리":
    if not st.session_state['chongmu_auth']:
        st.warning("🔒 총무 권한이 필요한 메뉴입니다.")
        cpwd = st.text_input("총무 전용 비밀번호", type="password", key="pwd_receipt")
        if st.button("인증", key="btn_auth_receipt"):
            if cpwd == st.secrets.get("chongmu_password", "admin1234"): st.session_state['chongmu_auth'] = True; st.rerun()
            else: st.error("❌ 불일치")
    else:
        st.subheader("🧾 비용집행관리")
        if not df_r.empty:
            df_r_calc = df_r.copy(); df_r_calc['날짜_dt'] = pd.to_datetime(df_r_calc['날짜'], errors='coerce')
            curr_month = datetime.date.today().replace(day=1)
            this_month_df = df_r_calc[df_r_calc['날짜_dt'].dt.date >= curr_month]
            monthly_cost = pd.to_numeric(this_month_df['비용'], errors='coerce').sum()
            total_cost = pd.to_numeric(df_r_calc['비용'], errors='coerce').sum()
            
            mc1, mc2 = st.columns(2)
            mc1.metric(f"이번 달 ({curr_month.month}월) 집행액", f"{int(monthly_cost):,}원")
            mc2.metric("전체 누적 집행액", f"{int(total_cost):,}원")
            st.divider()

        r_tabs = st.tabs(["👀 조회", "➕ 등록", "📝 수정", "🚨 삭제"])
        with r_tabs[0]:
            if not df_r.empty:
                col_f1, col_f2 = st.columns([1, 1])
                date_range = col_f1.date_input("조회 기간", [df_r_calc['날짜_dt'].min().date(), df_r_calc['날짜_dt'].max().date()])
                keyword = col_f2.text_input("검색어")
                if len(date_range) == 2: s_date, e_date = date_range
                else: s_date, e_date = date_range[0], date_range[0]
                
                df_r_filtered = df_r_calc[(df_r_calc['날짜_dt'].dt.date >= s_date) & (df_r_calc['날짜_dt'].dt.date <= e_date)].copy()
                if keyword: df_r_filtered = df_r_filtered[df_r_filtered.apply(lambda row: keyword in str(row.get('구매처','')) or keyword in str(row.get('내용','')), axis=1)]
                
                if not df_r_filtered.empty:
                    display_df = df_r_filtered[['번호', '날짜', '구매처', '내용', '비용', '비고']].copy()
                    display_df['비용'] = pd.to_numeric(display_df['비용'], errors='coerce').fillna(0).astype(int)
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                else: st.warning("조건에 맞는 내역이 없습니다.")
        with r_tabs[1]:
            with st.form("new_receipt_form"):
                rc_date = st.date_input("날짜", datetime.date.today()).strftime("%Y-%m-%d"); rc_vendor = st.text_input("구매처"); rc_detail = st.text_input("내용"); rc_cost = st.number_input("비용 (원)", min_value=0, step=1000); rc_memo = st.text_input("비고")
                rc_photo = st.file_uploader("영수증 사진 업로드", type=['png', 'jpg', 'jpeg'])
                if st.form_submit_button("등록 완료", type="primary"):
                    if not rc_vendor.strip() or rc_cost == 0: st.error("정보를 정확히 입력하세요.")
                    else:
                        p_url = upload_photo(rc_photo, f"영수증_{rc_vendor}") if rc_photo else ""
                        ws_r.append_row([len(df_r) + 1 if not df_r.empty else 1, rc_date, rc_vendor, rc_detail, rc_cost, rc_memo, p_url]); st.success("등록됨!"); time.sleep(1); st.cache_data.clear(); st.rerun()
        with r_tabs[2]:
            if not df_r.empty:
                opts = ["선택"] + df_r.apply(lambda r: f"No.{r.get('번호','')} | {r.get('구매처','')} | {parse_int_safe(r.get('비용', 0)):,}원", axis=1).tolist()
                sel_idx = st.selectbox("수정할 내역", range(len(opts)), format_func=lambda x: opts[x])
                if sel_idx > 0:
                    target = df_r.iloc[sel_idx - 1]
                    with st.form("edit_rcpt"):
                        e_d = st.date_input("날짜", parse_date_safe(target.get('날짜',''))).strftime("%Y-%m-%d"); e_v = st.text_input("구매처", value=target.get('구매처','')); e_dt = st.text_input("내용", value=target.get('내용','')); e_c = st.number_input("비용", value=parse_int_safe(target.get('비용', 0)), step=1000); e_m = st.text_input("비고", value=target.get('비고',''))
                        if st.form_submit_button("수정 저장"):
                            r_idx = int(target['sheet_row']); chunked_update(ws_r, [gspread.Cell(r_idx, 2, e_d), gspread.Cell(r_idx, 3, e_v), gspread.Cell(r_idx, 4, e_dt), gspread.Cell(r_idx, 5, str(e_c)), gspread.Cell(r_idx, 6, e_m)]); st.success("수정 완료"); time.sleep(1); st.cache_data.clear(); st.rerun()
        with r_tabs[3]:
            if not df_r.empty:
                sel_idx = st.selectbox("삭제 내역", range(len(opts)), format_func=lambda x: opts[x], key="del_r")
                if st.button("🚨 삭제") and sel_idx > 0: ws_r.delete_rows(int(df_r.iloc[sel_idx - 1]['sheet_row'])); st.success("삭제됨!"); time.sleep(1); st.cache_data.clear(); st.rerun()

elif selected_menu == "💰 교사 회비 사용내역":
    if not st.session_state['chongmu_auth']:
        st.warning("🔒 총무 권한이 필요한 메뉴입니다.")
        cpwd_dues = st.text_input("총무 전용 비밀번호 (이 탭에서도 입력 가능)", type="password", key="pwd_dues")
        if st.button("인증", key="btn_auth_dues"):
            if cpwd_dues == st.secrets.get("chongmu_password", "admin1234"): st.session_state['chongmu_auth'] = True; st.rerun()
            else: st.error("❌ 불일치")
    else:
        st.subheader("💰 교사 회비 사용내역 장부")
        with st.container(border=True):
            total_in = pd.to_numeric(df_in['입금액'], errors='coerce').sum() if not df_in.empty else 0
            total_out = pd.to_numeric(df_out['지출액'], errors='coerce').sum() if not df_out.empty else 0
            balance = total_in - total_out
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("🟢 누적 수입 (입금액)", f"{int(total_in):,}원"); col_m2.metric("🔴 누적 지출 (지출액)", f"{int(total_out):,}원"); col_m3.metric("💲 현재 잔액 (총 합계)", f"{int(balance):,}원")
        st.divider()
        
        l_tabs = st.tabs(["👀 전체 조회", "➕ 등록", "📝 수정", "🚨 삭제"])
        with l_tabs[0]:
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                st.markdown("##### 📥 수입 (입금 내역)")
                if not df_in.empty: 
                    disp_in = df_in[['날짜', '입금자명', '입금액', '비고']].copy()
                    st.dataframe(disp_in, use_container_width=True, hide_index=True)
            with col_l2:
                st.markdown("##### 📤 지출 (집행 내역)")
                if not df_out.empty: 
                    disp_out = df_out[['날짜', '내용', '지출액', '비고']].copy()
                    st.dataframe(disp_out, use_container_width=True, hide_index=True)
        with l_tabs[1]:
            tab_in, tab_out = st.tabs(["📥 입금 등록", "📤 지출 등록"])
            with tab_in:
                with st.form("new_income"):
                    in_date = st.date_input("입금 일자").strftime("%Y-%m-%d"); in_name = st.text_input("입금자명"); in_amount = st.number_input("입금액", min_value=0, step=1000); in_memo = st.text_input("비고")
                    if st.form_submit_button("추가", type="primary"):
                        ws_in.append_row([len(df_in) + 1 if not df_in.empty else 1, in_date, in_name, in_amount, in_memo]); st.success("완료"); time.sleep(1); st.cache_data.clear(); st.rerun()
            with tab_out:
                with st.form("new_expense"):
                    out_date = st.date_input("지출 일자").strftime("%Y-%m-%d"); out_detail = st.text_input("내용"); out_amount = st.number_input("지출액", min_value=0, step=1000); out_memo = st.text_input("비고")
                    if st.form_submit_button("추가", type="primary"):
                        ws_out.append_row([len(df_out) + 1 if not df_out.empty else 1, out_date, out_detail, out_amount, out_memo, ""]); st.success("완료"); time.sleep(1); st.cache_data.clear(); st.rerun()
        with l_tabs[2]:
            e_type = st.radio("수정할 장부", ["입금 장부", "지출 장부"], horizontal=True)
            if e_type == "입금 장부" and not df_in.empty:
                opts = ["선택"] + df_in.apply(lambda r: f"[{r.get('날짜','')} | {r.get('입금자명','')}", axis=1).tolist()
                idx = st.selectbox("수정 내역", range(len(opts)), format_func=lambda x: opts[x])
                if idx > 0:
                    t = df_in.iloc[idx - 1]
                    with st.form("edit_in_form"):
                        e_d = st.date_input("날짜", parse_date_safe(t.get('날짜',''))).strftime("%Y-%m-%d"); e_n = st.text_input("입금자명", value=t.get('입금자명','')); e_a = st.number_input("입금액", value=parse_int_safe(t.get('입금액', 0)), step=1000); e_m = st.text_input("비고", value=t.get('비고',''))
                        if st.form_submit_button("저장"): r_idx = int(t['sheet_row']); chunked_update(ws_in, [gspread.Cell(r_idx, 2, e_d), gspread.Cell(r_idx, 3, e_n), gspread.Cell(r_idx, 4, str(e_a)), gspread.Cell(r_idx, 5, e_m)]); st.success("수정 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()
            elif e_type == "지출 장부" and not df_out.empty:
                opts = ["선택"] + df_out.apply(lambda r: f"[{r.get('날짜','')} | {r.get('내용','')}", axis=1).tolist()
                idx = st.selectbox("수정 내역", range(len(opts)), format_func=lambda x: opts[x])
                if idx > 0:
                    t = df_out.iloc[idx - 1]
                    with st.form("edit_out_form"):
                        e_d = st.date_input("날짜", parse_date_safe(t.get('날짜',''))).strftime("%Y-%m-%d"); e_c = st.text_input("내용", value=t.get('내용','')); e_a = st.number_input("지출액", value=parse_int_safe(t.get('지출액', 0)), step=1000); e_m = st.text_input("비고", value=t.get('비고',''))
                        if st.form_submit_button("저장"): r_idx = int(t['sheet_row']); chunked_update(ws_out, [gspread.Cell(r_idx, 2, e_d), gspread.Cell(r_idx, 3, e_c), gspread.Cell(r_idx, 4, str(e_a)), gspread.Cell(r_idx, 5, e_m)]); st.success("수정 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()
        with l_tabs[3]:
            d_type = st.radio("삭제 장부", ["입금 장부", "지출 장부"], horizontal=True)
            if d_type == "입금 장부" and not df_in.empty:
                opts = ["선택"] + df_in.apply(lambda r: f"[{r.get('날짜','')} | {r.get('입금자명','')}", axis=1).tolist()
                idx = st.selectbox("삭제 내역", range(len(opts)), format_func=lambda x: opts[x])
                if st.button("🚨 삭제") and idx > 0: ws_in.delete_rows(int(df_in.iloc[idx-1]['sheet_row'])); st.success("삭제됨"); time.sleep(1); st.cache_data.clear(); st.rerun()
            elif d_type == "지출 장부" and not df_out.empty:
                opts = ["선택"] + df_out.apply(lambda r: f"[{r.get('날짜','')} | {r.get('내용','')}", axis=1).tolist()
                idx = st.selectbox("삭제 내역", range(len(opts)), format_func=lambda x: opts[x])
                if st.button("🚨 삭제") and idx > 0: ws_out.delete_rows(int(df_out.iloc[idx-1]['sheet_row'])); st.success("삭제됨"); time.sleep(1); st.cache_data.clear(); st.rerun()
