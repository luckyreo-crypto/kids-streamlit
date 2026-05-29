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
st.set_page_config(page_title="26년 슈팅스타 통합관리", page_icon="🌱", layout="wide")
st.markdown('<div id="top-anchor"></div>', unsafe_allow_html=True)

components.html(
    """
    <script>
    window.history.pushState(null, "", window.location.href);
    window.onpopstate = function() { window.history.pushState(null, "", window.location.href); };
    </script>
    """, height=0, width=0
)

INACTIVE_STATUS = ['이사', '비활성', '졸업', '타교회']
ALL_STATUS_OPTS = ["일반", "새친구", "교사", "교역자", "전도사", "목사", "이사", "졸업", "타교회", "비활성"]

st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 16px !important; }
    .class-header { background-color: #f1f8ff; padding: 15px 20px; border-radius: 10px; color: #0366d6; font-weight: 900; font-size: 1.2rem; margin-top: 25px; margin-bottom: 15px; border-left: 6px solid #0366d6; }
    div[data-testid="stToggle"] { border: 2px solid #eef2f6; padding: 12px 15px; border-radius: 12px; background-color: #ffffff; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px; }
    div[data-testid="stToggle"]:hover { border-color: #0366d6; background-color: #f8fbff; }
    div[data-testid="stButton"] button { width: 100%; border-radius: 8px; text-align: left; padding: 10px 12px; font-size: 1.05rem; white-space: normal; word-wrap: break-word; word-break: keep-all; min-height: 45px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stTabs"] > div:first-child { position: -webkit-sticky !important; position: sticky !important; top: 3.5rem !important; background-color: #ffffff !important; z-index: 999990 !important; padding: 10px 0 !important; }
    div[data-baseweb="tab"] { flex: 0 0 auto !important; padding: 8px 12px !important; margin: 2px !important; background-color: #f8f9fa; border-radius: 8px; border: 1px solid #ddd; }
    div[data-baseweb="tab"][aria-selected="true"] { background-color: #0366d6 !important; color: white !important; }
    div[data-baseweb="tab"] p { font-size: 1.05rem !important; font-weight: 800 !important; }
    .fab-button { position: fixed; bottom: 25px; right: 25px; left: auto; background-color: rgba(3, 102, 214, 0.9); color: white !important; padding: 12px 20px; border-radius: 30px; text-decoration: none; font-weight: 900; font-size: 1rem; box-shadow: 0 5px 15px rgba(0,0,0,0.4); z-index: 999999; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 시스템 접근 제어 ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if 'privacy_mode' not in st.session_state: st.session_state['privacy_mode'] = True
if 'chongmu_auth' not in st.session_state: st.session_state['chongmu_auth'] = False

if not st.session_state["authenticated"]:
    with st.container(border=True):
        st.markdown("<h2 style='text-align: center; color: #0366d6;'>🌱 슈팅스타 통합관리 로그인</h2>", unsafe_allow_html=True)
        pwd = st.text_input("비밀번호 입력", type="password", placeholder="비밀번호")
        if st.button("🚀 시스템 로그인", type="primary"):
            if "admin_password" in st.secrets and pwd == st.secrets["admin_password"]:
                st.session_state["authenticated"] = True; st.rerun()
            else: st.error("❌ 비밀번호 불일치")
    st.stop()

GOOGLE_PROXY_URL = st.secrets.get("GOOGLE_PROXY_URL", "")

start_date = datetime.date(2026, 1, 4)

# --- 3. 유틸리티 함수 ---
def safe_str(val): return '' if pd.isna(val) or str(val).strip() in ['None', 'nan', 'NaT', ''] else str(val).strip()
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
        worksheet.update_cells(cells[i:i + chunk_size]); time.sleep(0.5)

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
    if any(k in c_str for k in ['교역자', '전도사', '목사']): return (3, natural_sort_key(c_str))
    elif any(k in c_str for k in ['선생님', '교사']): return (2, natural_sort_key(c_str))
    return (1, natural_sort_key(c_str))

def get_teacher_rank(name, memo):
    text = str(name) + " " + str(memo)
    match = re.search(r'\[(\d+)\]', text)
    if match: return int(match.group(1))
    if '전도사' in text or '목사' in text: return 10
    if '부장' in text: return 20
    if '총무' in text: return 40
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
    if s in ['교역자', '전도사', '목사'] or any(k in m for k in ['전도사', '목사']) or any(k in c for k in ['교역자', '목사']): return 'pastor'
    if s == '교사' or any(k in c for k in ['교사', '선생님']) or any(k in m for k in ['교사', '부장', '총무']): return 'teacher'
    return 'student'

def check_is_staff(row):
    s, c, m = safe_str(row.get('학교상태', '')), safe_str(row.get('학년(담임)', '')), safe_str(row.get('비고', ''))
    if s in ['교사', '교역자', '전도사', '목사']: return True
    if s in INACTIVE_STATUS and (any(k in c for k in ['교사', '목사']) or any(k in m for k in ['교사', '총무'])): return True
    return False

# --- 4. 시트 연동 ---
@st.cache_resource
def init_connection():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds)

@st.cache_resource
def get_worksheets():
    sh = init_connection().open_by_key("1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q")
    ws_m = sh.worksheet("교적부")
    try: ws_a = sh.worksheet("활동간식")
    except: ws_a = sh.add_worksheet("활동간식", 500, 20); ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항"] + [f"사진{i}" for i in range(1, 16)] + ["등록일"])
    try: ws_s = sh.worksheet("주차별통계")
    except: ws_s = sh.add_worksheet("주차별통계", 200, 15); ws_s.append_row(["주차", "행사명", "유년부 재적", "출석", "추가", "유년부 합계", "교사재적", "교사출석", "총합", "비고", "업데이트일시"])
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

ws, ws_a, ws_s, ws_r, ws_in, ws_out, ws_p, ws_b = get_worksheets()
vals_m, vals_a, vals_s, vals_r, vals_in, vals_out, vals_p, vals_b = fetch_sheet_data()

df = pd.DataFrame(vals_m[1:], columns=vals_m[0]) if len(vals_m)>1 else pd.DataFrame()
if not df.empty: 
    df['sheet_row'] = range(2, len(df)+2)
    df = df[df['이름'].astype(str).str.strip() != '']
    if '상태' in df.columns and '학교상태' not in df.columns: df.rename(columns={'상태': '학교상태'}, inplace=True)
headers = vals_m[0]
df_act = pd.DataFrame(vals_a[1:], columns=vals_a[0]) if len(vals_a)>1 else pd.DataFrame()
if not df_act.empty: df_act['sheet_row'] = range(2, len(df_act)+2)
df_stat = pd.DataFrame(vals_s[1:], columns=vals_s[0]) if len(vals_s)>1 else pd.DataFrame()
df_r = pd.DataFrame(vals_r[1:], columns=vals_r[0]) if len(vals_r)>1 else pd.DataFrame()
if not df_r.empty: df_r['sheet_row'] = range(2, len(df_r)+2)
df_in = pd.DataFrame(vals_in[1:], columns=vals_in[0]) if len(vals_in)>1 else pd.DataFrame()
if not df_in.empty: df_in['sheet_row'] = range(2, len(df_in)+2)
df_out = pd.DataFrame(vals_out[1:], columns=vals_out[0]) if len(vals_out)>1 else pd.DataFrame()
if not df_out.empty: df_out['sheet_row'] = range(2, len(df_out)+2)
df_p = pd.DataFrame(vals_p[1:], columns=vals_p[0]) if len(vals_p)>1 else pd.DataFrame()
if not df_p.empty: df_p['sheet_row'] = range(2, len(df_p)+2)
df_b = pd.DataFrame(vals_b[1:], columns=vals_b[0]) if len(vals_b)>1 else pd.DataFrame()
if not df_b.empty: df_b['sheet_row'] = range(2, len(df_b)+2)

class_col = '학년(담임)' if '학년(담임)' in df.columns else '반'
status_col = '학교상태'

# --- 다이얼로그(팝업) 모음 ---
@st.dialog("👤 학생 정보 상세", width="large")
def edit_student_dialog(target_dict):
    r_id = target_dict['sheet_row']
    ek = f"edit_{r_id}"
    if ek not in st.session_state: st.session_state[ek] = False
    
    if not st.session_state[ek]:
        st.markdown(f"### 🎈 {safe_str(target_dict.get('이름', ''))}", unsafe_allow_html=True)
        img_url = safe_str(target_dict.get('사진', '')).replace("&vid=1","")
        if img_url and 'http' in img_url: st.markdown(f'<img src="{img_url}" style="width:100%; max-width:300px; border-radius:15px; margin:auto; display:block; margin-bottom:20px;">', unsafe_allow_html=True)
        
        st.markdown(f"**🏫 반:** {safe_str(target_dict.get(class_col,''))}")
        if st.session_state.get('privacy_mode', True):
            st.markdown(f"**📞 연락처:** 🔒 보호됨\n\n**🏠 주소:** 🔒 보호됨\n\n**🎂 생일:** 🔒 보호됨")
        else:
            st.markdown(f"**📞 연락처:** {safe_str(target_dict.get('연락처',''))}")
            st.markdown(f"**👨‍👩‍👦 부모:** {safe_str(target_dict.get('부모(아빠/엄마)',''))}")
            st.markdown(f"**🏠 주소:** {safe_str(target_dict.get('주소',''))}")
            st.markdown(f"**🎂 생일:** {safe_str(target_dict.get('생년월일',''))}")
        st.markdown(f"**📝 비고:** {safe_str(target_dict.get('비고',''))}")
        st.button("✏️ 정보 수정", use_container_width=True, on_click=lambda: st.session_state.update({ek: True}))
    else:
        st.warning("정보 수정 중")
        with st.form("edit_form_s"):
            e_name = st.text_input("이름", value=safe_str(target_dict.get('이름','')))
            e_class = st.text_input("학년(담임)", value=safe_str(target_dict.get(class_col,'')))
            curr_s = safe_str(target_dict.get('학교상태', '일반'))
            e_status = st.selectbox("구분", ALL_STATUS_OPTS, index=ALL_STATUS_OPTS.index(curr_s) if curr_s in ALL_STATUS_OPTS else 0)
            e_birth = st.date_input("생년월일", value=parse_date_safe(safe_str(target_dict.get('생년월일','')))).strftime("%Y-%m-%d")
            e_phone = st.text_input("연락처", value=safe_str(target_dict.get('연락처','')))
            e_addr = st.text_input("주소", value=safe_str(target_dict.get('주소','')))
            e_memo = st.text_input("비고", value=safe_str(target_dict.get('비고','')))
            e_photo = st.file_uploader("새 사진 등록/변경", type=['png','jpg','jpeg'])
            
            if st.form_submit_button("💾 변경사항 저장", type="primary", use_container_width=True):
                p_url = upload_photo(e_photo, e_name) if e_photo else safe_str(target_dict.get('사진',''))
                up_map = {'이름':e_name, class_col:e_class, '생년월일':e_birth, '연락처':e_phone, '주소':e_addr, '비고':e_memo, '학교상태':e_status, '상태':e_status, '사진':p_url}
                cells = []
                for k,v in up_map.items():
                    if k in headers: cells.append(gspread.Cell(int(target_dict['sheet_row']), headers.index(k)+1, str(v)))
                if cells: chunked_update(ws, cells)
                st.session_state[ek] = False; st.success("저장 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()
        st.button("❌ 취소", on_click=lambda: st.session_state.update({ek: False}), use_container_width=True)

@st.dialog("📖 주보 보기", width="large")
def view_bulletin_dialog(w_str, d_str, row_data):
    st.markdown(f"<h3 style='color:#0366d6; text-align:center;'>{w_str} 주보</h3>", unsafe_allow_html=True)
    img1, img2 = str(row_data.get('주보이미지1','')), str(row_data.get('주보이미지2',''))
    t1, t2 = st.tabs(["앞면", "뒷면"])
    with t1:
        if img1 and 'http' in img1: st.markdown(f"<img src='{img1.replace('&vid=1','')}' style='width:100%; border-radius:10px;'>", unsafe_allow_html=True)
    with t2:
        if img2 and 'http' in img2: st.markdown(f"<img src='{img2.replace('&vid=1','')}' style='width:100%; border-radius:10px;'>", unsafe_allow_html=True)

# --- 탭 구성 (교적부 관리가 10번 인덱스로 이동됨) ---
tabs = st.tabs(["🏫 반별명단", "🎂 생일", "🙏 기도순서", "📝 주보", "🌱 새친구", "⚙️ 행사일정", "✅ 출석체크", "📊 통계", "🧾 비용집행", "💰 교사회비", "📋 교적부 관리"])

# ==========================================
# [탭 0] 반별명단 (개선 1: 사진 출력)
# ==========================================
with tabs[0]:
    st.markdown('<a href="#top-anchor" class="fab-button">⬆ 맨 위로</a>', unsafe_allow_html=True)
    st.subheader("🏫 반별 명단 조회")
    st.info("💡 **아이콘:** 👤 일반 &nbsp; 🌱 새친구 &nbsp; 🧑‍🏫 교사 &nbsp; ✝️ 교역자 &nbsp; 🚫 비활성")
    
    all_classes = sorted([c for c in df[class_col].unique() if str(c).strip()], key=class_sort_key)
    selected_class = st.selectbox("👇 조회할 반을 선택하세요", ["반을 선택하세요"] + all_classes)
    
    if selected_class != "반을 선택하세요":
        group = df[df[class_col] == selected_class].copy()
        group['role'] = group.apply(get_role, axis=1)
        group['sort_key'] = group.apply(lambda r: 100 if r[status_col] in INACTIVE_STATUS else (get_teacher_rank(r['이름'], r.get('비고','')) if r['role'] in ['teacher','pastor'] else (60 if r[status_col]=='새친구' else 80)), axis=1)
        group = group.sort_values(by=['sort_key', '이름'])
        
        active_cnt = len(group[~group[status_col].isin(INACTIVE_STATUS)])
        st.markdown(f"<div class='class-header'>🏷️ {selected_class} ({active_cnt}명)</div>", unsafe_allow_html=True)
        
        for _, r in group.iterrows():
            s, n = r[status_col], r['이름']
            pfx = "🚫 " if s in INACTIVE_STATUS else ""
            sfx = f" ({s})" if s in INACTIVE_STATUS else ""
            label = f"{pfx}{'✝️ ' if r['role']=='pastor' else '🧑‍🏫 ' if r['role']=='teacher' else '🔴 ' if s=='새친구' else '👤 '}{n}{sfx}"
            
            with st.container():
                c1, c2 = st.columns([1, 4])
                photo_url = str(r.get('사진','')).replace('&vid=1','')
                with c1:
                    if photo_url and photo_url.startswith('http'):
                        st.markdown(f'<img src="{photo_url}" style="width:45px; height:45px; border-radius:50%; object-fit:cover; border:2px solid #ddd;">', unsafe_allow_html=True)
                    else: st.markdown("<div style='font-size:2rem; text-align:center;'>👤</div>", unsafe_allow_html=True)
                with c2:
                    if st.button(label, key=f"btn_{r['sheet_row']}", use_container_width=True): edit_student_dialog(r.to_dict())

# ==========================================
# [탭 1] 생일 (개선 3: 이름 옆 반 표시 간소화)
# ==========================================
with tabs[1]:
    st.subheader("🎂 월별 생일")
    b_map = {i: [] for i in range(1, 13)}
    bd_df = df[~df[status_col].isin(INACTIVE_STATUS)].copy()
    
    for _, r in bd_df.iterrows():
        b = str(r.get('생년월일', ''))
        if '-' in b and len(b.split('-')) == 3:
            try:
                m, d = int(b.split('-')[1]), int(b.split('-')[2])
                c_raw = str(r.get(class_col, ''))
                # 괄호 안의 선생님 이름 제거 (예: 1학년(홍길동) -> 1학년)
                c_clean = c_raw.split('(')[0].strip() if '(' in c_raw else c_raw
                b_map[m].append({"name": r['이름'], "class": c_clean, "day": d, "role": get_role(r)})
            except: pass
            
    curr_month = datetime.date.today().month
    for m in range(1, 13):
        is_curr = (m == curr_month)
        if is_curr: st.markdown('<div id="current-month"></div>', unsafe_allow_html=True)
        
        with st.expander(f"📅 {m}월 생일자", expanded=is_curr):
            if b_map[m]:
                for p in sorted(b_map[m], key=lambda x: x["day"]):
                    icn = "✝️" if p['role']=='pastor' else "🧑‍🏫" if p['role']=='teacher' else "🎈"
                    st.markdown(f"<div style='font-size:1.1rem; padding:8px 0; border-bottom:1px solid #eee;'>{icn} <b>{p['name']}</b> <span style='color:gray; font-size:0.9rem;'>({p['class']})</span><span style='float:right; color:#e65100; font-weight:bold;'>{p['day']}일</span></div>", unsafe_allow_html=True)
            else: st.markdown("<p style='text-align:center; color:#ccc; padding:10px;'>생일자가 없습니다</p>", unsafe_allow_html=True)
            
    components.html("<script>setTimeout(()=>document.getElementById('current-month')?.scrollIntoView({behavior:'smooth', block:'center'}), 500);</script>", height=0)

# ==========================================
# [탭 2] 기도순서 (개선 6: 서브 탭 UI)
# ==========================================
with tabs[2]:
    st.subheader("🙏 기도순서 관리")
    t_pv, t_pa, t_pe, t_pd = st.tabs(["👀 일정 보기", "➕ 신규 등록", "📝 내역 수정", "🚨 내역 삭제"])
    
    with t_pv:
        if not df_p.empty:
            df_p_calc = df_p.copy()
            df_p_calc['날짜_dt'] = pd.to_datetime(df_p_calc['날짜'], errors='coerce')
            st.dataframe(df_p_calc.sort_values(by='날짜_dt')[['날짜', '이름', '비고']], use_container_width=True, hide_index=True)
        else: st.info("등록된 일정이 없습니다.")
        
    with t_pa:
        with st.form("pray_add"):
            p_d = st.date_input("기도 일자").strftime("%Y-%m-%d")
            p_n = st.text_input("기도자 이름")
            p_m = st.text_input("비고")
            if st.form_submit_button("등록", type="primary"):
                ws_p.append_row([str(len(df_p)+1), p_d, p_n, p_m]); st.success("저장 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()
                
    with t_pe:
        if not df_p.empty:
            opts = ["선택"] + df_p.apply(lambda r: f"[{r.get('날짜','')}] {r.get('이름','')}", axis=1).tolist()
            sel = st.selectbox("수정할 대상", range(len(opts)), format_func=lambda x: opts[x])
            if sel > 0:
                with st.form("pray_edit"):
                    e_n = st.text_input("이름 수정", df_p.iloc[sel-1].get('이름',''))
                    if st.form_submit_button("수정", type="primary"):
                        chunked_update(ws_p, [gspread.Cell(int(df_p.iloc[sel-1]['sheet_row']), 3, e_n)])
                        st.success("수정 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

    with t_pd:
        if not df_p.empty:
            opts = ["선택"] + df_p.apply(lambda r: f"[{r.get('날짜','')}] {r.get('이름','')}", axis=1).tolist()
            sel = st.selectbox("삭제할 대상", range(len(opts)), format_func=lambda x: opts[x])
            if st.button("🚨 삭제 실행", type="primary") and sel > 0:
                ws_p.delete_rows(int(df_p.iloc[sel-1]['sheet_row'])); st.success("삭제 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 3] 주보 (개선 6: 서브 탭 UI)
# ==========================================
with tabs[3]:
    st.subheader("📝 주보 관리")
    t_bv, t_be = st.tabs(["👀 전체 보기", "⚙️ 설정/업로드"])
    curr_week = datetime.date.today().isocalendar()[1]
    
    with t_bv:
        cols = st.columns(2)
        for i in range(1, 53):
            w_str = f"{i}주"
            match = df_b[df_b['주차'] == w_str] if not df_b.empty else pd.DataFrame()
            is_ex = not match.empty and str(match.iloc[0].get('주보이미지1','')).startswith('http')
            
            with cols[(i-1) % 2]:
                if i == curr_week: st.markdown('<div id="c-week"></div>', unsafe_allow_html=True)
                if st.button(f"{'✅' if is_ex else '⬜'} {w_str}", key=f"bv_{i}", type="primary" if is_ex else "secondary"):
                    if is_ex: view_bulletin_dialog(w_str, "", match.iloc[0])
                    else: st.warning("미등록")
    
    with t_be:
        cols = st.columns(2)
        for i in range(1, 53):
            with cols[(i-1) % 2]:
                if st.button(f"⚙️ {i}주 설정", key=f"be_{i}"):
                    pass
    components.html("<script>setTimeout(()=>document.getElementById('c-week')?.scrollIntoView({behavior:'smooth', block:'center'}), 500);</script>", height=0)

# ==========================================
# [탭 4] 새친구
# ==========================================
with tabs[4]:
    st.subheader("🌱 최근 등록 새친구")
    news = df[df[status_col] == '새친구'].copy()
    if not news.empty: st.dataframe(news[['이름', class_col, '연락처', '비고']], use_container_width=True, hide_index=True)
    else: st.info("등록된 새친구가 없습니다.")

# ==========================================
# [탭 5] 행사 기록 관리 (개선 4 & 6: PDF 다운로드 및 탭 UI)
# ==========================================
with tabs[5]:
    st.markdown('<a href="#top-anchor" class="fab-button">⬆ 맨 위로</a>', unsafe_allow_html=True)
    st.subheader("⚙️ 행사일정 기록 관리")
    
    t_ev_view, t_ev_add, t_ev_edit, t_ev_del = st.tabs(["📂 보기 및 PDF다운로드", "➕ 행사 등록", "📝 내용 수정", "🚨 삭제"])
    
    def format_event(row_id):
        if row_id == "행사 선택": return "행사 선택"
        match = df_act[df_act['sheet_row'] == row_id]
        if not match.empty: return f"{match.iloc[0].get('날짜','')} | {match.iloc[0].get('활동명','')}"
        return "알 수 없음"

    with t_ev_view:
        if not df_act.empty:
            view_act_df = df_act.copy()
            view_act_df['sort_date'] = pd.to_datetime(view_act_df['날짜'], errors='coerce')
            view_act_df = view_act_df.sort_values(by=['sort_date', 'sheet_row'], ascending=[False, False])
            
            # 개선 4: 맨 앞장은 요약표, 그 다음부터 1장당 행사 1개씩, 사진은 약간 작게
            html_act_report = """
            <html>
            <head>
                <meta charset="utf-8">
                <title>행사일정 보고서</title>
                <style>
                    body { font-family: 'Malgun Gothic', sans-serif; margin: 20px; color: #333; }
                    h1 { text-align: center; color: #0366d6; margin-bottom: 20px; }
                    table { width: 100%; border-collapse: collapse; margin-bottom: 30px; page-break-after: always; }
                    th { background-color: #f1f8ff; padding: 10px; border: 1px solid #ddd; font-size: 14px; }
                    td { padding: 10px; border: 1px solid #ddd; font-size: 13px; text-align: center; }
                    .event-page { page-break-after: always; margin-top: 20px; padding: 10px; }
                    .event-title { font-size: 20px; color: #0366d6; border-bottom: 2px solid #0366d6; padding-bottom: 5px; margin-bottom: 15px; }
                    .event-desc { background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; line-height: 1.6; }
                    .img-grid { display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; }
                    /* 사진을 조금 작게 표시하기 위한 CSS */
                    .img-grid img { max-width: 250px; height: auto; border-radius: 5px; border: 1px solid #ddd; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                    @media print { body { margin: 0; } }
                </style>
            </head>
            <body>
                <h1>슈팅스타 유년부 행사일정 요약 보고서</h1>
                
                <h2>📊 1. 행사 전체 요약표</h2>
                <table>
                    <thead>
                        <tr><th>일자</th><th>행사명</th><th>세부 내용 요약</th></tr>
                    </thead>
                    <tbody>
            """
            for _, row in view_act_df.iterrows():
                summary_text = str(row.get('세부내용',''))[:40] + ("..." if len(str(row.get('세부내용',''))) > 40 else "")
                html_act_report += f"<tr><td>{row.get('날짜','')}</td><td><strong>{row.get('활동명','')}</strong></td><td style='text-align:left;'>{summary_text}</td></tr>"
            html_act_report += "</tbody></table>"
            
            for _, row in view_act_df.iterrows():
                html_act_report += f"<div class='event-page'><div class='event-title'>📅 {row.get('활동명','')} ({row.get('날짜','')})</div>"
                html_act_report += f"<div class='event-desc'><strong>📝 상세 내용:</strong><br>{str(row.get('세부내용','')).replace(chr(10), '<br>')}</div>"
                
                valid_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                if valid_urls:
                    html_act_report += "<h3>📸 첨부 사진</h3><div class='img-grid'>"
                    for media_url in valid_urls:
                        clean_url = str(media_url).replace("&vid=1", "").replace("?vid=1", "")
                        if 'vid=1' not in str(media_url).lower() and not any(ext in str(media_url).lower() for ext in ['.mp4', '.mov', '.avi']):
                            html_act_report += f"<img src='{clean_url}'>"
                    html_act_report += "</div>"
                html_act_report += "</div>"
            html_act_report += "</body></html>"
            
            st.download_button(
                label="📄 행사일정 보고서 다운로드 (HTML ➔ 인쇄 PDF)",
                data=html_act_report.encode("utf-8"),
                file_name=f"유년부_행사일정_{datetime.date.today()}.html",
                mime="text/html",
                use_container_width=True,
                type="primary"
            )
            st.info("💡 다운로드한 HTML 문서를 열고 브라우저에서 'PDF로 저장(인쇄)' 하시면 1행사 당 1장씩 깔끔하게 출력됩니다.")
            st.divider()
            
            for _, row in view_act_df.iterrows():
                with st.expander(f"📅 {row.get('날짜', '')} | {row.get('활동명', '')}"):
                    st.write(f"**내용:** {row.get('세부내용', '')}")
                    if str(row.get('공지사항', '')).strip(): st.markdown(f"**📢 공지:** <span style='color: #d32f2f;'>{row.get('공지사항', '')}</span>", unsafe_allow_html=True)
                    
                    valid_urls = [row.get(f'사진{i}', "") for i in range(1, 16) if str(row.get(f'사진{i}', "")).startswith('http')]
                    if valid_urls:
                        for media_url in valid_urls:
                            clean_url = str(media_url).replace("&vid=1", "").replace("?vid=1", "")
                            st.markdown(f"<img src='{clean_url}' style='width:100%; border-radius:8px; margin-bottom:10px;'>", unsafe_allow_html=True)
                                
    with t_ev_add:
        with st.form("new_e"):
            a_d = st.date_input("행사 날짜")
            a_t = st.text_input("행사명")
            a_c = st.text_area("세부 내용")
            a_n = st.text_input("공지사항")
            a_f = st.file_uploader("사진 (최대15개)", accept_multiple_files=True, type=['png','jpg','jpeg'])
            if st.form_submit_button("저장", type="primary"):
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
                    if "등록일" in h_map: new_row[h_map["등록일"]] = str(datetime.datetime.now())
                    for k in range(1, 16):
                        if f"사진{k}" in h_map: new_row[h_map[f"사진{k}"]] = urls[k-1]
                    ws_act.append_row(new_row)
                    st.success("등록 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

    with t_ev_edit:
        if not df_act.empty:
            opts = ["행사 선택"] + df_act['sheet_row'].tolist()
            sel = st.selectbox("수정할 행사 선택", opts, format_func=format_event)
            if sel != "행사 선택":
                tgt = df_act[df_act['sheet_row'] == int(sel)].iloc[0]
                with st.form("edit_ev"):
                    e_d = st.date_input("날짜", value=parse_date_safe(tgt.get('날짜', '')))
                    e_t = st.text_input("행사명", value=tgt.get('활동명', ''))
                    e_c = st.text_area("내용", value=tgt.get('세부내용', ''))
                    if st.form_submit_button("텍스트 정보만 수정", type="primary"):
                        chunked_update(ws_act, [gspread.Cell(int(sel), 1, str(e_d)), gspread.Cell(int(sel), 2, e_t), gspread.Cell(int(sel), 3, e_c)])
                        st.success("수정 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

    with t_ev_del:
        if not df_act.empty:
            opts = ["행사 선택"] + df_act['sheet_row'].tolist()
            sel = st.selectbox("삭제할 행사 선택", opts, format_func=format_event)
            if st.button("🚨 삭제 실행", type="primary") and sel != "행사 선택":
                ws_act.delete_rows(int(sel)); st.success("삭제됨!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 6] 출석체크
# ==========================================
with tabs[6]:
    st.subheader("📅 주간 출석 체크")
    with st.container(border=True):
        sel_w_raw = st.selectbox("출석 주차 선택", [f"{i}주" for i in range(1, 53)] + ["✏️ 직접입력"], index=max(0, min(51, datetime.date.today().isocalendar()[1] - 1)))
        if sel_w_raw == "✏️ 직접입력": 
            tgt_date = st.date_input("날짜 선택", datetime.date.today())
            sel_w = tgt_date.strftime("%Y-%m-%d")
        else: 
            sel_w = sel_w_raw
            tgt_date = start_date + datetime.timedelta(days=(int(sel_w_raw.replace("주", ""))-1)*7)
            
        all_classes_list = sorted([str(c) for c in df[class_col].unique() if str(c).strip()], key=class_sort_key)
        sel_class = st.selectbox("조회할 반 선택", ["반을 선택하세요", "전체 명단 불러오기"] + all_classes_list)

    if sel_class != "반을 선택하세요":
        att_df = df[df.apply(lambda r: is_enrolled_at_date(r, tgt_date), axis=1)].copy()
        if sel_class != "전체 명단 불러오기": att_df = att_df[att_df[class_col] == sel_class]
        if sel_w not in att_df.columns: att_df[sel_w] = ""
        
        with st.form("att_toggle"):
            new_att = {}
            grp = att_df.sort_values(by=['이름']).groupby(class_col)
            for c_name in sorted(grp.groups.keys(), key=class_sort_key):
                st.markdown(f"<div class='class-header'>🏷️ {c_name}</div>", unsafe_allow_html=True)
                cols = st.columns(2)
                for i, (idx, row) in enumerate(grp.get_group(c_name).iterrows()):
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    s_label = "👤" if row[status_col]=='일반' else ("🔴" if row[status_col]=='새친구' else "🧑‍🏫")
                    new_att[row['sheet_row']] = cols[i%2].toggle(f"{s_label} {row['이름']}", value=is_on)
            
            st.divider()
            guest_in = st.number_input("🎉 새친구/추가 방문 인원", min_value=0, value=0)
            if st.form_submit_button("💾 출석 데이터 저장", type="primary", use_container_width=True):
                with st.spinner("기록 중..."):
                    tc = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                    if sel_w not in headers: 
                        try: ws.update_cell(1, tc, sel_w)
                        except: ws.add_cols(5); ws.update_cell(1, tc, sel_w)
                    
                    cells = [gspread.Cell(int(r), tc, "1" if v else "") for r, v in new_att.items()]
                    if cells: chunked_update(ws, cells)
                    st.success("저장 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 7] 통계
# ==========================================
with tabs[7]:
    st.subheader("📊 주간 통계 조회")
    if not df_stat.empty:
        st.dataframe(df_stat, use_container_width=True, hide_index=True)

# ==========================================
# [탭 8] 비용집행관리 (개선 5 & 6: CSV 리셋 순번 및 서브 탭 UI)
# ==========================================
with tabs[8]:
    if not st.session_state['chongmu_auth']:
        with st.container(border=True):
            cpwd = st.text_input("총무 권한 비밀번호", type="password")
            if st.button("인증", type="primary", use_container_width=True):
                if cpwd == st.secrets.get("chongmu_password", "admin1234"): st.session_state['chongmu_auth'] = True; st.rerun()
                else: st.error("오류")
    else:
        st.subheader("🧾 비용집행관리")
        t_ex_v, t_ex_a, t_ex_e, t_ex_d = st.tabs(["👀 내역 조회/다운로드", "➕ 신규 등록", "📝 내역 수정", "🚨 내역 삭제"])
        
        with t_ex_v:
            if not df_r.empty:
                df_r_calc = df_r.copy()
                df_r_calc['날짜_dt'] = pd.to_datetime(df_r_calc['날짜'], errors='coerce')
                
                d_range = st.date_input("조회 기간 설정", [df_r_calc['날짜_dt'].min().date() if pd.notnull(df_r_calc['날짜_dt'].min()) else datetime.date.today(), datetime.date.today()])
                if len(d_range) == 2: s_d, e_d = d_range
                else: s_d, e_d = d_range[0], d_range[0]
                
                filt = df_r_calc[(df_r_calc['날짜_dt'].dt.date >= s_d) & (df_r_calc['날짜_dt'].dt.date <= e_d)].copy()
                
                if not filt.empty:
                    st.dataframe(filt[['번호', '날짜', '구매처', '내용', '비용']], use_container_width=True, hide_index=True)
                    
                    # 개선 5: 기간 설정 후 CSV 다운로드 시 순번이 1번부터 차례대로 시작되도록 정렬
                    csv_df = filt[['번호', '날짜', '구매처', '내용', '비용', '비고']].copy()
                    csv_df['번호'] = range(1, len(csv_df) + 1)
                    
                    st.download_button(
                        label="📊 엑셀(CSV) 다운로드",
                        data=csv_df.to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"비용집행내역_{s_d}_{e_d}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        type="primary"
                    )

        with t_ex_a:
            with st.form("new_receipt"):
                r_d = st.date_input("결제 날짜").strftime("%Y-%m-%d")
                r_v = st.text_input("구매처 (상호)")
                r_c = st.text_input("구매 내용")
                r_cost = st.number_input("지출 비용(원)", step=1000)
                r_m = st.text_input("비고")
                r_p = st.file_uploader("영수증 사진 첨부", type=['png','jpg'])
                if st.form_submit_button("등록 완료", type="primary", use_container_width=True):
                    p_url = upload_photo(r_p, f"영수증_{r_v}") if r_p else ""
                    ws_r.append_row([len(df_r)+1, r_d, r_v, r_c, r_cost, r_m, p_url])
                    st.success("내역이 등록되었습니다!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

        with t_ex_e:
            if not df_r.empty:
                opts = ["선택"] + df_r.apply(lambda r: f"No.{r.get('번호','')} | {r.get('구매처','')}", axis=1).tolist()
                sel = st.selectbox("수정 대상 선택", range(len(opts)), format_func=lambda x: opts[x])
                if sel > 0:
                    with st.form("edit_receipt"):
                        e_cost = st.number_input("비용금액 재설정", value=parse_int_safe(df_r.iloc[sel-1].get('비용',0)), step=1000)
                        if st.form_submit_button("금액 수정", type="primary", use_container_width=True):
                            chunked_update(ws_r, [gspread.Cell(int(df_r.iloc[sel-1]['sheet_row']), 5, str(e_cost))])
                            st.success("비용이 수정되었습니다!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

        with t_ex_d:
            if not df_r.empty:
                opts = ["선택"] + df_r.apply(lambda r: f"No.{r.get('번호','')} | {r.get('구매처','')}", axis=1).tolist()
                sel = st.selectbox("삭제 대상 선택", range(len(opts)), format_func=lambda x: opts[x])
                if st.button("🚨 해당 내역 삭제", type="primary", use_container_width=True) and sel > 0:
                    ws_r.delete_rows(int(df_r.iloc[sel-1]['sheet_row'])); st.success("삭제되었습니다!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 9] 교사회비 (개선 6: 서브 탭 UI)
# ==========================================
with tabs[9]:
    if st.session_state['chongmu_auth']:
        st.subheader("💰 교사 회비 장부 관리")
        t_d_v, t_d_i, t_d_o = st.tabs(["👀 장부 조회", "📥 수입금 등록", "📤 지출금 등록"])
        
        with t_d_v:
            if not df_in.empty: st.markdown("##### 📥 수입 리스트"); st.dataframe(df_in[['날짜', '입금자명', '입금액']], hide_index=True, use_container_width=True)
            if not df_out.empty: st.markdown("##### 📤 지출 리스트"); st.dataframe(df_out[['날짜', '내용', '지출액']], hide_index=True, use_container_width=True)
            
        with t_d_i:
            with st.form("new_in"):
                d = st.date_input("입금 일자").strftime("%Y-%m-%d"); n = st.text_input("입금자명"); a = st.number_input("입금액(원)", step=1000)
                if st.form_submit_button("수입 등록", type="primary", use_container_width=True):
                    ws_in.append_row([len(df_in)+1, d, n, a, ""]); st.success("등록 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()
                    
        with t_d_o:
            with st.form("new_out"):
                d = st.date_input("지출 일자").strftime("%Y-%m-%d"); c = st.text_input("지출 내용"); a = st.number_input("지출액(원)", step=1000)
                if st.form_submit_button("지출 등록", type="primary", use_container_width=True):
                    ws_out.append_row([len(df_out)+1, d, c, a, "", ""]); st.success("등록 완료!"); time.sleep(1); fetch_sheet_data.clear(); st.rerun()

# ==========================================
# [탭 10] 교적부 관리 (개선 2 & 6: 위치 맨 뒤로 이동 및 서브 탭 UI)
# ==========================================
with tabs[10]:
    st.subheader("📋 교적부 관리")
    
    t_m_v, t_m_e, t_m_a = st.tabs(["👀 전체 명단 조회", "📝 인원 정보 수정/비활성", "➕ 신규 인원 등록"])
    
    with t_m_v:
        df_display = df.copy()
        if st.session_state['privacy_mode']:
            for cp in ['생년월일', '연락처', '주소', '부모(아빠/엄마)']:
                if cp in df_display.columns: df_display[cp] = "🔒 [보호됨]"
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
    with t_m_e:
        opts = ["인원 선택"] + df.apply(lambda r: f"{r['이름']} | {r.get(class_col,'')} ({r.get(status_col,'일반')})", axis=1).tolist()
        sel = st.selectbox("수정할 인원을 검색하거나 선택하세요", range(len(opts)), format_func=lambda x: opts[x])
        if sel > 0: edit_student_dialog(df.iloc[sel-1].to_dict())
            
    with t_m_a:
        with st.form("add_member"):
            n_name = st.text_input("이름 (필수입력)")
            n_class = st.text_input("학년(담임) (필수입력)")
            n_status = st.selectbox("구분", ALL_STATUS_OPTS, index=0)
            n_reg = st.date_input("등록 일자", value=datetime.date.today()).strftime("%Y-%m-%d")
            n_photo = st.file_uploader("프로필 사진 첨부", type=['png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("✨ 인원 신규 등록하기", type="primary", use_container_width=True):
                if n_name and n_class:
                    p_url = upload_photo(n_photo, n_name)
                    new_row = [""] * len(headers)
                    h_map = {str(h): i for i, h in enumerate(headers)}
                    if '이름' in h_map: new_row[h_map['이름']] = n_name
                    if class_col in h_map: new_row[h_map[class_col]] = n_class
                    if '생년월일' in h_map: new_row[h_map['생년월일']] = "2015-01-01"
                    if '등록일' in h_map: new_row[h_map['등록일']] = n_reg
                    if '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                    elif '상태' in h_map: new_row[h_map['상태']] = n_status
                    if '사진' in h_map: new_row[h_map['사진']] = p_url
                    
                    ws.append_row(new_row)
                    st.success("✅ 교적부에 신규 인원이 성공적으로 등록되었습니다!"); time.sleep(1.5); fetch_sheet_data.clear(); st.rerun()
                else:
                    st.warning("⚠️ 이름과 반 정보는 필수 입력 항목입니다.")
