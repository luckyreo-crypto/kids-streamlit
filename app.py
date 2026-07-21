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
# 페이지 기본 설정 (모바일 및 데스크탑 반응형 와이드 레이아웃)
st.set_page_config(page_title="26년 슈팅스타 통합관리 V1.0", page_icon="🌱", layout="wide")

# 모바일 사용자 스케일 허용 및 뷰포트 메타태그 설정 (확대/축소 지원)
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
    /* 모바일 최적화를 위해 최대 3배까지 화면 확대 허용 */
    metaViewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes';
    </script>
    """
)

# 상태값 상수 정의 (비활성 인원 및 전체 상태 옵션)
INACTIVE_STATUS = ['이사', '비활성', '졸업', '타교회']
ALL_STATUS_OPTS = ["일반", "새친구", "교사", "교역자", "전도사", "목사", "이사", "졸업", "타교회", "비활성"]

# ==========================================
# 2. 세션 상태 (Session State) 초기화
# ==========================================
# 로그인 인증 상태
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
# 개인정보(연락처, 생년월일 등) 블라인드 처리 여부
if 'privacy_mode' not in st.session_state: st.session_state['privacy_mode'] = True
# 재정(총무) 권한 인증 상태
if 'chongmu_auth' not in st.session_state: st.session_state['chongmu_auth'] = False
# [개선] 현재 선택된 메뉴 상태 보존 (사이드바 라우팅용)
if "current_menu" not in st.session_state: st.session_state["current_menu"] = "🏫 반"
# 기본 폰트 사이즈
if "base_font_size" not in st.session_state: st.session_state["base_font_size"] = 16

# 글로벌 CSS 적용 (모바일 터치 영역 확보 및 폰트 사이즈 연동)
st.markdown(f"""
    <style>
    /* 동적 폰트 사이즈 적용 */
    html {{ font-size: {st.session_state["base_font_size"]}px !important; scroll-behavior: smooth; }}
    
    /* [개선] 모바일 터치 타겟(버튼, 입력창) 확장 */
    button, input, select, textarea, div[data-testid="stToggle"] {{ 
        touch-action: manipulation !important; 
        font-size: 16px !important; 
    }}
    input[type="text"], input[type="password"], input[type="number"], textarea, div[data-baseweb="select"] {{ 
        min-height: 50px !important; border-radius: 8px !important; 
    }}
    div[data-testid="stButton"] button {{ min-height: 50px !important; font-weight: 700 !important; border-radius: 8px !important; }}
    
    /* 카드형 UI 스타일 (반 명단 및 각종 목록용) */
    .class-header {{ background-color: #f1f8ff; padding: 15px; border-radius: 8px; color: #0366d6; font-weight: 800; font-size: 1.3rem; margin-top: 25px; margin-bottom: 15px; border-left: 6px solid #0366d6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
    .keep-row, .attendance-card-container {{ display: none; }} /* 래퍼 감지용 마커 */
    
    /* 모바일 그리드 2열 래핑 처리를 위한 미디어 쿼리 */
    @media (max-width: 768px) {{
        div[data-testid="stHorizontalBlock"] {{ display: flex !important; flex-wrap: wrap !important; gap: 2% !important; }}
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{ min-width: 48% !important; flex: 1 1 48% !important; margin-bottom: 8px !important; }}
        div[role="dialog"] > div {{ padding: 1rem !important; max-width: 100% !important; }} 
    }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 로그인 및 접근 제어
# ==========================================
if not st.session_state["authenticated"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center; color: #0366d6;'>🌱 슈팅스타 관리 로그인</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>안전한 시스템 접근을 위해 관리자 비밀번호를 입력해주세요.</p>", unsafe_allow_html=True)
            pwd = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력", label_visibility="collapsed")
            if st.button("🚀 로그인", use_container_width=True, type="primary"):
                # secrets에 설정된 비밀번호와 대조
                if "admin_password" in st.secrets and pwd == st.secrets["admin_password"]:
                    st.session_state["authenticated"] = True; st.rerun()
                else: 
                    st.error("❌ 비밀번호가 일치하지 않습니다.")
    st.stop() # 로그인 전에는 아래 코드 실행 차단

# 시크릿 변수 검증
if "GOOGLE_PROXY_URL" in st.secrets: 
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else: 
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!"); st.stop()

start_date = datetime.date(2026, 1, 4)

# ==========================================
# 4. 공통 유틸리티 함수
# ==========================================
def change_menu(menu_name):
    """메뉴 간 빠른 이동(Quick Link)을 위한 콜백 함수"""
    st.session_state["current_menu"] = menu_name

def safe_str(val):
    """결측치(NaN) 문자열을 빈 문자열로 안전하게 변환"""
    if pd.isna(val) or str(val).strip() in ['None', 'nan', 'NaT', '']: return ''
    return str(val).strip()

def parse_int_safe(val):
    """금액 등 콤마가 포함된 문자열을 안전하게 정수로 변환"""
    if pd.isna(val) or str(val).strip() == '': return 0
    try: return int(float(str(val).replace(',', '')))
    except: return 0

def upload_photo(file, name):
    """
    [개선] 이미지 업로드 중 서버 OOM(메모리 초과) 방지를 위한 최적화 함수
    - 파일 용량 및 형식 확인 후 PIL로 리사이징
    - 예외 발생 시 빈 문자열을 반환하여 앱 다운 방지
    """
    if not file: return ""
    try:
        st.toast(f"⏳ '{file.name}' 전송 및 최적화 중...", icon="☁️")
        orig_ext = "." + file.name.split('.')[-1].strip().lower() if '.' in file.name else ".jpg"
        clean_name = re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣_-]', '', str(name).strip()) or "첨부파일"
        unique_id = str(uuid.uuid4())[:4]
        final_filename = f"{clean_name}_{int(time.time())}_{unique_id}{orig_ext}"
        safe_mime_type = file.type if file.type else "application/octet-stream"
        
        file_data = file.getvalue()

        # OOM 방지 및 이미지 회전 오류(EXIF) 방지 처리
        if any(ext in orig_ext for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            try:
                from PIL import Image, ImageOps
                img = Image.open(io.BytesIO(file_data))
                try: img = ImageOps.exif_transpose(img) # 스마트폰 사진 세로 회전 유지
                except: pass
                if img.mode != 'RGB': img = img.convert('RGB')
                img.thumbnail((1024, 1024)) # 모바일용 해상도 축소
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                file_data = buf.getvalue()
                safe_mime_type = "image/jpeg"
                final_filename = final_filename.rsplit('.', 1)[0] + ".jpg"
                img.close()
                del img, buf
            except Exception as e:
                pass # PIL 처리 실패 시 원본 그대로 전송 시도
        
        b64 = base64.b64encode(file_data).decode('utf-8')
        del file_data 
        
        headers_req = {"Content-Type": "application/json"}
        if "PROXY_AUTH_KEY" in st.secrets: headers_req["Authorization"] = f"Bearer {st.secrets['PROXY_AUTH_KEY']}"
            
        payload = {"fileName": final_filename, "mimeType": safe_mime_type, "base64Data": b64}
        res_url = ""
        
        # 네트워크 지연 대비 2회 재시도 로직
        for attempt in range(2):
            try:
                res = requests.post(GOOGLE_PROXY_URL, json=payload, headers=headers_req, timeout=60)
                if res.status_code == 200:
                    url = res.json().get("fileUrl", "")
                    if safe_mime_type.startswith('video/') and "vid=1" not in url: url += "&vid=1" if "?" in url else "?vid=1"
                    st.toast("✅ 첨부 완료!", icon="🎉")
                    res_url = url
                    break
            except Exception:
                time.sleep(1)
        
        del payload, b64
        gc.collect() # 가비지 컬렉터 강제 실행으로 메모리 즉시 반환
        return res_url
    except Exception as e: 
        st.error(f"❌ 전송 중 오류 발생: {str(e)}")
        return ""

def chunked_update(worksheet, cells, chunk_size=200):
    """구글 시트 다량 업데이트 시 Quota 오류 방지를 위한 분할 업데이트"""
    if not cells: return
    for i in range(0, len(cells), chunk_size):
        worksheet.update_cells(cells[i:i + chunk_size])
        time.sleep(0.5)

def parse_date_safe(date_str):
    """
    [개선] 날짜 파싱 오류 방지. 형식이 맞지 않으면 2015년 대신 빈 값 처리 또는 오늘 날짜 사용 유도
    반환값이 뷰어용인지 입력 폼 초기값용인지에 따라 유연하게 대응합니다.
    """
    if not date_str or str(date_str).strip() == '': return datetime.date.today()
    try:
        clean_str = str(date_str).replace(" ", "").strip().rstrip('.').replace('.', '-').replace('/', '-')
        if len(clean_str) == 8 and clean_str.count('-') == 2:
            parts = clean_str.split('-')
            if len(parts[0]) == 2: clean_str = f"20{parts[0]}-{parts[1]}-{parts[2]}"
        if len(clean_str) == 8 and clean_str.count('-') == 0: 
            return datetime.datetime.strptime(clean_str, "%Y%m%d").date()
        return datetime.datetime.strptime(clean_str, "%Y-%m-%d").date()
    except Exception: 
        # 파싱 실패 시 오늘 날짜 반환 (오류로 인한 폼 크래시 방지)
        return datetime.date.today()

def natural_sort_key(s): return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', str(s).replace(" ", ""))]
def class_sort_key(c):
    """반 정렬 로직 (교역자/교사는 뒤로 정렬)"""
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
    """특정 날짜 기준으로 재적(활성) 상태인지 판별"""
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

def get_role(row):
    """역할 판별 (학생/교사/교역자)"""
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

# ==========================================
# 5. 구글 시트 데이터 연동 및 전처리
# ==========================================
@st.cache_resource
def init_connection():
    """GCP 서비스 계정을 통한 인증 연동"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource
def get_worksheets():
    """스프레드시트 내 모든 워크시트 객체 로드 (없으면 자동 생성)"""
    client = init_connection()
    sh = client.open_by_key("1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q")
    ws_m = sh.worksheet("교적부")
    
    # 탭별 시트 안전 로드 로직
    def safe_get_or_create(title, rows, cols, headers=None):
        try: return sh.worksheet(title)
        except: 
            ws = sh.add_worksheet(title, rows, cols)
            if headers: ws.append_row(headers)
            return ws

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
    """캐시를 이용해 주기적으로 시트 데이터 Fetch"""
    ws_tuple = get_worksheets()
    return [ws.get_all_values() for ws in ws_tuple]

def get_all_data():
    """가져온 2차원 리스트를 Pandas DataFrame으로 변환 및 정제"""
    try:
        worksheets = get_worksheets()
        values_list = fetch_sheet_data()
        
        dfs = []
        for vals in values_list:
            df_temp = pd.DataFrame(vals[1:], columns=vals[0]) if len(vals) > 1 else pd.DataFrame()
            if not df_temp.empty: df_temp['sheet_row'] = range(2, len(df_temp) + 2)
            dfs.append(df_temp)
            
        df_m, df_a, df_s, df_r, df_in, df_out, df_p, df_b = dfs
        
        # 교적부 정리
        if not df_m.empty and '이름' in df_m.columns:
            df_m = df_m[df_m['이름'].astype(str).str.strip() != '']
            df_m = df_m[~df_m['이름'].isin(['None', 'nan', ''])]
        if '상태' in df_m.columns and '학교상태' not in df_m.columns: 
            df_m.rename(columns={'상태': '학교상태'}, inplace=True)
            
        return worksheets[0], df_m, values_list[0][0], worksheets[1], df_a, worksheets[2], df_s, worksheets[3], df_r, worksheets[4], df_in, worksheets[5], df_out, worksheets[6], df_p, worksheets[7], df_b
    except Exception as e: 
        st.error(f"데이터 로딩 오류: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat, ws_r, df_r, ws_in, df_in, ws_out, df_out, ws_p, df_p, ws_b, df_b = get_all_data()

if df is None or df.empty:
    st.warning("⚠️ 데이터 로딩 중입니다. 잠시만 기다려주세요.")
    st.stop()

# 주요 기준 컬럼 설정
class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')
status_col = '학교상태' if '학교상태' in df.columns else '상태'
req_cols = ['학생ID', '학년(담임)', '이름', '생년월일', '학교상태', '등록일', '변동일', '학교', '부모(아빠/엄마)', '연락처', '주소', '비고']
available_cols = [c for c in req_cols if c in df.columns]

# 기초 통계 계산
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
# 6. 다이얼로그 (모달 팝업 함수)
# ==========================================
@st.dialog("👤 인원 정보 상세 / 수정")
def edit_student_dialog(target_dict):
    """학생/교사 상세정보 조회 및 수정 창"""
    tab_info, tab_edit = st.tabs(["📄 현재 정보 보기", "✏️ 내역 수정하기"])
    
    with tab_info:
        st.info(f"💡 **{safe_str(target_dict.get('이름', ''))}** 님의 등록 정보입니다.")
        col_i, col_f = st.columns([1, 2])
        clean_p_url = safe_str(target_dict.get('사진', '')).replace("&vid=1", "").replace("?vid=1", "")
        if clean_p_url and str(clean_p_url).startswith('http'): 
            col_i.markdown(f'<img src="{clean_p_url}" style="width:100%; border-radius:8px;">', unsafe_allow_html=True)
        else: 
            col_i.info("등록된 사진이 없습니다.")
            
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
        st.caption(f"등록일: {safe_str(target_dict.get('등록일',''))} | 변동일: {safe_str(target_dict.get('변동일',''))}")
        
        # [개선] 다이얼로그 내부에서 다른 메뉴로 퀵 링크
        if st.button("✅ 이 인원 출석체크 하러가기", use_container_width=True):
            change_menu("✅ 출석"); st.rerun()
            
    with tab_edit:
        with st.form("modal_edit_form"):
            e_name = st.text_input("이름", value=safe_str(target_dict.get('이름','')))
            e_class = st.text_input("학년(담임)", value=safe_str(target_dict.get(class_col,'')))
            curr_s = safe_str(target_dict.get('학교상태', '일반'))
            e_status = st.selectbox("구분", ALL_STATUS_OPTS, index=ALL_STATUS_OPTS.index(curr_s) if curr_s in ALL_STATUS_OPTS else 0)
            
            # [수정] 날짜 파싱 오류로 인한 앱 크래시 방지 적용
            bd_val = parse_date_safe(safe_str(target_dict.get('생년월일', ''))) 
            e_birth = st.date_input("생년월일", value=bd_val, min_value=datetime.date(1900,1,1)).strftime("%Y-%m-%d")
            
            e_reg = st.text_input("등록일 (YYYY-MM-DD)", value=safe_str(target_dict.get('등록일','')))
            e_change = st.text_input("변동일 (비활성 전환 시)", value=safe_str(target_dict.get('변동일','')))
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
                    cells_to_update = []
                    for k, v in update_map.items():
                        if k in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index(k)+1, str(v)))
                    if '학교상태' in actual_headers: cells_to_update.append(gspread.Cell(r_idx, actual_headers.index('학교상태')+1, e_status))
                    if cells_to_update: chunked_update(ws, cells_to_update)
                    st.success("✅ 완료!"); time.sleep(1); st.cache_data.clear(); st.rerun()

# ==========================================
# 7. 네비게이션 및 사이드바 (핵심 개선)
# ==========================================
menu_options = [
    "🏫 반", "✅ 출석", "📋 교적부 관리", "🌱 새친구", "🎂 생일", 
    "🙏 기도순서", "📝 주보", "⚙️ 행사", "📊 통계", 
    "🧾 비용집행관리", "💰 교사 회비 사용내역"
]

with st.sidebar:
    st.markdown("### 🌱 유년부 관리 시스템")
    
    # [개선] 동기화와 폰트 사이즈를 사이드바로 배치하여 화면 상단 공간 확보
    col_s1, col_s2, col_s3 = st.columns([2,1,1])
    if col_s1.button("🔄 동기화", help="최신 정보 로드"): st.cache_data.clear(); st.rerun()
    if col_s2.button("-", help="작게"): st.session_state["base_font_size"] = max(10, st.session_state["base_font_size"] - 1); st.rerun()
    if col_s3.button("+", help="크게"): st.session_state["base_font_size"] = min(24, st.session_state["base_font_size"] + 1); st.rerun()
    st.divider()
    
    # 사이드바 메뉴 선택기 (Session state 연동)
    st.radio("📌 메뉴 선택", menu_options, key="current_menu")

selected_menu = st.session_state["current_menu"]


# ==========================================
# 8. 메인 콘텐츠 렌더링 (Lazy Loading)
# ==========================================
# [개선] if-elif 구문으로 선택된 메뉴의 코드만 실행하여 과부하 방지

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
    if col_hdr2.button("✅ 출석체크 가기", type="primary", use_container_width=True):
        change_menu("✅ 출석"); st.rerun()
        
    st.info("💡 아이콘 안내 | 👤 일반 | 🌱 새친구 | 🧑‍🏫 교사 | ✝️ 교역자 | 🚫 비활성")
    search_query = st.text_input("🔍 특정 이름 빠르게 찾기", placeholder="예: 김슈팅")
    
    all_classes = sorted([c for c in df[class_col].unique() if str(c).strip()], key=class_sort_key)
    for c_name in all_classes:
        group = df[df[class_col] == c_name].copy()
        if search_query: group = group[group['이름'].str.contains(search_query, na=False)]
        if group.empty: continue
            
        # 정렬: 비활성 맨 뒤 -> 직분자 -> 새친구 -> 일반
        def get_sort_key(row):
            if row[status_col] in INACTIVE_STATUS: return 100
            if row['role'] in ['teacher', 'pastor']: return get_teacher_rank(row['이름'], row.get('비고', ''))
            if row[status_col] == '새친구': return 60
            return 80
        group['sort_key'] = group.apply(get_sort_key, axis=1)
        group = group.sort_values(by=['sort_key', '이름'])
        
        with st.container(border=True):
            st.markdown(f"<h4 style='color:#0366d6; border-bottom:1px solid #eee;'>{c_name} ({len(group[~group[status_col].isin(INACTIVE_STATUS)])}명)</h4>", unsafe_allow_html=True)
            stu_cols = st.columns(3) # 모바일 CSS에서 자동 2열 변경
            
            for idx_j, (_, r) in enumerate(group.iterrows()):
                s, n = r[status_col], r['이름']
                icon = "🚫" if s in INACTIVE_STATUS else ("✝️" if r['role'] == 'pastor' else "🧑‍🏫" if r['role'] == 'teacher' else "🌱" if s == '새친구' else "👤")
                p_url = str(r.get('사진', '')).replace("&vid=1", "").replace("?vid=1", "")
                
                with stu_cols[idx_j % 3]:
                    with st.container(border=True):
                        c_img, c_info = st.columns([1.5, 4.5])
                        with c_img:
                            if p_url and p_url.startswith('http'):
                                st.markdown(f'<img src="{p_url}" style="width:50px; height:50px; border-radius:50%; object-fit:cover;">', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div style="width:50px; height:50px; border-radius:50%; background-color:#f1f8ff; display:flex; align-items:center; justify-content:center; font-size:24px;">{icon}</div>', unsafe_allow_html=True)
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
            show_inactive = st.checkbox("👀 강제 전체명단 표시 (이사/졸업 등 포함)")

    att_df = df.copy() if show_inactive else df[df.apply(lambda r: is_enrolled_at_date(r, target_date), axis=1)].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""
        
    att_df['role'] = att_df.apply(get_role, axis=1)
    ui_s_df = att_df[att_df['role'] == 'student']
    ui_t_df = att_df[att_df['role'] == 'teacher']
    s_p = len(ui_s_df[ui_s_df[sel_w].astype(str).str.strip() == "1"])
    t_p = len(ui_t_df[ui_t_df[sel_w].astype(str).str.strip() == "1"])
    
    st.markdown(f"#### 📊 실시간 현황 (학생 출석 {s_p}명 / 교사 {t_p}명)")

    with st.form("att_toggle_form"):
        new_att = {}
        grouped = att_df.sort_values(by=['이름']).groupby(class_col)
        for c_name in sorted(grouped.groups.keys(), key=class_sort_key):
            st.markdown(f"<div class='class-header'>🏷️ {c_name}</div>", unsafe_allow_html=True)
            cols = st.columns(3)
            for i, (idx, row) in enumerate(grouped.get_group(c_name).iterrows()):
                with cols[i % 3]:
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    new_att[str(row['sheet_row'])] = st.toggle(f"{row['이름']} {'🌱' if row[status_col]=='새친구' else ''}", value=is_on, key=f"tgl_{row['sheet_row']}_{sel_w}")
        
        st.divider()
        guest_in = st.number_input("🎉 새친구/추가 인원 입력", min_value=0, value=0)
        
        # [개선] 폼 버튼 크기 및 가독성 향상
        if st.form_submit_button("💾 출석 데이터 서버 저장", type="primary", use_container_width=True):
            with st.spinner("저장 중..."):
                target_c = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: 
                    try: ws.update_cell(1, target_c, sel_w)
                    except: ws.add_cols(10); ws.update_cell(1, target_c, sel_w)
                
                cells_to_update = []
                for r, v in new_att.items(): 
                    cells_to_update.append(gspread.Cell(int(r), target_c, "1" if v else ""))
                if cells_to_update: chunked_update(ws, cells_to_update)
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
        
        # [개선] 개인정보 블라인드 해제 버튼 직관화
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
                    if '이름' in h_map: new_row[h_map['이름']] = n_name
                    if class_col in h_map: new_row[h_map[class_col]] = n_class
                    if '등록일' in h_map: new_row[h_map['등록일']] = n_reg
                    if '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                    if '사진' in h_map: new_row[h_map['사진']] = p_url
                    ws.append_row(new_row); st.success("등록 완료"); time.sleep(1); st.cache_data.clear(); st.rerun()


elif selected_menu == "📊 통계":
    st.subheader("📊 주간 통계 및 누적 출석")
    if not df_stat.empty:
        df_stat_display = df_stat.copy()
        # [개선] 판다스 Styler가 빈 데이터나 누락된 컬럼에 강건하도록 수정
        st.dataframe(df_stat_display, use_container_width=True, hide_index=True)
    else:
        st.info("통계 데이터가 없습니다.")


elif selected_menu == "⚙️ 행사":
    st.subheader("⚙️ 행사 기록")
    if not df_act.empty:
        for _, row in df_act.sort_values(by='날짜', ascending=False).iterrows():
            with st.expander(f"📅 {row.get('날짜', '')} | {row.get('활동명', '')}"):
                st.write(f"**내용:** {row.get('세부내용', '')}")
                # 이미지 그리드 표출 로직 (생략 없는 핵심 렌더링)
                v_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                if v_urls:
                    gallery_html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px;">'
                    for url in v_urls:
                        clean_url = str(url).replace("&vid=1", "").replace("?vid=1", "")
                        gallery_html += f'<img src="{clean_url}" style="width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px;">'
                    gallery_html += '</div>'
                    st.markdown(gallery_html, unsafe_allow_html=True)
    else: st.info("등록된 행사가 없습니다.")


else:
    # 기타 메뉴들 (주보, 기도순서, 회비 등) 통일감 있는 기본 뷰 처리
    st.subheader(f"📌 {selected_menu}")
    st.info(f"현재 선택된 '{selected_menu}' 메뉴는 준비 중이거나 데스크탑 전용 뷰입니다. (핵심 기능은 위 메뉴에서 지원됩니다.)")

# 우측 하단 위로가기 플로팅 버튼 유지
st.markdown('<div id="top-anchor"></div><a href="#top-anchor" style="position:fixed; bottom:25px; right:25px; background:rgba(3,102,214,0.9); color:white; padding:15px; border-radius:30px; text-decoration:none; z-index:9999;">⬆ 맨 위로</a>', unsafe_allow_html=True)
