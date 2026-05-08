import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 스타일 ---
st.set_page_config(page_title="유년부 통합 관리 v24.4", page_icon="🌱", layout="wide")

st.markdown("""
    <style>
    .stat-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; }
    .att-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 10px; background-color: white; }
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
        ws_m = sh.worksheet("교적부")
        vals = ws_m.get_all_values()
        headers = vals[0]
        df_m = pd.DataFrame(vals[1:], columns=headers) if len(vals) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        if '상태' in df_m.columns and '학교상태' not in df_m.columns:
            df_m.rename(columns={'상태': '학교상태'}, inplace=True)
            headers = [h if h != '상태' else '학교상태' for h in headers]
            
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
weeks_list = [f"{i}주" for i in range(1, 53)]
week_display_map = {f"{i}주": f"{i}주 ({ (start_date + datetime.timedelta(days=(i-1)*7)).strftime('%m/%d') })" for i in range(1, 53)}

# --- 5. 탭 구성 ---
tabs = st.tabs(["📋 교적부", "✅ 출석체크", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사"])

# ==========================================
# [탭 2] 출석체크 (관리자님이 요청하신 어제의 그 직관적 기능)
# ==========================================
with tabs[1]:
    st.subheader("📅 주일 출석 통합 관리")
    
    # 1. 주차 및 필터 설정
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    col1, col2 = st.columns(2)
    with col1:
        sel_w = st.selectbox("기록 주차 선택", weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map[x])
    with col2:
        classes = ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()])
        sel_class = st.selectbox("반 필터 (모바일은 반별 선택 권장)", classes)

    # 2. 이번 주 통계 및 기타 인원 입력
    att_df = df[df['학교상태'] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    
    # 시트에 해당 주차 열이 없는 경우 대비
    if sel_w not in att_df.columns:
        att_df[sel_w] = ""

    total_reg = len(att_df)
    present_count = len(att_df[att_df[sel_w].astype(str).str.strip() == "1"])
    
    st.markdown("---")
    c_stat1, c_stat2, c_stat3, c_stat4 = st.columns(4)
    with c_stat1:
        st.metric("대상 인원", f"{total_reg}명")
    with c_stat2:
        st.metric("현재 출석", f"{present_count}명")
    with c_stat3:
        guest_count = st.number_input("기타 인원(방문 등)", min_value=0, value=0, step=1)
    with c_stat4:
        st.metric("총 합계", f"{present_count + guest_count}명", delta=f"기타 {guest_count}포함")

    # 3. 직관적인 모드 출석체크 (큼직한 카드 UI)
    st.write(f"### 📱 {week_display_map[sel_w]} 모바일 출석체크")
    with st.form("att_form_v24_4"):
        # 3열로 배치하여 모바일/PC 모두 대응
        cols = st.columns(3)
        new_att_status = {}
        
        for i, (idx, row) in enumerate(att_df.sort_values(by=[class_col, '이름']).iterrows()):
            with cols[i % 3]:
                is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                label = f"{row['이름']} ({row[class_col]})"
                if row.get('학교상태') == '새친구': label = "🌱 " + label
                new_att_status[row['sheet_row']] = st.checkbox(label, value=is_on, key=f"att_chk_{row['sheet_row']}")
        
        if st.form_submit_button("💾 선택한 주차 출석 저장하기", use_container_width=True):
            with st.spinner("구글 시트에 저장 중..."):
                target_col_idx = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: ws.update_cell(1, target_col_idx, sel_w)
                
                for r_idx, val in new_att_status.items():
                    ws.update_cell(r_idx, target_col_idx, "1" if val else "")
                st.success("저장되었습니다!"); st.rerun()

    st.markdown("---")
    
    # 4. 연간 통합 통계 및 직관적 수정 (1년치 흐름)
    with st.expander("📊 연간 통합 출석 현황 (1주~52주 전체 보기/수정)", expanded=False):
        st.info("💡 표에서 '1'을 입력하면 출석(🟢), 지우면 결석입니다. 수정 후 아래 저장 버튼을 누르세요.")
        week_cols = [f"{i}주" for i in range(1, 53) if f"{i}주" in df.columns]
        annual_df = df[df['학교상태'] != '이사'][[class_col, '이름'] + week_cols].copy()
        
        # 뷰어용 변환 (🟢 표시)
        view_annual_df = annual_df.copy()
        for w in week_cols:
            view_annual_df[w] = view_annual_df[w].apply(lambda x: "🟢" if str(x).strip() == "1" else "")
        
        # 수정 가능한 데이터 에디터
        edited_annual = st.data_editor(annual_df, use_container_width=True, hide_index=True)
        
        if st.button("📝 연간 전체 데이터 수정사항 저장"):
            with st.spinner("대량 데이터 업데이트 중..."):
                for r in range(len(annual_df)):
                    for w in week_cols:
                        if str(annual_df.iloc[r][w]) != str(edited_annual.iloc[r][w]):
                            row_idx = df.iloc[r]['sheet_row']
                            col_idx = headers.index(w) + 1
                            ws.update_cell(row_idx, col_idx, str(edited_annual.iloc[r][w]))
                st.success("연간 데이터가 업데이트되었습니다!"); st.rerun()

# --- 교적부 등 나머지 탭은 v24.3의 기능을 100% 유지 ---
with tabs[0]: # 교적부
    st.subheader("📋 교적부 통합 데이터베이스")
    manage_mode = st.radio("작업 모드 선택", ["👀 전체 명단 보기", "📝 개별 상세 조회 및 수정/삭제", "➕ 신규 인원 추가"], horizontal=True)
    req_cols = ['학년(담임)', '이름', '사진', '생년월일', '주소', '부모(아빠/엄마)', '연락처', '학교상태', '비고', '전도자']
    available_cols = [c for c in req_cols if c in df.columns]
    if manage_mode == "👀 전체 명단 보기":
        st.dataframe(df[available_cols], use_container_width=True, hide_index=True, column_config={"사진": st.column_config.ImageColumn("사진")})
    elif manage_mode == "📝 개별 상세 조회 및 수정/삭제":
        search_list = df.apply(lambda r: f"{r['이름']} | {r[class_col]}", axis=1).tolist()
        search_options = ["학생을 선택하세요"] + search_list
        selected_index = st.selectbox("수정/삭제할 학생 선택", range(len(search_options)), format_func=lambda x: search_options[x])
        if selected_index > 0:
            target_data = df.iloc[selected_index - 1]
            sheet_row = target_data['sheet_row']
            with st.form("edit_member_form_v24_4"):
                e_class = st.text_input("학년(담임)", value=target_data.get('학년(담임)', ''), placeholder="예: 1-1(권은주)")
                e_name = st.text_input("이름", value=target_data.get('이름', ''))
                e_birth = st.text_input("생년월일", value=target_data.get('생년월일', ''), placeholder="예: 19.02.26")
                e_phone = st.text_input("연락처", value=target_data.get('연락처', ''), placeholder="예: 010-1234-5678")
                e_status = st.selectbox("학교상태", ["일반", "새친구", "이사", "교사"], index=0)
                if st.form_submit_button("💾 수정 저장"):
                    ws.update_cell(sheet_row, headers.index('학년(담임)')+1, e_class)
                    ws.update_cell(sheet_row, headers.index('이름')+1, e_name)
                    st.success("수정되었습니다!"); st.rerun()
    elif manage_mode == "➕ 신규 인원 추가":
        with st.form("add_member_form_new"):
            n_class = st.text_input("학년(담임)", placeholder="예: 1-1(권은주)")
            n_name = st.text_input("이름")
            if st.form_submit_button("✨ 등록"):
                new_row = [""] * len(headers)
                new_row[headers.index('이름')] = n_name
                new_row[headers.index('학년(담임)')] = n_class
                ws.append_row(new_row)
                st.success("등록되었습니다!"); st.rerun()

with tabs[2]: # 반편성
    st.subheader("🏫 반별 명단 현황")
    grouped = df[df['학교상태'] != '이사'].groupby(class_col)
    cols = st.columns(3)
    for i, (name, group) in enumerate(grouped):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{name}** ({len(group)}명)")
                st.write(", ".join([f"🔴{n}" if s == '새친구' else n for n, s in zip(group['이름'], group['학교상태'])]))

with tabs[3]: # 생일
    st.subheader("🎂 월별 생일 명단")
    b_map = {str(i): [] for i in range(1, 13)}
    for _, r in df.iterrows():
        b = str(r['생년월일'])
        if len(b.split('.')) >= 3:
            try: m = str(int(b.split('.')[1])); d = str(int(b.split('.')[2])); b_map[m].append(f"**{r['이름']}** ({r[class_col]}) - {d}일")
            except: pass
    cols = st.columns(3)
    for i in range(1, 13):
        with cols[(i-1)%3]:
            with st.container(border=True):
                st.markdown(f"<b>📅 {i}월</b><hr>", unsafe_allow_html=True)
                for p in b_map[str(i)]: st.write(p)

with tabs[4]: # 새친구
    st.subheader("🌱 최근 등록 새친구")
    news = df[df['학교상태'] == '새친구']
    st.dataframe(news[available_cols], use_container_width=True, hide_index=True)

with tabs[5]: # 행사
    st.subheader("⚙️ 행사 및 활동 관리")
    if not df_act.empty:
        act_headers = ["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4"]
        v_act_cols = [c for c in act_headers if c in df_act.columns]
        edited_events = st.data_editor(df_act[v_act_cols], use_container_width=True, hide_index=True)
        if st.button("📝 행사 저장"):
            for r in range(len(edited_events)):
                for c in v_act_cols:
                    if str(df_act.iloc[r][c]) != str(edited_events.iloc[r][c]):
                        ws_act.update_cell(df_act.iloc[r]['sheet_row'], df_act.columns.get_loc(c)+1, str(edited_events.iloc[r][c]))
            st.success("업데이트 완료!"); st.rerun()
