import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 ---
st.set_page_config(page_title="유년부 관리 시스템", page_icon="🌱", layout="wide")

# 시크릿에서 징검다리 주소 가져오기
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
        
        # 헤더와 데이터를 분리해서 가져오기 (행 번호 추적을 위해)
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return ws, pd.DataFrame(), []
            
        headers = all_values[0]
        data_rows = all_values[1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        # 구글 시트의 실제 행 번호 기록 (헤더가 1행이므로 데이터는 2행부터)
        df['sheet_row'] = range(2, len(data_rows) + 2)
        
        # 컬럼명 유연하게 맞추기
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
st.title("🌱 유년부 통합 관리 시스템 v14.0")
st.markdown("---")

if df.empty:
    st.warning("구글 시트에 데이터가 없습니다.")
    st.stop()

# --- 4. 화면 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["✅ 출석 체크 현황", "📋 교적부 관리 (수정/등록/삭제)", "🏫 반편성 및 통계"])

# ==========================================
# [탭 1] 출석 체크 (모바일 최적화 & 현황판)
# ==========================================
with tab1:
    st.subheader("📅 실시간 출석 체크 현황")
    
    # 1. 가장 가까운 주차 자동 계산
    current_week_num = datetime.date.today().isocalendar()[1]
    weeks = [f"{i}주차" for i in range(1, 53)]
    
    # 시트에 주차 컬럼이 없으면 에러 방지
    for w in weeks:
        if w not in df.columns:
            df[w] = ""
            
    colA, colB, colC = st.columns(3)
    with colA:
        selected_week = st.selectbox("출석 주차 선택", weeks, index=current_week_num - 1)
    with colB:
        class_list = ["전체보기"] + sorted(list(df[df['반'] != '']['반'].unique()))
        selected_class = st.selectbox("반 필터", class_list)
    with colC:
        search_name = st.text_input("이름 검색 (출석용)", "")

    # 2. 필터링 (이사/퇴소자 제외)
    att_df = df.copy()
    if '상태' in att_df.columns:
        att_df = att_df[att_df['상태'] != '이사']
    if selected_class != "전체보기":
        att_df = att_df[att_df['반'] == selected_class]
    if search_name:
        att_df = att_df[att_df['이름'].str.contains(search_name)]
        
    att_df = att_df.sort_values(by=['반', '이름'])

    # 3. 출석 통계 대시보드
    total_students = len(att_df)
    attended_count = len(att_df[att_df[selected_week].astype(str).str.strip() == "1"])
    absent_count = total_students - attended_count
    att_rate = int((attended_count / total_students * 100)) if total_students > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 인원", f"{total_students}명")
    m2.metric("✅ 출석", f"{attended_count}명")
    m3.metric("❌ 결석", f"{absent_count}명")
    m4.metric("📈 출석률", f"{att_rate}%")
    
    st.markdown("---")

    # 4. 모바일 친화적 출석 폼 (일괄 저장 기능으로 속도 향상)
    with st.form("attendance_form"):
        st.write("✔️ 터치하여 출석을 체크하고, 하단의 [출석 일괄 저장]을 누르세요.")
        
        # 체크박스 상태를 담을 딕셔너리
        new_att_status = {}
        
        cols = st.columns(2) # 모바일에서는 자동으로 세로로 쌓임, PC에서는 2단
        for i, (idx, row) in enumerate(att_df.iterrows()):
            col = cols[i % 2]
            is_attended = True if str(row[selected_week]).strip() == "1" else False
            name_display = f"🔴 {row['이름']}" if row.get('상태') == '새친구' else row['이름']
            label = f"[{row['반']}] {name_display}"
            
            # 체크박스 생성
            new_att_status[row['sheet_row']] = col.checkbox(label, value=is_attended, key=f"chk_{row['sheet_row']}")
            
        submit_att = st.form_submit_button("💾 출석 일괄 저장", use_container_width=True)
        
        if submit_att:
            with st.spinner("구글 시트에 출석을 기록 중입니다..."):
                try:
                    # 해당 주차의 열(Column) 인덱스 찾기 (A=1, B=2...)
                    col_index = headers.index(selected_week) + 1
                    
                    # 변경된 데이터만 찾아서 업데이트 (일괄 업데이트 시도)
                    for sheet_row, is_checked in new_att_status.items():
                        val_to_write = "1" if is_checked else ""
                        ws.update_cell(sheet_row, col_index, val_to_write)
                        
                    st.success(f"{selected_week} 출석이 완벽하게 저장되었습니다!")
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 중 에러 발생: {e}")

# ==========================================
# [탭 2] 교적부 관리 (명단 + 프로필 + 수정/등록)
# ==========================================
with tab2:
    st.subheader("📋 교적부 개별 관리 (수정/등록/삭제)")
    
    # 1. 관리 모드 선택 (상세보기&수정 vs 신규등록)
    manage_mode = st.radio("작업 선택", ["🔍 기존 인원 검색 및 수정/삭제", "➕ 신규 인원 등록"], horizontal=True)
    
    if manage_mode == "🔍 기존 인원 검색 및 수정/삭제":
        st.info("💡 표에서 학생을 확인하고, 아래에서 이름으로 선택하여 상세정보 4배 확대 및 수정/삭제하세요.")
        
        # 정렬 및 필터 적용된 테이블 보여주기
        sort_opt = st.selectbox("표 정렬 기준", ["반 기준 오름차순", "이름순 정렬"])
        display_df = df.copy()
        if sort_opt == "이름순 정렬":
            display_df = display_df.sort_values('이름')
        else:
            display_df = display_df.sort_values('반')
            
        st.dataframe(display_df[['반', '이름', '상태', '연락처', '부모님', '생년월일']], use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # 2. 수정/삭제할 타겟 선택
        target_list = ["선택 안함"] + list(display_df['이름'] + " (" + display_df['반'] + ")")
        target_selection = st.selectbox("📝 상세 프로필 조회 및 수정할 학생을 선택하세요.", target_list)
        
        if target_selection != "선택 안함":
            # 선택한 학생 데이터 추출
            target_name = target_selection.split(" (")[0]
            target_grade = target_selection.split(" (")[1].replace(")", "")
            target_data = df[(df['이름'] == target_name) & (df['반'] == target_grade)].iloc[0]
            sheet_row = target_data['sheet_row']
            
            st.markdown(f"### 👤 {target_name} 학생 상세 프로필")
            
            # 3. 사진 4배 확대 뷰 & 정보 폼
            col_img, col_form = st.columns([1, 2])
            
            with col_img:
                if target_data.get('사진'):
                    st.image(target_data['사진'], use_container_width=True, caption=f"{target_name} 학생")
                else:
                    st.info("등록된 사진이 없습니다.")
                    
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
                    
                    e_photo = st.file_uploader("사진 변경 (기존 사진을 유지하려면 비워두세요)", type=["jpg", "png", "jpeg"])
                    
                    col_btn1, col_btn2 = st.columns(2)
                    submit_edit = col_btn1.form_submit_button("💾 정보 수정 (업데이트)")
                    submit_del = col_btn2.form_submit_button("🚨 이 학생 완전히 삭제")
                    
                    if submit_edit:
                        photo_url = target_data.get('사진', '') # 기본은 기존 사진
                        if e_photo:
                            with st.spinner("새 사진 업로드 중..."):
                                b64 = base64.b64encode(e_photo.getvalue()).decode()
                                res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{e_name}_{e_photo.name}", "mimeType": e_photo.type, "base64Data": b64}).json()
                                if res.get("success"): photo_url = res.get("fileUrl")
                        
                        # 구글 시트 업데이트 (A~L열을 쓴다고 가정. 실제 컬럼 인덱스에 맞춰야 함)
                        try:
                            # 기존 행 데이터를 리스트로 가져와서 필요한 부분만 교체 (안전한 방식)
                            row_values = ws.row_values(sheet_row)
                            # 길이를 최소 헤더만큼 늘림
                            row_values += [""] * (len(headers) - len(row_values))
                            
                            # 값 교체 (인덱스 매칭)
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
                            if '사진' in headers: row_values[headers.index('사진')] = photo_url
                            
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
                    photo_url = ""
                    if n_photo:
                        with st.spinner("구글 드라이브에 사진 저장 중..."):
                            b64 = base64.b64encode(n_photo.getvalue()).decode()
                            res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{n_name}_{n_photo.name}", "mimeType": n_photo.type, "base64Data": b64}).json()
                            if res.get("success"): photo_url = res.get("fileUrl")
                    
                    try:
                        # 빈 배열 생성 후 채워넣기
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
                        if '사진' in headers: new_row[headers.index('사진')] = photo_url
                        
                        ws.append_row(new_row)
                        st.success(f"{n_name} 등록 성공!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"시트 저장 에러: {e}")

# ==========================================
# [탭 3] 반편성 현황 (기존 기능 유지)
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
