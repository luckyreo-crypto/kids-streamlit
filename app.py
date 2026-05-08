import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 관리 시스템", page_icon="🌱", layout="wide")

if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 및 데이터 로드 ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
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
        if len(all_values) <= 1:
            return ws, pd.DataFrame(), []
            
        headers = all_values[0]
        data_rows = all_values[1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        df['sheet_row'] = range(2, len(data_rows) + 2)
        
        rename_dict = {}
        if '학년(담임)' in df.columns: rename_dict['학년(담임)'] = '반'
        if '부모(아빠/엄마)' in df.columns: rename_dict['부모(아빠/엄마)'] = '부모님'
        if '비고' in df.columns: rename_dict['비고'] = '등록일/기타'
        df.rename(columns=rename_dict, inplace=True)
        
        return ws, df, headers
    except Exception as e:
        st.error(f"시트 로드 에러: {e}")
        return None, pd.DataFrame(), []

ws, df, headers = get_data()

# --- 3. 헤더 영역 ---
st.title("🌱 유년부 통합 관리 시스템 v15.0")
st.markdown("---")

if df.empty:
    st.warning("구글 시트에 데이터가 없습니다.")
    st.stop()

# --- 4. 화면 탭 구성 ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "✅ 출석 체크", "📋 교적부 관리", "🏫 반편성 통계", "🎂 월별 생일표", "🌱 새친구 목록"
])

# ==========================================
# [탭 1] 출석 체크 (날짜 표시 + 표 형식 에디터)
# ==========================================
with tab1:
    st.subheader("📅 실시간 주일 출석 체크")
    
    # 주차 및 날짜 계산 (2026년 기준, 1월 4일이 첫 주일)
    start_date = datetime.date(2026, 1, 4)
    week_options = []
    week_col_names = []
    for i in range(1, 53):
        col_name = f"{i}주차"
        week_col_names.append(col_name)
        week_options.append(f"{col_name} ({start_date.strftime('%m/%d')})")
        start_date += datetime.timedelta(days=7)
        # 시트에 주차 컬럼이 없으면 에러 방지용으로 추가
        if col_name not in df.columns:
            df[col_name] = ""
            
    # 현재 주차 자동 선택
    current_week_idx = datetime.date.today().isocalendar()[1] - 1
    if current_week_idx < 0 or current_week_idx > 51: current_week_idx = 0
    
    colA, colB, colC = st.columns(3)
    with colA:
        selected_display = st.selectbox("출석 주차 및 날짜 선택", week_options, index=current_week_idx)
        selected_week_col = selected_display.split(" ")[0] # "1주차" 만 추출
    with colB:
        class_list = ["전체보기"] + sorted(list(df[df['반'] != '']['반'].unique()))
        selected_class = st.selectbox("반 필터", class_list)
    with colC:
        search_name = st.text_input("이름 검색 (출석용)", "")

    # 필터링
    att_df = df.copy()
    if '상태' in att_df.columns:
        att_df = att_df[att_df['상태'] != '이사']
    if selected_class != "전체보기":
        att_df = att_df[att_df['반'] == selected_class]
    if search_name:
        att_df = att_df[att_df['이름'].str.contains(search_name)]
        
    att_df = att_df.sort_values(by=['반', '이름'])

    # 출석 통계 대시보드
    total_students = len(att_df)
    attended_count = len(att_df[att_df[selected_week_col].astype(str).str.strip() == "1"])
    absent_count = total_students - attended_count
    att_rate = int((attended_count / total_students * 100)) if total_students > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 인원", f"{total_students}명")
    m2.metric("✅ 출석", f"{attended_count}명")
    m3.metric("❌ 결석", f"{absent_count}명")
    m4.metric("📈 출석률", f"{att_rate}%")
    
    st.markdown("---")

    # 어제 버전처럼 표에서 바로 체크하는 기능 (Data Editor)
    st.write("✔️ 표에서 체크박스를 클릭하여 출석을 체크한 뒤, **[💾 출석 일괄 저장]** 버튼을 누르세요.")
    
    # 편집용 데이터프레임 만들기
    edit_df = att_df[['sheet_row', '반', '이름', '상태']].copy()
    edit_df['✅ 출석체크'] = att_df[selected_week_col].apply(lambda x: True if str(x).strip() == "1" else False)
    
    # 데이터 에디터 표시
    edited_df = st.data_editor(
        edit_df[['반', '이름', '상태', '✅ 출석체크']],
        disabled=["반", "이름", "상태"], # 체크박스만 수정 가능하게 잠금
        use_container_width=True,
        hide_index=True,
    )
    
    if st.button("💾 출석 일괄 저장", type="primary", use_container_width=True):
        with st.spinner("구글 시트에 기록 중입니다..."):
            try:
                # 변경된 항목만 찾아서 업데이트
                col_index = headers.index(selected_week_col) + 1
                for i in range(len(edit_df)):
                    old_val = edit_df.iloc[i]['✅ 출석체크']
                    new_val = edited_df.iloc[i]['✅ 출석체크']
                    if old_val != new_val:
                        sheet_row = edit_df.iloc[i]['sheet_row']
                        val_to_write = "1" if new_val else ""
                        ws.update_cell(sheet_row, col_index, val_to_write)
                st.success(f"{selected_display} 출석이 성공적으로 저장되었습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"저장 중 에러 발생: {e}")

    # 연간 통계표 (어제 버전 복구)
    with st.expander("📈 전체 연간 출석 통계 보기 (PC 권장)", expanded=False):
        cols_to_show = ['반', '이름'] + week_col_names
        st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)


