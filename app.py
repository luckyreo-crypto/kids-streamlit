import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 통합 관리 시스템", page_icon="🌱", layout="wide")

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

def get_data():
    try:
        sh = client.open_by_key(sheet_id)
        ws = sh.worksheet("교적부")
        all_values = ws.get_all_values()
        
        if not all_values or len(all_values) <= 1: 
            return ws, pd.DataFrame(), []
            
        headers = all_values[0]
        max_len = max(len(row) for row in all_values)
        
        # 부족한 헤더 강제 채우기
        while len(headers) < max_len:
            headers.append(f"미지정_컬럼_{len(headers)}")
            
        data_rows = []
        for row in all_values[1:]:
            padded_row = row + [""] * (max_len - len(row))
            data_rows.append(padded_row)
            
        df = pd.DataFrame(data_rows, columns=headers)
        df['sheet_row'] = range(2, len(data_rows) + 2) # 실제 행 번호
        
        # 컬럼명 유연성 확보
        rename_dict = {'학년(담임)': '반', '부모(아빠/엄마)': '부모님', '비고': '등록일/기타'}
        df.rename(columns={k: v for k, v in rename_dict.items() if k in df.columns}, inplace=True)
        
        for essential in ['이름', '반', '상태']:
            if essential not in df.columns: df[essential] = ""
                
        return ws, df, headers
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None, pd.DataFrame(), []

ws, df, headers = get_data()

if df.empty:
    st.error("🚨 구글 시트에 데이터가 없거나 형식이 잘못되었습니다. 시트 내용을 확인해주세요.")
    st.stop()

# --- 3. 공통 함수: 사진 업로드 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}).json()
        return res.get("fileUrl", "")
    except:
        return ""

# --- 4. 주차 및 날짜 세팅 (2026년 기준) ---
start_date = datetime.date(2026, 1, 4)
weeks_info = {}
for i in range(1, 53):
    w_name = f"{i}주차"
    w_date = start_date.strftime('%m/%d')
    weeks_info[w_name] = f"{w_name} ({w_date})"
    start_date += datetime.timedelta(days=7)

# --- 5. 화면 및 탭 구성 ---
st.title("🌱 유년부 통합 관리 시스템 v19.0")
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "01. 출석 & 연간통계", "02. 교적부 관리", "03. 반편성 현황", "04. 월별 생일표", "05. 새친구 목록"
])

