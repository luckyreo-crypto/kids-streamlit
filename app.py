import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 스타일 ---
st.set_page_config(page_title="유년부 통합 관리 v24.3", page_icon="🌱", layout="wide")

st.markdown("""
    <style>
    .attendance-box { border: 1px solid #ddd; padding: 10px; border-radius: 8px; background-color: #f9f9f9; margin-bottom: 10px; text-align: center; }
    .stCheckbox { transform: scale(1.2); }
    .month-container { min-height: 200px; border: 1px solid #eee; padding: 10px; border-radius: 10px; background: white; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

client = init_connection()
sheet_id = "1UfoeHFWPoJ3bnkjLJyIwEIURyeKa82i7SrMXK35tq3Q"

def get_all_data():
    try:
        sh = client.open_by_key(sheet_id)
        # 1. 교적부 로드
        ws_m = sh.worksheet("교적부")
        vals = ws_m.get_all_values()
        headers = vals[0]
        df_m = pd.DataFrame(vals[1:], columns=headers) if len(vals) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        if '상태' in df_m.columns and '학교상태' not in df_m.columns:
            df_m.rename(columns={'상태': '학교상태'}, inplace=True)
            headers = [h if h != '상태' else '학교상태' for h in headers]
            
        # 2. 활동간식 로드
        try:
            ws_a = sh.worksheet("활동간식")
            a_vals = ws_a.get_all_values()
        except:
            ws_a = sh.add_worksheet(title="활동간식", rows="500", cols="10")
            ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
            a_vals = ws_a.get_all_values()
            
        df_a = pd.DataFrame(a_vals[1:], columns=a_vals[0]) if len(a_vals) > 1 else pd.DataFrame()
        df_a['sheet_row'] = range(2, len(df_a) + 2)
        
        return ws_m, df_m, headers, ws_a, df_a
    except Exception as e:
        st.error(f"데이터 연동 에러: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame()

ws, df, headers, ws_act, df_act = get_all_data()

# --- 3. 공통 함수 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}).json()
        return res.get("fileUrl", "")
    except: return ""

class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')

# --- 4. 주차 및 날짜 생성 ---
start_date = datetime.date(2026, 1, 4)
weeks_list = []
week_display_map = {}
for i in range(1, 53):
    w_name = f"{i}주"
    w_disp = f"{w_name} ({start_date.strftime('%m/%d')})"
    weeks_list.append(w_name)
    week_display_map[w_name] = w_disp
    start_date += datetime.timedelta(days=7)

# --- 5. 탭 구성 ---
tabs = st.tabs(["📋 교적부", "✅ 출석체크", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사"])

if df.empty:
    st.warning("데이터를 불러오지 못했습니다. 구글 시트를 확인해주세요.")
    st.stop()

# ==========================================
# [탭 1] 교적부 관리 (입력 패턴 가이드 강화)
# ==========================================
with tabs[0]:
    st.subheader("📋 교적부 통합 데이터베이스")
    manage_mode = st.radio("작업 모드 선택", ["👀 전체 명단 보기", "📝 개별 상세 조회 및 수정/삭제", "➕ 신규 인원 추가"], horizontal=True)
    
    req_cols = ['학년(담임)', '이름', '사진', '생년월일', '주소', '부모(아빠/엄마)', '연락처', '학교상태', '비고', '전도자']
    available_cols = [c for c in req_cols if c in df.columns]

    st.markdown("---")

    if manage_mode == "👀 전체 명단 보기":
        st.write(f"현재 등록된 총 인원: **{len(df)}명**")
        st.dataframe(df[available_cols], use_container_width=True, hide_index=True, column_config={"사진": st.column_config.ImageColumn("사진")})

    elif manage_mode == "📝 개별 상세 조회 및 수정/삭제":
        search_list = df.apply(lambda r: f"{r['이름']} | {r[class_col]}", axis=1).tolist()
        search_options = ["학생을 선택하세요"] + search_list
        selected_index = st.selectbox("수정/삭제할 학생 선택", range(len(search_options)), format_func=lambda x: search_options[x])
        
        if selected_index > 0:
            target_data = df.iloc[selected_index - 1]
            sheet_row = target_data['sheet_row']
            st.markdown(f"#### 👤 {target_data['이름']} 상세 프로필")
            
            col_img, col_form = st.columns([1, 2])
            with col_img:
                photo_url = target_data.get('사진', '')
                if isinstance(photo_url, str) and photo_url.startswith('http'): st.image(photo_url, use_container_width=True)
                else: st.info("등록된 사진이 없습니다.")
                    
            with col_form:
                with st.form("edit_member_form_safe"):
                    # 기존 형식 유지 가이드 적용
                    e_class = st.text_input("학년(담임)", value=target_data.get('학년(담임)', ''), placeholder="예: 1-1(권은주)")
                    e_name = st.text_input("이름", value=target_data.get('이름', ''))
                    e_birth = st.text_input("생년월일", value=target_data.get('생년월일', ''), placeholder="예: 19.02.26")
                    e_addr = st.text_input("주소", value=target_data.get('주소', ''))
                    e_parents = st.text_input("부모(아빠/엄마)", value=target_data.get('부모(아빠/엄마)', ''))
                    e_phone = st.text_input("연락처", value=target_data.get('연락처', ''), placeholder="예: 010-1234-5678")
                    
                    status_opts = ["일반", "새친구", "이사", "교사"]
                    curr_status = target_data.get('학교상태', '일반')
                    e_status = st.selectbox("학교상태", status_opts, index=status_opts.index(curr_status) if curr_status in status_opts else 0)
                    e_memo = st.text_input("비고", value=target_data.get('비고', ''))
                    e_evangelist = st.text_input("전도자", value=target_data.get('전도자', ''))
                    e_photo = st.file_uploader("사진 변경 (선택)", type=["jpg", "png", "jpeg"])
                    
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("💾 정보 수정", use_container_width=True):
                        with st.spinner("정보 업데이트 중..."):
                            new_photo_url = photo_url
                            if e_photo: new_photo_url = upload_photo(e_photo, e_name)
                            update_map = {'학년(담임)': e_class, '이름': e_name, '생년월일': e_birth, '주소': e_addr, '부모(아빠/엄마)': e_parents, '연락처': e_phone, '학교상태': e_status, '비고': e_memo, '전도자': e_evangelist, '사진': new_photo_url}
                            for col_name, new_val in update_map.items():
                                if col_name in headers: ws.update_cell(sheet_row, headers.index(col_name) + 1, str(new_val))
                            st.success("수정이 완료되었습니다!"); st.rerun()
                            
                    if c2.form_submit_button("🚨 완전 삭제", use_container_width=True):
                        ws.delete_rows(int(sheet_row))
                        st.success("삭제되었습니다."); st.rerun()

    elif manage_mode == "➕ 신규 인원 추가":
        st.markdown("#### ✨ 새로운 인원 등록")
        with st.form("add_member_form_v24_3", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                # ★ 핵심: 기존 패턴 가이드(Placeholder) 적용
                n_class = st.text_input("학년(담임) (필수)", placeholder="예: 1-1(권은주)")
                n_name = st.text_input("이름 (필수)")
                n_birth = st.text_input("생년월일", placeholder="예: 19.02.26")
                n_parents = st.text_input("부모(아빠/엄마)")
                n_phone = st.text_input("연락처", placeholder="예: 010-1234-5678")
            with col2:
                n_addr = st.text_input("주소")
                n_status = st.selectbox("학교상태", ["일반", "새친구", "이사", "교사"], index=1)
                n_memo = st.text_input("비고 (등록일 등)")
                n_evangelist = st.text_input("전도자")
                n_photo = st.file_uploader("사진 첨부", type=["jpg", "png", "jpeg"])
                
            if st.form_submit_button("✨ 교적부에 등록하기", use_container_width=True):
                if not n_name or not n_class:
                    st.error("이름과 학년(담임)은 필수입니다.")
                else:
                    with st.spinner("등록 중..."):
                        photo_url = upload_photo(n_photo, n_name)
                        new_row = [""] * len(headers)
                        h_map = {str(h).strip(): i for i, h in enumerate(headers)}
                        if '학년(담임)' in h_map: new_row[h_map['학년(담임)']] = n_class
                        if '이름' in h_map: new_row[h_map['이름']] = n_name
                        if '생년월일' in h_map: new_row[h_map['생년월일']] = n_birth
                        if '주소' in h_map: new_row[h_map['주소']] = n_addr
                        if '부모(아빠/엄마)' in h_map: new_row[h_map['부모(아빠/엄마)']] = n_parents
                        if '연락처' in h_map: new_row[h_map['연락처']] = n_phone
                        if '학교상태' in h_map: new_row[h_map['학교상태']] = n_status
                        if '비고' in h_map: new_row[h_map['비고']] = n_memo
                        if '전도자' in h_map: new_row[h_map['전도자']] = n_evangelist
                        if '사진' in h_map: new_row[h_map['사진']] = photo_url
                        ws.append_row(new_row)
                        st.success(f"{n_name} 학생이 성공적으로 등록되었습니다!"); st.rerun()
# ==========================================
# [탭 2] 출석체크 (기존 기능 유지)
# ==========================================
with tabs[1]:
    st.subheader("📅 주차별 출석 관리")
    
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    sel_w = st.selectbox("날짜 주차 선택", weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map[x])
    
    classes = ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()])
    sel_class = st.selectbox("반 필터", classes, key="att_class_sel")

    att_df = df[df['학교상태' if '학교상태' in df.columns else '상태'] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    att_df = att_df.sort_values(by=[class_col, '이름'])

    with st.form("quick_att_form_v24"):
        cols = st.columns(3)
        new_att_values = {}
        for i, (idx, row) in enumerate(att_df.iterrows()):
            with cols[i % 3]:
                is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                label = f"{row['이름']}({row[class_col]})"
                new_att_values[row['sheet_row']] = st.checkbox(label, value=is_on, key=f"att_chk_{row['sheet_row']}")
        
        if st.form_submit_button("💾 현재 주차 출석 저장", use_container_width=True):
            with st.spinner("저장 중..."):
                if sel_w not in headers:
                    ws.update_cell(1, len(headers)+1, sel_w)
                col_idx = headers.index(sel_w) + 1 if sel_w in headers else len(headers)+1
                for r_idx, val in new_att_values.items():
                    ws.update_cell(r_idx, col_idx, "1" if val else "")
                st.success("저장 완료!")
                st.rerun()

# ==========================================
# [탭 3] 반편성 현황 (기존 기능 유지)
# ==========================================
with tabs[2]:
    st.subheader("🏫 반별 명단 현황")
    if not df.empty:
        status_col = '학교상태' if '학교상태' in df.columns else '상태'
        grouped = df[df[status_col] != '이사'].groupby(class_col)
        cols = st.columns(3)
        for i, (name, group) in enumerate(grouped):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{name}** ({len(group)}명)")
                    names = [f"🔴{n}" if s == '새친구' else n for n, s in zip(group['이름'], group[status_col])]
                    st.write(", ".join(names))

# ==========================================
# [탭 4] 월별 생일표 (기존 기능 유지)
# ==========================================
with tabs[3]:
    st.subheader("🎂 월별 생일 명단")
    if '생년월일' in df.columns:
        b_map = {str(i): [] for i in range(1, 13)}
        for _, r in df.iterrows():
            b = str(r['생년월일'])
            if len(b.split('.')) >= 3:
                try:
                    m = str(int(b.split('.')[1]))
                    d = str(int(b.split('.')[2]))
                    b_map[m].append(f"**{r['이름']}** ({r[class_col]}) - {d}일")
                except: pass
        
        cols = st.columns(3)
        for i in range(1, 13):
            with cols[(i-1)%3]:
                st.markdown(f"""<div class="month-container">
                    <p style="font-size: 1.2rem; font-weight: bold; color: #ff4b4b;">📅 {i}월</p>
                    <hr style="margin: 10px 0;">
                """, unsafe_allow_html=True)
                if b_map[str(i)]:
                    for p in b_map[str(i)]: st.write(p)
                else: st.caption("생일자 없음")
                st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# [탭 5] 새친구 목록 (기존 기능 유지)
# ==========================================
with tabs[4]:
    st.subheader("🌱 최근 등록 새친구")
    status_col = '학교상태' if '학교상태' in df.columns else '상태'
    news = df[df[status_col] == '새친구']
    if not news.empty:
        st.dataframe(news[available_cols], use_container_width=True, hide_index=True)
    else: st.info("새친구가 없습니다.")

# ==========================================
# [탭 6] 행사 (기존 기능 유지)
# ==========================================
with tabs[5]:
    st.subheader("⚙️ 행사 및 활동 관리")
    
    st.write("📂 **활동 내역 수정 및 관리**")
    if not df_act.empty:
        act_headers = ["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4"]
        valid_act_cols = [c for c in act_headers if c in df_act.columns]
        
        edited_events = st.data_editor(
            df_act[valid_act_cols],
            use_container_width=True,
            hide_index=True,
            key="events_editor"
        )
        
        if st.button("📝 행사 내용 변경사항 저장"):
            with st.spinner("수정 중..."):
                changed_acts = 0
                for r_idx in range(len(edited_events)):
                    for c_name in valid_act_cols:
                        o_v = str(df_act.iloc[r_idx][c_name]).strip()
                        n_v = str(edited_events.iloc[r_idx][c_name]).strip()
                        if o_v != n_v:
                            s_row = df_act.iloc[r_idx]['sheet_row']
                            act_sh_headers = ws_act.row_values(1)
                            s_col = act_sh_headers.index(c_name) + 1
                            ws_act.update_cell(s_row, s_col, n_v)
                            changed_acts += 1
                st.success(f"{changed_acts}개의 행사 정보가 업데이트되었습니다!")
                st.rerun()
    
    st.markdown("---")
    with st.expander("➕ 신규 활동 기록 추가"):
        with st.form("act_form_new"):
            d = st.date_input("날짜", datetime.date.today())
            t = st.text_input("활동명")
            desc = st.text_area("세부내용")
            note = st.text_area("공지사항")
            files = st.file_uploader("사진(최대 4장)", accept_multiple_files=True)
            if st.form_submit_button("기록 저장"):
                urls = ["", "", "", ""]
                for i, f in enumerate(files[:4]):
                    urls[i] = upload_photo(f, f"act_{t}_{i}")
                ws_act.append_row([str(d), t, desc, note, urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())])
                st.success("성공적으로 저장되었습니다!")
                st.rerun()