# ==========================================
# [탭 2] 교적부 관리 (에러 수정 완료)
# ==========================================
with tab2:
    st.subheader("📋 교적부 개별 관리")
    manage_mode = st.radio("작업 선택", ["🔍 기존 인원 검색 및 수정/삭제", "➕ 신규 인원 등록"], horizontal=True)
    
    if manage_mode == "🔍 기존 인원 검색 및 수정/삭제":
        sort_opt = st.selectbox("명단 정렬 기준", ["반 순서대로", "이름순"])
        display_df = df.copy()
        if sort_opt == "이름순":
            display_df = display_df.sort_values('이름')
        else:
            display_df = display_df.sort_values('반')
            
        st.dataframe(display_df[['반', '이름', '상태', '연락처', '부모님', '생년월일']], use_container_width=True, hide_index=True)
        st.markdown("---")
        
        target_list = ["선택 안함"] + list(display_df['이름'] + " (" + display_df['반'] + ")")
        target_selection = st.selectbox("📝 상세 프로필을 조회하고 수정/삭제할 학생을 선택하세요.", target_list)
        
        if target_selection != "선택 안함":
            target_name = target_selection.split(" (")[0]
            target_grade = target_selection.split(" (")[1].replace(")", "")
            target_data = df[(df['이름'] == target_name) & (df['반'] == target_grade)].iloc[0]
            sheet_row = target_data['sheet_row']
            
            st.markdown(f"### 👤 {target_name} 학생 상세 프로필")
            
            col_img, col_form = st.columns([1, 2])
            with col_img:
                # 사진 에러(MediaFileStorageError) 방지 코드 적용
                photo_url = target_data.get('사진', '')
                if isinstance(photo_url, str) and photo_url.startswith('http'):
                    try:
                        st.image(photo_url, use_container_width=True, caption=f"{target_name} 학생")
                    except:
                        st.warning("사진 URL이 유효하지 않습니다.")
                else:
                    st.info("등록된 사진이 없거나 옛날(NAS) 주소입니다.")
                    
            with col_form:
                with st.form("edit_form"):
                    e_name = st.text_input("이름", value=target_data.get('이름', ''))
                    e_grade = st.text_input("반 (예: 1-1)", value=target_data.get('반', ''))
                    e_status = st.selectbox("상태", ["일반", "새친구", "이사", "교사"], index=["일반", "새친구", "이사", "교사"].index(target_data.get('상태', '일반')) if target_data.get('상태') in ["일반", "새친구", "이사", "교사"] else 0)
                    e_birth = st.text_input("생년월일", value=target_data.get('생년월일', ''))
                    e_phone = st.text_input("연락처", value=target_data.get('연락처', ''))
                    e_parents = st.text_input("부모님", value=target_data.get('부모님', ''))
                    e_address = st.text_input("주소", value=target_data.get('주소', ''))
                    e_memo = st.text_input("등록일/기타", value=target_data.get('등록일/기타', ''))
                    e_photo = st.file_uploader("사진 변경 (기존 사진 유지시 비워둠)", type=["jpg", "png", "jpeg"])
                    
                    c1, c2 = st.columns(2)
                    submit_edit = c1.form_submit_button("💾 정보 수정 (업데이트)")
                    submit_del = c2.form_submit_button("🚨 이 학생 완전히 삭제")
                    
                    if submit_edit:
                        new_photo_url = photo_url
                        if e_photo:
                            with st.spinner("새 사진 업로드 중..."):
                                b64 = base64.b64encode(e_photo.getvalue()).decode()
                                res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{e_name}_{e_photo.name}", "mimeType": e_photo.type, "base64Data": b64}).json()
                                if res.get("success"): new_photo_url = res.get("fileUrl")
                        try:
                            row_values = ws.row_values(sheet_row)
                            row_values += [""] * (len(headers) - len(row_values))
                            if '이름' in headers: row_values[headers.index('이름')] = e_name
                            if '학년(담임)' in headers: row_values[headers.index('학년(담임)')] = e_grade
                            if '반' in headers: row_values[headers.index('반')] = e_grade
                            if '상태' in headers: row_values[headers.index('상태')] = e_status
                            if '생년월일' in headers: row_values[headers.index('생년월일')] = e_birth
                            if '연락처' in headers: row_values[headers.index('연락처')] = e_phone
                            if '부모(아빠/엄마)' in headers: row_values[headers.index('부모(아빠/엄마)')] = e_parents
                            if '부모님' in headers: row_values[headers.index('부모님')] = e_parents
                            if '주소' in headers: row_values[headers.index('주소')] = e_address
                            if '비고' in headers: row_values[headers.index('비고')] = e_memo
                            if '등록일/기타' in headers: row_values[headers.index('등록일/기타')] = e_memo
                            if '사진' in headers: row_values[headers.index('사진')] = new_photo_url
                            
                            ws.update(f"A{sheet_row}", [row_values])
                            st.success("수정이 완료되었습니다!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"수정 실패: {e}")
                            
                    if submit_del:
                        ws.delete_rows(sheet_row)
                        st.success(f"{target_name} 학생이 삭제되었습니다.")
                        st.rerun()

    elif manage_mode == "➕ 신규 인원 등록":
        # ... (신규 등록 코드는 이전과 동일하게 유지하여 안정성 확보)
        st.markdown("### ✨ 새로운 학생/교사 등록")
        with st.form("new_member_form"):
            col1, col2 = st.columns(2)
            with col1:
                n_status = st.selectbox("상태", ["일반", "새친구", "이사", "교사"])
                n_grade = st.text_input("반 (예: 1-1, 교사)")
                n_name = st.text_input("이름")
                n_birth = st.text_input("생년월일 (예: 19.02.26)")
                n_phone = st.text_input("연락처")
            with col2:
                n_parents = st.text_input("부모님")
                n_address = st.text_input("주소")
                n_memo = st.text_input("등록일/비고")
                n_evangelist = st.text_input("전도자")
                n_photo = st.file_uploader("사진 선택", type=["jpg", "png", "jpeg"])
                
            submit_new = st.form_submit_button("저장하기", use_container_width=True)

            if submit_new:
                if not n_name or not n_grade:
                    st.warning("이름과 반은 필수 입력입니다!")
                else:
                    new_photo_url = ""
                    if n_photo:
                        with st.spinner("구글 드라이브에 사진 저장 중..."):
                            b64 = base64.b64encode(n_photo.getvalue()).decode()
                            res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{n_name}_{n_photo.name}", "mimeType": n_photo.type, "base64Data": b64}).json()
                            if res.get("success"): new_photo_url = res.get("fileUrl")
                    
                    try:
                        new_row = [""] * len(headers)
                        if '이름' in headers: new_row[headers.index('이름')] = n_name
                        if '학년(담임)' in headers: new_row[headers.index('학년(담임)')] = n_grade
                        if '반' in headers: new_row[headers.index('반')] = n_grade
                        if '상태' in headers: new_row[headers.index('상태')] = n_status
                        if '생년월일' in headers: new_row[headers.index('생년월일')] = n_birth
                        if '연락처' in headers: new_row[headers.index('연락처')] = n_phone
                        if '부모(아빠/엄마)' in headers: new_row[headers.index('부모(아빠/엄마)')] = n_parents
                        if '부모님' in headers: new_row[headers.index('부모님')] = n_parents
                        if '주소' in headers: new_row[headers.index('주소')] = n_address
                        if '비고' in headers: new_row[headers.index('비고')] = n_memo
                        if '등록일/기타' in headers: new_row[headers.index('등록일/기타')] = n_memo
                        if '전도자' in headers: new_row[headers.index('전도자')] = n_evangelist
                        if '사진' in headers: new_row[headers.index('사진')] = new_photo_url
                        
                        ws.append_row(new_row)
                        st.success(f"{n_name} 등록 성공!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"시트 저장 에러: {e}")

# ==========================================
# [탭 3] 반편성 현황
# ==========================================
with tab3:
    st.subheader("🏫 반편성 및 요약 현황")
    st.write("※ 🔴: 새친구, ̶취̶소̶선̶: 이사")
    
    if not df.empty:
        student_df = df[(df['반'] != '교사') & (~df['반'].str.contains('테스트', na=False))]
        st.metric("현재 재적 학생 인원", f"{len(student_df)}명")
        
        grouped = df.groupby('반')
        cols = st.columns(3)
        col_idx = 0
        
        for grade, group in grouped:
            if grade == "": continue
            with cols[col_idx % 3]:
                with st.container(border=True):
                    st.markdown(f"#### {grade} (총 {len(group)}명)")
                    names = []
                    for _, row in group.iterrows():
                        n = str(row['이름'])
                        if row.get('상태') == '새친구': n = f"🔴{n}"
                        elif row.get('상태') == '이사': n = f"~{n}~"
                        names.append(n)
                    st.write(", ".join(names))
            col_idx += 1

# ==========================================
# [탭 4] 월별 생일표 (복구)
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
                    month = str(int(birth.split('.')[1]))
                    day = int(birth.split('.')[2])
                    months_data[month].append(f"**{name}** ({grade}, {day}일)")
                except:
                    pass
        
        cols = st.columns(4)
        for i in range(1, 13):
            with cols[(i-1) % 4]:
                with st.container(border=True):
                    st.markdown(f"##### {i}월")
                    if months_data[str(i)]:
                        for person in months_data[str(i)]:
                            st.write(person)
                    else:
                        st.caption("없음")

# ==========================================
# [탭 5] 새친구 목록 (복구)
# ==========================================
with tab5:
    st.subheader("🌱 최근 등록된 새친구 목록")
    if not df.empty and '상태' in df.columns:
        new_friends_df = df[df['상태'] == '새친구']
        if not new_friends_df.empty:
            # 필요한 컬럼만 추출 (시트에 존재하는지 확인 후 안전하게 추출)
            cols_to_display = []
            for c in ['등록일/기타', '비고', '반', '이름', '생년월일', '전도자', '부모님', '연락처', '주소']:
                if c in new_friends_df.columns:
                    cols_to_display.append(c)
            st.dataframe(new_friends_df[cols_to_display], use_container_width=True, hide_index=True)
        else:
            st.info("현재 등록된 새친구가 없습니다.")