# ==========================================
# [탭 1] 출석 & 연간통계 (오류 완벽 차단)
# ==========================================
with tab1:
    st.subheader("📅 주일 출석 체크 및 수정")
    
    curr_week = datetime.date.today().isocalendar()[1] - 1
    weeks_list = list(weeks_info.keys())
    
    colA, colB, colC = st.columns(3)
    with colA:
        sel_w = st.selectbox("주차 선택 (과거/미래 출석 관리)", weeks_list, index=max(0, min(51, curr_week)), format_func=lambda x: weeks_info[x])
    with colB:
        classes = ["전체보기"] + sorted([str(c) for c in df['반'].unique() if str(c).strip()])
        sel_class = st.selectbox("반 필터", classes)
    with colC:
        search_name = st.text_input("이름 검색")

    # ★ 핵심 수정: 시트에 주차가 있는지 공백 무시하고 찾기
    matched_col = None
    for h in headers:
        if str(h).strip() == sel_w:
            matched_col = h
            break

    # 시트에 없는 주차일 경우 공간 늘리고 안전하게 생성
    if not matched_col:
        with st.spinner(f"시트에 '{sel_w}' 칸을 자동으로 생성하고 있습니다 (공간 확장 포함)..."):
            new_col_idx = len(headers) + 1
            try:
                ws.update_cell(1, new_col_idx, sel_w)
            except:
                # 구글 시트 기둥(열)이 꽉 찼을 경우 1칸 강제 추가 후 다시 시도
                ws.add_cols(1)
                ws.update_cell(1, new_col_idx, sel_w)
            
            headers.append(sel_w)
            df[sel_w] = ""
            st.rerun()

    target_col_name = matched_col if matched_col else sel_w
    target_col_idx = headers.index(target_col_name) + 1

    # 필터링
    att_df = df[df['상태'] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df['반'] == sel_class]
    if search_name: att_df = att_df[att_df['이름'].str.contains(search_name, na=False)]
    
    total = len(att_df)
    present = len(att_df[att_df[target_col_name].astype(str).str.strip() == "1"])
    absent = total - present
    rate = int((present/total)*100) if total > 0 else 0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 인원", f"{total}명")
    m2.metric("✅ 출석", f"{present}명")
    m3.metric("❌ 결석", f"{absent}명")
    m4.metric("📈 출석률", f"{rate}%")
    st.markdown("---")

    # 출석 에디터
    st.write(f"✔️ **{weeks_info[sel_w]}** 출석을 체크하고 하단의 버튼을 누르세요.")
    edit_att_df = att_df[['sheet_row', '반', '이름']].copy()
    edit_att_df['✅ 출석'] = att_df[target_col_name].apply(lambda x: True if str(x).strip() == "1" else False)
    
    edited_att = st.data_editor(
        edit_att_df[['반', '이름', '✅ 출석']], 
        use_container_width=True, hide_index=True, disabled=["반", "이름"]
    )
    
    if st.button("💾 출석 결과 저장 / 수정", type="primary", use_container_width=True):
        with st.spinner("시트 업데이트 중..."):
            changed = 0
            for i in range(len(edit_att_df)):
                old_val = edit_att_df.iloc[i]['✅ 출석']
                new_val = edited_att.iloc[i]['✅ 출석']
                if old_val != new_val:
                    row_idx = edit_att_df.iloc[i]['sheet_row']
                    ws.update_cell(row_idx, target_col_idx, "1" if new_val else "")
                    changed += 1
            if changed > 0:
                st.success(f"{changed}명의 출석 정보가 변경되었습니다!")
                st.rerun()
            else:
                st.info("변경된 출석 내용이 없습니다.")

    st.markdown("---")
    
    # ★ 추가: 과거 출석 현황 한눈에 보기
    with st.expander("📊 전체 연간 출석 현황 보기 (과거 출석 리스트 확인용)", expanded=False):
        week_cols = [c for c in df.columns if "주차" in str(c)]
        disp_annual_df = df[df['상태'] != '이사'][['반', '이름'] + week_cols].copy()
        
        # 1을 O로, 빈칸을 X로 예쁘게 변환해서 보여주기
        for w in week_cols:
            disp_annual_df[w] = disp_annual_df[w].apply(lambda x: "🟢" if str(x).strip() == "1" else "")
            
        st.dataframe(disp_annual_df.sort_values(by=['반', '이름']), use_container_width=True, hide_index=True)

