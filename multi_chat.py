import streamlit as st
import json
import uuid
import time
import pandas as pd
import io
from datetime import datetime
from openai import OpenAI

# 구글 시트 연동 라이브러리
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# [설정]
# ==========================================
API_KEY = st.secrets["MY_API_KEY"]

MODEL_OPTIONS = {
    "DeepSeek V3.2": "deepseek/deepseek-v3.2",
    "Sonnet 4": "anthropic/claude-sonnet-4", 
    "Grok-4.1": "x-ai/grok-4.1-fast",
    "mimo": "xiaomi/mimo-v2-flash:free"
    "Gemini 2.0_Free": "google/gemini-2.0-flash-exp:free",
}

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)

# ==========================================
# [함수] 구글 시트 DB 관리 (핵심)
# ==========================================
@st.cache_resource
def get_google_sheet():
    # Secrets에서 키 정보를 가져옴
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"]) # Secrets 내용을 딕셔너리로 변환
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # 시트 이름으로 열기 (엑셀 파일명과 똑같아야 함)
    sh = client.open("dodochat_db") 
    return sh.sheet1

def load_all_chats_from_sheet():
    """시트에서 모든 채팅 목록을 불러옵니다."""
    try:
        sheet = get_google_sheet()
        # 모든 데이터 가져오기 (리스트 형태)
        data = sheet.get_all_records()
        # 데이터가 없으면 빈 리스트 반환
        if not data:
            return []
        
        # 최신순 정렬 (timestamp 기준 내림차순)
        # 엑셀에 저장될 때 문자열이므로 정렬이 필요하다면 여기서 처리
        data.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        return data
    except Exception as e:
        st.error(f"DB 로드 실패: {e}")
        return []

def save_chat_to_sheet(chat_id, title, history):
    """채팅 내용을 시트에 저장(없으면 생성, 있으면 수정)"""
    try:
        sheet = get_google_sheet()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_json = json.dumps(history, ensure_ascii=False)
        
        # [수정됨] 최신 gspread(6.0.0+) 대응: find는 이제 에러 대신 None을 줍니다.
        cell = sheet.find(chat_id)
        
        if cell:
            # ID를 찾았으면 -> 해당 줄 업데이트
            row = cell.row
            sheet.update_cell(row, 2, title)         # B열: 제목
            sheet.update_cell(row, 3, history_json)  # C열: 대화내용
            sheet.update_cell(row, 4, timestamp)     # D열: 수정시간
        else:
            # ID가 없으면(None) -> 새 줄 추가
            sheet.append_row([chat_id, title, history_json, timestamp])
            
    except Exception as e:
        # 그 외 진짜 에러(연결 끊김 등)는 여기서 잡습니다.
        st.warning(f"저장 중 오류 발생 (잠시 후 다시 시도됩니다): {e}")

# ==========================================
# [UI] 화면 구성
# ==========================================
st.set_page_config(page_title="DoDo Chat", page_icon="☁️", layout="wide")

# 세션 초기화 (현재 선택된 채팅방 ID)
if "current_chat_id" not in st.session_state:
    st.session_state["current_chat_id"] = None

def build_context(turn_history, slot_index):
    messages = []
    messages.append({"role": "system", "content": f"당신은 {slot_index+1}번 화면의 AI입니다."})
    for turn in turn_history:
        messages.append({"role": "user", "content": turn["user"]})
        responses = turn.get("responses", {})
        str_idx = str(slot_index)
        if str_idx in responses:
            messages.append({"role": "assistant", "content": responses[str_idx]["text"]})
    return messages

