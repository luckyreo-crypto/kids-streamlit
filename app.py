import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import base64
import datetime

# --- 1. 기본 설정 및 모바일 최적화 스타일 ---
st.set_page_config(page_title="유년부 통합 관리 v26.0", page_icon="🌱", layout="wide")

st.markdown("""
    <style>
    /* 반별 그룹 헤더 스타일 */
    .class-header {
        background-color: #f1f8ff;
        padding: 12px 15px;
        border-radius: 8px;
        color: #0366d6;
        font-weight: 800;
        font-size: 1.1rem;
        margin-top: 20px;
        margin-bottom: 15px;
        border-left: 5px solid #0366d6;
    }
    .month-container { 
        min-height: 200px; border: 1px solid #eee; padding: 10px; 
        border-radius: 10px; background: white; margin-bottom: 15px; 
    }
    </style>
    """, unsafe_allow_html=True)

if "GOOGLE_PROXY_URL" in st.secrets:
    GOOGLE_PROXY_URL = st.secrets["GOOGLE_PROXY_URL"]
else:
    st.error("Secrets 설정에서 GOOGLE_PROXY_URL이 누락되었습니다!")
    st.stop()

# --- 2. 구글 시트 연결 및 데이터 로드 ---
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
        
        # 1. 교적부 시트 로드
        ws_m = sh.worksheet("교적부")
        vals = ws_m.get_all_values()
        headers = vals[0]
        df_m = pd.DataFrame(vals[1:], columns=headers) if len(vals) > 1 else pd.DataFrame()
        df_m['sheet_row'] = range(2, len(df_m) + 2)
        
        if '상태' in df_m.columns and '학교상태' not in df_m.columns:
            df_m.rename(columns={'상태': '학교상태'}, inplace=True)
            headers = [h if h != '상태' else '학교상태' for h in headers]
            
        # 2. 활동간식 시트 로드
        try:
            ws_a = sh.worksheet("활동간식")
            a_vals = ws_a.get_all_values()
            if not a_vals:
                ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
                a_vals = ws_a.get_all_values()
        except:
            ws_a = sh.add_worksheet(title="활동간식", rows="500", cols="10")
            ws_a.append_row(["날짜", "활동명", "세부내용", "공지사항", "사진1", "사진2", "사진3", "사진4", "등록일"])
            a_vals = ws_a.get_all_values()
            
        df_a = pd.DataFrame(a_vals[1:], columns=a_vals[0]) if len(a_vals) > 1 else pd.DataFrame()
        df_a['sheet_row'] = range(2, len(df_a) + 2)
        
        # 3. 주차별통계 시트 (신규 추가: 에러 나지 않게 안전하게 생성)
        try:
            ws_s = sh.worksheet("주차별통계")
        except:
            ws_s = sh.add_worksheet(title="주차별통계", rows="100", cols="10")
            ws_s.append_row(["주차", "대상인원", "출석", "결석", "기타인원", "총합계", "출석률", "업데이트일시"])
        s_vals = ws_s.get_all_values()
        df_s = pd.DataFrame(s_vals[1:], columns=s_vals[0]) if len(s_vals) > 1 else pd.DataFrame()
        
        return ws_m, df_m, headers, ws_a, df_a, ws_s, df_s
    except Exception as e:
        st.error(f"데이터 연동 에러: {e}")
        return None, pd.DataFrame(), [], None, pd.DataFrame(), None, pd.DataFrame()

ws, df, headers, ws_act, df_act, ws_stat, df_stat = get_all_data()

# --- 3. 공통 함수 ---
def upload_photo(file, name):
    if not file: return ""
    try:
        b64 = base64.b64encode(file.getvalue()).decode()
        res = requests.post(GOOGLE_PROXY_URL, json={"fileName": f"{name}_{file.name}", "mimeType": file.type, "base64Data": b64}).json()
        return res.get("fileUrl", "")
    except: return ""

class_col = '학년(담임)' if '학년(담임)' in df.columns else ('반' if '반' in df.columns else '')

# --- 4. 주차 및 날짜 세팅 ---
start_date = datetime.date(2026, 1, 4)
weeks_list = [f"{i}주" for i in range(1, 53)]
week_display_map = {f"{i}주": f"{i}주 ({ (start_date + datetime.timedelta(days=(i-1)*7)).strftime('%m/%d') })" for i in range(1, 53)}