# ==========================================
# [탭 2] 교적부 관리
# ==========================================
with tab2:
    st.subheader("📋 교적부 데이터 관리")
    st.info("💡 표에서 글자를 더블클릭해 수정한 후, **[수정 내용 저장]**을 누르면 시트가 안전하게 업데이트됩니다.")
    
    disp_cols = ['반', '이름', '상태', '연락처', '부모님', '주소', '등록일/기타', '전도자']
    disp_cols = [c for c in disp_cols if c in df.columns]
    
    manage_df = df[disp_cols].copy()
    
    edited_manage = st.data_editor(
        manage_df, use_container_width=True, hide_index=True,
        column_config={"상태": st.column_config.SelectboxColumn("상태", options=["일반", "새친구", "이사", "교사"])}
    )
    
    if st.button("💾 표 수정 내용 안전하게 저장", use_container_width=True):
        with st.spinner("변경된 칸만 찾아서 핀셋 업데이트 중입니다..."):
            changes_made = False
            for r_idx in range(len(manage_df)):
                for c_name in disp_cols:
                    old_v = str(manage_df.iloc[r_idx][c_name]).strip()
                    new_v = str(edited_manage.iloc[r_idx][c_name]).strip()
                    
                    if old_v != new_v:
                        sheet_r = df.iloc[r_idx]['sheet_row']
                        
                        orig_h = c_name
                        if c_name == '반' and '학년(담임)' in headers: orig_h = '학년(담임)'
                        elif c_name == '부모님' and '부모(아빠/엄마)' in headers: orig_h = '부모(아빠/엄마)'
                        elif c_name == '등록일/기타' and '비고' in headers: orig_h = '비고'
                        
                        if orig_h in headers:
                            sheet_c = headers.index(orig_h) + 1
                            ws.update_cell(sheet_r, sheet_c, new_v)
                            changes_made = True
            
            if changes_made:
                st.success("데이터가 안전하게 저장되었습니다!")
                st.rerun()
            else:
                st.info("변경된 내용이 없습니다.")

    st.markdown("---")
    
    with st.expander("➕ 새친구 / 신규 인원 등록 (사진 첨부 가능)", expanded=False):
        with st.form("new_member_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                n_name = st.text_input("이름 (필수)")
                n_class = st.text_input("반 (필수, 예: 1-1(권은주))")
                n_status = st.selectbox("상태", ["일반", "새친구", "이사", "교사"], index=1)
                n_birth = st.text_input("생년월일 (예: 19.02.26)")
            with c2:
                n_phone = st.text_input("연락처")
                n_parents = st.text_input("부모님")
                n_addr = st.text_input("주소")
                n_photo = st.file_uploader("학생 사진 (선택)", type=["jpg", "png", "jpeg"])
                
            if st.form_submit_button("✨ 교적부에 새로 등록하기", use_container_width=True):
                if not n_name or not n_class:
                    st.error("이름과 반은 반드시 입력해야 합니다.")
                else:
                    with st.spinner("구글 시트에 추가 중입니다..."):
                        photo_url = upload_photo(n_photo, n_name)
                        new_row = [""] * len(headers)
                        
                        h_map = {str(h).strip(): i for i, h in enumerate(headers)}
                        if '이름' in h_map: new_row[h_map['이름']] = n_name
                        if '학년(담임)' in h_map: new_row[h_map['학년(담임)']] = n_class
                        elif '반' in h_map: new_row[h_map['반']] = n_class
                        if '상태' in h_map: new_row[h_map['상태']] = n_status
                        if '생년월일' in h_map: new_row[h_map['생년월일']] = n_birth
                        if '연락처' in h_map: new_row[h_map['연락처']] = n_phone
                        if '부모(아빠/엄마)' in h_map: new_row[h_map['부모(아빠/엄마)']] = n_parents
                        elif '부모님' in h_map: new_row[h_map['부모님']] = n_parents
                        if '주소' in h_map: new_row[h_map['주소']] = n_addr
                        if '사진' in h_map: new_row[h_map['사진']] = photo_url
                        
                        ws.append_row(new_row)
                        st.success(f"[{n_class}] {n_name} 학생이 등록되었습니다!")
                        st.rerun()

# ==========================================
# [탭 3] 반편성 현황
# ==========================================
with tab3:
    st.subheader("🏫 반편성 현황")
    if not df.empty:
        student_df = df[(df['반'] != '교사') & (df['상태'] != '이사')]
        st.metric("총 재적 인원 (이사/교사 제외)", f"{len(student_df)}명")
        
        grouped = df.groupby('반')
        cols = st.columns(3)
        i = 0
        for name, group in grouped:
            if not str(name).strip() or name == "교사": continue
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{name}** ({len(group)}명)")
                    members = []
                    for _, r in group.iterrows():
                        nm = r['이름']
                        if r.get('상태') == '새친구': nm = f"🔴{nm}"
                        elif r.get('상태') == '이사': nm = f"~~{nm}~~"
                        members.append(str(nm))
                    st.write(", ".join(members))
            i += 1

# ==========================================
# [탭 4] 월별 생일표
# ==========================================
with tab4:
    st.subheader("🎂 월별 생일표")
    if not df.empty and '생년월일' in df.columns:
        months_data = {str(i): [] for i in range(1, 13)}
        for _, row in df.iterrows():
            birth = str(row.get('생년월일', ''))
            name = str(row.get('이름', ''))
            grade = str(row.get('반', ''))
            if birth and len(birth.split('.')) >= 3:
                try:
                    m = str(int(birth.split('.')[1]))
                    d = int(birth.split('.')[2])
                    months_data[m].append(f"**{name}** ({grade}, {d}일)")
                except: pass
        
        cols = st.columns(4)
        for i in range(1, 13):
            with cols[(i-1) % 4]:
                with st.container(border=True):
                    st.markdown(f"##### {i}월")
                    if months_data[str(i)]:
                        for p in months_data[str(i)]: st.write(p)
                    else:
                        st.caption("없음")

# ==========================================
# [탭 5] 새친구 목록
# ==========================================
with tab5:
    st.subheader("🌱 최근 등록된 새친구 목록")
    if not df.empty and '상태' in df.columns:
        new_df = df[df['상태'] == '새친구']
        if not new_df.empty:
            view_cols = [c for c in ['등록일/기타', '반', '이름', '생년월일', '연락처', '주소'] if c in new_df.columns]
            st.dataframe(new_df[view_cols], use_container_width=True, hide_index=True)
        else:
            st.info("등록된 새친구가 없습니다.")