# 사이드바
with st.sidebar:
    st.title("🎛️ 클라우드 컨트롤")
    
    # 1. 화면 설정
    st.subheader("1. 화면 설정")
    num_screens = st.radio("화면 분할", [1, 2, 3, 4], horizontal=True, index=0)
    use_tabs = st.toggle("📱 모바일 탭 모드", value=False)
    
    st.divider()
    
    # 2. 모델 설정
    st.subheader("2. 모델 배정")
    selected_models = []
    model_names = list(MODEL_OPTIONS.keys())
    for i in range(num_screens):
        model_name = st.selectbox(f"화면 {i+1}", model_names, index=i % len(model_names), key=f"m_{i}")
        selected_models.append(MODEL_OPTIONS[model_name])

    st.divider()
    
    # 3. 채팅방 목록 (DB 연동)
    st.subheader("3. 채팅방")
    
    # [새 채팅]
    if st.button("➕ 새 채팅 시작", use_container_width=True):
        new_id = str(uuid.uuid4())[:8]
        new_title = f"새 대화 ({datetime.now().strftime('%m/%d %H:%M')})"
        # 빈 대화로 DB에 즉시 생성
        save_chat_to_sheet(new_id, new_title, [])
        st.session_state["current_chat_id"] = new_id
        st.rerun()

    # DB에서 목록 불러오기
    all_chats = load_all_chats_from_sheet()
    
    if all_chats:
        chat_options = {chat['chat_id']: chat['title'] for chat in all_chats}
        
        # 현재 ID가 유효한지 확인
        if st.session_state["current_chat_id"] not in chat_options:
            st.session_state["current_chat_id"] = all_chats[0]['chat_id']
            
        selected_id = st.radio(
            "목록", 
            list(chat_options.keys()), 
            format_func=lambda x: chat_options[x],
            index=list(chat_options.keys()).index(st.session_state["current_chat_id"]) if st.session_state["current_chat_id"] else 0
        )
        
        if selected_id != st.session_state["current_chat_id"]:
            st.session_state["current_chat_id"] = selected_id
            st.rerun()
            
        # [현재 대화 내용 가져오기]
        current_chat_data = next((item for item in all_chats if item["chat_id"] == st.session_state["current_chat_id"]), None)
        history = json.loads(current_chat_data['history']) if current_chat_data else []
        current_title = current_chat_data['title'] if current_chat_data else "제목 없음"
        
        st.divider()
        
        # [제목 변경 기능]
        new_name = st.text_input("제목 변경", value=current_title)
        if new_name != current_title:
             # 제목만 바뀌어도 DB 업데이트
             save_chat_to_sheet(st.session_state["current_chat_id"], new_name, history)
             st.rerun()

        # ⭐ [요건 3] 엑셀 다운로드 기능 (xlsx)
        st.caption("💾 내보내기")
        if history:
            # 엑셀용 데이터 프레임 생성
            excel_data = []
            for turn in history:
                row = {"User Question": turn['user']}
                for k, v in turn.get("responses", {}).items():
                    row[f"AI_{k}_Model"] = v.get("model_name", "")
                    row[f"AI_{k}_Answer"] = v.get("text", "")
                excel_data.append(row)
            
            df = pd.DataFrame(excel_data)
            
            # 엑셀 바이너리 변환
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Chat History')
                
            st.download_button(
                label="📥 엑셀(.xlsx)로 다운로드",
                data=buffer.getvalue(),
                file_name=f"{current_title}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    else:
        st.info("저장된 대화가 없습니다.")
        history = []
        current_title = "새 채팅"


# 메인 화면
st.title(f"☁️ {current_title}")

# 탭 모드 or 분할 모드
if use_tabs:
    containers = st.tabs([f"화면 {i+1}" for i in range(num_screens)])
else:
    containers = st.columns(num_screens)

# 대화 렌더링
for turn in history:
    with st.chat_message("user"):
        st.markdown(turn["user"])
    
    for i in range(num_screens):
        with containers[i]:
            resp_data = turn.get("responses", {}).get(str(i))
            if resp_data:
                tokens = resp_data.get('usage', {}).get('total_tokens', 'N/A')
                st.caption(f"🤖 {resp_data.get('model_name', 'AI')} | 🪙 {tokens}")
                if "Error" in resp_data['text']:
                    st.error(resp_data['text'])
                else:
                    st.info(resp_data['text'])

# 입력
if prompt := st.chat_input("질문하기..."):
    with st.chat_message("user"):
        st.markdown(prompt)
        
    current_turn_responses = {}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 컨테이너 다시 잡기 (입력 시)
    if use_tabs:
        containers = st.tabs([f"화면 {i+1}" for i in range(num_screens)])
    else:
        containers = st.columns(num_screens)

    for i in range(num_screens):
        with containers[i]:
            model_id = selected_models[i]
            display_name = [k for k, v in MODEL_OPTIONS.items() if v == model_id][0]
            
            st.caption(f"🏃 {display_name}...")
            msg_placeholder = st.empty()
            full_text = ""
            usage_info = {}
            
            context = build_context(history, i)
            context.append({"role": "user", "content": prompt})
            
            try:
                response = client.chat.completions.create(
                    model=model_id,
                    messages=context,
                    stream=True,
                    stream_options={"include_usage": True}
                )
                
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        full_text += chunk.choices[0].delta.content
                        msg_placeholder.info(full_text + "▌")
                    if chunk.usage:
                        usage_info = {"total_tokens": chunk.usage.total_tokens}

                msg_placeholder.info(full_text)
                
                current_turn_responses[str(i)] = {
                    "timestamp": timestamp,
                    "model_name": display_name,
                    "model_id": model_id,
                    "text": full_text,
                    "usage": usage_info
                }
            except Exception as e:
                msg_placeholder.error(f"Error: {e}")
                current_turn_responses[str(i)] = {
                    "text": f"Error: {e}",
                    "model_name": display_name
                }

    # ⭐ [요건 1, 2] 구글 시트에 즉시 저장
    if st.session_state.get("current_chat_id"):
        new_turn = {"user": prompt, "responses": current_turn_responses}
        history.append(new_turn)
        save_chat_to_sheet(st.session_state["current_chat_id"], current_title, history)