# --- 5. 화면 탭 구성 ---
st.title("🌱 유년부 통합 관리 시스템 v26.0")
tabs = st.tabs(["✅ 출석체크", "📋 교적부", "🏫 반편성", "🎂 생일표", "🌱 새친구", "⚙️ 행사"])

if df.empty:
    st.warning("데이터를 불러오지 못했습니다. 구글 시트를 확인해주세요.")
    st.stop()

# ==========================================
# [탭 1] 출석체크 (🚀 최신 모바일 UI 전면 개편)
# ==========================================
with tabs[0]:
    st.subheader("📅 주간 출석 & 통계 관리")
    
    # 1. 주차 및 반 필터
    curr_week_idx = datetime.date.today().isocalendar()[1] - 1
    col1, col2 = st.columns(2)
    with col1:
        sel_w = st.selectbox("출석 기록 주차 (날짜)", weeks_list, index=max(0, min(51, curr_week_idx)), format_func=lambda x: week_display_map[x])
    with col2:
        classes = ["전체보기"] + sorted([str(c) for c in df[class_col].unique() if str(c).strip()])
        sel_class = st.selectbox("반 필터", classes)

    att_df = df[df['학교상태'] != '이사'].copy()
    if sel_class != "전체보기": att_df = att_df[att_df[class_col] == sel_class]
    if sel_w not in att_df.columns: att_df[sel_w] = ""

    # 2. 실시간 통계 및 기타 인원 입력
    total_reg = len(att_df)
    present_count = len(att_df[att_df[sel_w].astype(str).str.strip() == "1"])
    
    # 기존에 저장된 기타인원 불러오기
    saved_guest = 0
    if not df_stat.empty and '주차' in df_stat.columns:
        match_stat = df_stat[df_stat['주차'] == sel_w]
        if not match_stat.empty:
            try: saved_guest = int(match_stat.iloc[0]['기타인원'])
            except: pass

    st.markdown("---")
    st.write("📊 **이번 주 요약 대시보드**")
    c_stat1, c_stat2, c_stat3, c_stat4 = st.columns(4)
    with c_stat1: st.metric("대상 인원", f"{total_reg}명")
    with c_stat2: st.metric("현재 출석", f"{present_count}명")
    with c_stat3: guest_input = st.number_input("기타 방문 인원", min_value=0, value=saved_guest, step=1)
    with c_stat4: st.metric("총 합계 (출석+기타)", f"{present_count + guest_input}명")

    # 3. 모바일 최적화 출석부 (반별 그룹핑 + 토글 스위치)
    st.markdown("---")
    st.write(f"### 📱 **{week_display_map[sel_w]} 모바일 출석부**")
    
    with st.form("att_toggle_form"):
        new_att_status = {}
        grouped_att = att_df.sort_values(by=['이름']).groupby(class_col)
        
        # 반별로 구역을 나누어 세련되게 출력
        for class_name, group in sorted(grouped_att):
            st.markdown(f"<div class='class-header'>🏷️ {class_name} ({len(group)}명)</div>", unsafe_allow_html=True)
            cols = st.columns(3)
            for i, (idx, row) in enumerate(group.iterrows()):
                with cols[i % 3]:
                    is_on = True if str(row.get(sel_w, "")).strip() == "1" else False
                    label = f"🌱 {row['이름']}" if row.get('학교상태') == '새친구' else row['이름']
                    # 최신식 토글 스위치 적용!
                    new_att_status[row['sheet_row']] = st.toggle(label, value=is_on, key=f"tgl_{row['sheet_row']}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.form_submit_button("💾 출석 및 주간 통계 통합 저장", type="primary", use_container_width=True):
            with st.spinner("구글 시트에 기록 중입니다..."):
                # A. 출석 데이터 저장
                target_col_idx = headers.index(sel_w) + 1 if sel_w in headers else len(headers) + 1
                if sel_w not in headers: ws.update_cell(1, target_col_idx, sel_w)
                
                final_present = 0
                for r_idx, val in new_att_status.items():
                    ws.update_cell(r_idx, target_col_idx, "1" if val else "")
                    if val: final_present += 1

                # B. 주차별 통계 시트 저장
                target_stat_row = -1
                if not df_stat.empty and '주차' in df_stat.columns:
                    match = df_stat[df_stat['주차'] == sel_w]
                    if not match.empty:
                        target_stat_row = match.index[0] + 2 # 헤더가 1번줄이므로 index+2
                
                rate = int((final_present / total_reg) * 100) if total_reg > 0 else 0
                now_str = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
                stat_data = [sel_w, total_reg, final_present, total_reg - final_present, guest_input, final_present + guest_input, f"{rate}%", now_str]
                
                if target_stat_row != -1:
                    ws_stat.update(f"A{target_stat_row}:H{target_stat_row}", [stat_data])
                else:
                    ws_stat.append_row(stat_data)

                st.success("출석과 통계가 완벽하게 저장되었습니다!")
                st.rerun()

    st.markdown("---")
    
    # 4. 연간 데이터 체크박스(Checkbox) 에디터 변환 (나이스한 UI)
    with st.expander("📊 1년 전체 출석부 한눈에 보기 및 일괄 수정", expanded=False):
        st.write("💡 아래 표의 **체크박스를 클릭**하여 쉽게 수정할 수 있습니다. (숫자 1을 입력할 필요가 없습니다!)")
        week_cols = [f"{i}주" for i in range(1, 53) if f"{i}주" in df.columns]
        annual_df = df[df['학교상태'] != '이사'][[class_col, '이름', 'sheet_row'] + week_cols].copy()
        
        # 숫자 '1'을 파이썬의 True/False(체크박스)로 변환
        bool_df = annual_df.copy()
        for w in week_cols:
            bool_df[w] = bool_df[w].apply(lambda x: True if str(x).strip() == "1" else False)
            
        # 열(Column) 설정: 이름과 반은 수정 불가, 주차는 체크박스
        cfg = {
            class_col: st.column_config.TextColumn("반", disabled=True),
            '이름': st.column_config.TextColumn("이름", disabled=True),
            'sheet_row': None # 행번호 숨기기
        }
        for w in week_cols:
            cfg[w] = st.column_config.CheckboxColumn(w, default=False)
            
        edited_bool = st.data_editor(bool_df, column_config=cfg, use_container_width=True, hide_index=True)
        
        if st.button("📝 연간 출석부 수정사항 서버에 반영"):
            with st.spinner("대규모 업데이트 중..."):
                for r in range(len(annual_df)):
                    for w in week_cols:
                        old_v = True if str(annual_df.iloc[r][w]).strip() == "1" else False
                        new_v = edited_bool.iloc[r][w]
                        if old_v != new_v:
                            row_idx = annual_df.iloc[r]['sheet_row']
                            col_idx = headers.index(w) + 1
                            ws.update_cell(row_idx, col_idx, "1" if new_v else "")
                st.success("연간 출석부 업데이트가 완료되었습니다!")
                st.rerun()

# ==========================================
# [탭 2] 교적부 관리 (다른 탭 건드리지 않음! 이전 코드 100% 동일 유지)
# ==========================================
with tabs[1]:
    st.subheader("📋 교적부 통합 데이터베이스")
    manage_mode = st.radio("작업 모드 선택", ["👀 전체 명단 보기", "📝 개별 상세 조회 및 수정/삭제", "➕ 신규 인원 추가"], horizontal=True)
    req_cols = ['학년(담임)', '이름', '사진', '생년월일', '주소', '부모(아빠/엄마)', '연락처', '학교상태', '비고', '전도자']
    available_cols = [c for c in req_cols if c in df.columns]

    st.markdown("---")
    if manage_mode == "👀 전체 명단 보기":
        st.write(f"현재 등록된 총 인원: **{len(df)}명**")
        st.dataframe(df[available_cols], use_container_width=True, hide_index=True, column_config={"사진": st.column_config.ImageColumn("사진")})

    elif manage_mode == "📝 개별 상세 조회 및 수정/삭제":
        search_list = df.apply(lambda r: f"{r['이름']} | {r.get(class_col, '')}", axis=1).tolist()
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
                    e_photo = st.file_uploader("사진 변경 (유지하려면 비워두세요)", type=["jpg", "png", "jpeg"])
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
        with st.form("add_member_form_safe", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                n_class = st.text_input("학년(담임) (필수)", placeholder="예: 1-1(권은주)")
                n_name = st.text_input("이름 (필수)")
                n_birth = st.text_input("생년월일", placeholder="예: 19.02.26")
                n_parents = st.text_input("부모(아빠/엄마)")
                n_phone = st.text_input("연락처", placeholder="예: 010-1234-5678")
            with col2:
                n_addr = st.text_input("주소")
                n_status = st.selectbox("학교상태", ["일반", "새친구", "이사", "교사"], index=1)
                n_memo = st.text_input("비고")
                n_evangelist = st.text_input("전도자")
                n_photo = st.file_uploader("사진 첨부", type=["jpg", "png", "jpeg"])
            if st.form_submit_button("✨ 등록하기", use_container_width=True):
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
                        st.success("등록 완료!"); st.rerun()

# ==========================================
# [탭 3] 반편성 현황 (이전 코드 100% 동일 유지)
# ==========================================
with tabs[2]:
    st.subheader("🏫 반별 명단 현황")
    grouped = df[df['학교상태'] != '이사'].groupby(class_col)
    cols = st.columns(3)
    for i, (name, group) in enumerate(grouped):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{name}** ({len(group)}명)")
                st.write(", ".join([f"🔴{n}" if s == '새친구' else n for n, s in zip(group['이름'], group['학교상태'])]))

# ==========================================
# [탭 4] 월별 생일표 (모바일 정렬 완벽 해결 & 최신 UI)
# ==========================================
with tabs[3]:
    st.subheader("🎂 월별 생일 명단")
    st.info("💡 모바일에서도 1월부터 12월까지 순서대로, 날짜(일)가 빠른 순으로 예쁘게 정렬되어 보입니다.")
    
    # 1. 월별 데이터 수집 (날짜 정렬을 위해 딕셔너리 리스트로 저장)
    b_map = {i: [] for i in range(1, 13)}
    
    for _, r in df.iterrows():
        b = str(r.get('생년월일', ''))
        if len(b.split('.')) >= 3:
            try: 
                m = int(b.split('.')[1])
                d = int(b.split('.')[2])
                if 1 <= m <= 12:
                    b_map[m].append({
                        "name": str(r.get('이름', '')), 
                        "class": str(r.get(class_col, '')), 
                        "day": d
                    })
            except: 
                pass
                
    # 2. 모바일 세로 엉킴 방지: 가로(Row) 단위로 묶어서 그리기
    for row_idx in range(4):  # 4줄 (4 x 3칸 = 12개월)
        cols = st.columns(3)
        for col_idx in range(3):
            m = row_idx * 3 + col_idx + 1
            with cols[col_idx]:
                with st.container(border=True):
                    # 세련된 카드 헤더
                    st.markdown(f"<h4 style='color:#0366d6; margin-bottom:0;'>📅 {m}월</h4>", unsafe_allow_html=True)
                    st.divider() # 깔끔한 가로선
                    
                    # 해당 월의 생일자들을 날짜(일) 순으로 오름차순 정렬
                    sorted_bdays = sorted(b_map[m], key=lambda x: x["day"])
                    
                    if sorted_bdays:
                        for p in sorted_bdays:
                            # 이름, 반, 날짜를 가독성 좋게 출력
                            st.markdown(
                                f"🎈 **{p['name']}** <span style='font-size:0.9em; color:#666;'>({p['class']})</span> &nbsp;→&nbsp; <span style='color:#e65100; font-weight:bold;'>{p['day']}일</span>", 
                                unsafe_allow_html=True
                            )
                    else:
                        st.caption("생일자 없음")
# ==========================================
# [탭 5] 새친구 목록 (이전 코드 100% 동일 유지)
# ==========================================
with tabs[4]:
    st.subheader("🌱 최근 등록 새친구")
    news = df[df['학교상태'] == '새친구']
    if not news.empty:
        st.dataframe(news[available_cols], use_container_width=True, hide_index=True)
    else:
        st.info("등록된 새친구가 없습니다.")

# ==========================================
# [탭 6] 행사 및 활동 관리 (이전 코드 100% 동일 유지)
# ==========================================
with tabs[5]:
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
    with st.expander("➕ 활동 추가"):
        with st.form("new_act"):
            d = st.date_input("날짜"); t = st.text_input("활동명"); desc = st.text_area("내용"); files = st.file_uploader("사진", accept_multiple_files=True)
            if st.form_submit_button("저장"):
                urls = ["", "", "", ""]; [urls.__setitem__(i, upload_photo(f, t)) for i, f in enumerate(files[:4])]
                ws_act.append_row([str(d), t, desc, "", urls[0], urls[1], urls[2], urls[3], str(datetime.datetime.now())])
                st.success("저장 완료!"); st.rerun()
