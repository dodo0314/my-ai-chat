import streamlit as st
import os
import json
import uuid
import time
from datetime import datetime
from openai import OpenAI

# ==========================================
# [설정] API 키 및 모델 리스트
# ==========================================
API_KEY = st.secrets["MY_API_KEY"]
SAVE_FOLDER = "chat_multi_data"

MODEL_OPTIONS = {
    "DeepSeek V3.2": "deepseek/deepseek-v3.2",
    "Sonnet 4.5": "anthropic/claude-sonnet-4.5", 
    "Grok-4.1": "x-ai/grok-4.1-fast",
    "Gemini 2.0_Free": "google/gemini-2.0-flash-exp:free",
    "mimo": "xiaomi/mimo-v2-flash:free",
}

if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)

# ==========================================
# [함수] 데이터 관리
# ==========================================
def load_chat(filename):
    if not filename: return []
    filepath = os.path.join(SAVE_FOLDER, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_chat(filename, history):
    filepath = os.path.join(SAVE_FOLDER, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_chat_files():
    if not os.path.exists(SAVE_FOLDER): return []
    files = [f for f in os.listdir(SAVE_FOLDER) if f.endswith(".json")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SAVE_FOLDER, x)), reverse=True)
    return files

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

# ==========================================
# [UI] 화면 구성
# ==========================================
st.set_page_config(page_title="멀티 그리드 챗봇", layout="wide")

with st.sidebar:
    st.title("🎛️ 멀티 컨트롤")
    
    # 1. 초기화 로직
    files = get_chat_files()
    if not files:
        init_file = f"New_Chat_{uuid.uuid4().hex[:4]}.json"
        save_chat(init_file, [])
        st.session_state["multi_chat_file"] = init_file
        st.rerun()
    
    if "multi_chat_file" not in st.session_state:
        st.session_state["multi_chat_file"] = files[0]

    # 2. 화면 설정 (탭 모드 추가됨!)
    st.subheader("1. 화면 설정")
    num_screens = st.radio("화면 분할 개수", [1, 2, 3, 4], horizontal=True, index=0)
    
    # ⭐ [NEW] 모바일용 탭 모드 스위치
    use_tabs = st.toggle("📱 모바일 탭 모드 (세로형)", value=False)
    
    st.divider()
    
    # 3. 모델 배정
    st.subheader("2. 모델 배정")
    selected_models = []
    model_names = list(MODEL_OPTIONS.keys())
    
    for i in range(num_screens):
        default_idx = i % len(model_names)
        model_name = st.selectbox(
            f"📺 화면 {i+1} 모델", 
            model_names, 
            index=default_idx,
            key=f"model_select_{i}"
        )
        selected_models.append(MODEL_OPTIONS[model_name])

    st.divider()
    
    # 4. 채팅방 목록
    st.subheader("3. 채팅방 목록")
    if st.button("➕ 새 채팅 만들기", use_container_width=True):
        new_filename = f"New_Chat_{uuid.uuid4().hex[:4]}.json"
        save_chat(new_filename, [])
        st.session_state["multi_chat_file"] = new_filename
        st.rerun()

    files = get_chat_files()
    if st.session_state["multi_chat_file"] not in files and files:
         st.session_state["multi_chat_file"] = files[0]

    if files:
        current_file = st.radio("대화 선택", files, index=files.index(st.session_state["multi_chat_file"]) if st.session_state["multi_chat_file"] in files else 0, label_visibility="collapsed")
        if current_file != st.session_state["multi_chat_file"]:
            st.session_state["multi_chat_file"] = current_file
            st.rerun()
            
        st.markdown("---")
        st.caption("📝 이름 변경")
        current_filename = st.session_state["multi_chat_file"]
        new_name_input = st.text_input("파일명 수정", value=current_filename.replace(".json", ""), label_visibility="collapsed")
        
        if st.button("이름 변경 적용"):
            old_path = os.path.join(SAVE_FOLDER, current_filename)
            new_path = os.path.join(SAVE_FOLDER, f"{new_name_input}.json")
            if os.path.exists(new_path) and new_path != old_path:
                st.error("이미 존재하는 이름입니다.")
            else:
                os.rename(old_path, new_path)
                st.session_state["multi_chat_file"] = f"{new_name_input}.json"
                st.success("변경 완료!")
                time.sleep(0.5)
                st.rerun()

# 메인 화면
safe_filename = st.session_state.get("multi_chat_file", "새 채팅")
st.title(f"🧩 {safe_filename.replace('.json', '')}")

history = load_chat(st.session_state.get("multi_chat_file"))

# ==========================================
# [기록 렌더링] 탭 모드 적용
# ==========================================
for turn in history:
    with st.chat_message("user"):
        st.markdown(turn["user"])
    
    # ⭐ 여기가 핵심 변경 포인트 (1)
    if use_tabs:
        containers = st.tabs([f"화면 {i+1}" for i in range(num_screens)])
    else:
        containers = st.columns(num_screens)

    for i in range(num_screens):
        with containers[i]:
            resp_data = turn.get("responses", {}).get(str(i))
            if resp_data:
                tokens = resp_data.get('usage', {}).get('total_tokens', 'N/A')
                st.caption(f"🤖 {resp_data.get('model_name', 'AI')} | 🪙 Tokens: {tokens}")
                
                if "Error" in resp_data['text']:
                    st.error(resp_data['text'])
                else:
                    st.info(resp_data['text'])

# ==========================================
# [입력 및 실행] 탭 모드 적용
# ==========================================
if prompt := st.chat_input("질문하기..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # ⭐ 여기가 핵심 변경 포인트 (2)
    if use_tabs:
        containers = st.tabs([f"화면 {i+1}" for i in range(num_screens)])
    else:
        containers = st.columns(num_screens)

    current_turn_responses = {}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for i in range(num_screens):
        with containers[i]:
            model_id = selected_models[i]
            display_name = [k for k, v in MODEL_OPTIONS.items() if v == model_id][0]
            
            st.caption(f"🏃 Running: {display_name}...")
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
                        usage_info = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }

                msg_placeholder.info(full_text)
                
                current_turn_responses[str(i)] = {
                    "timestamp": timestamp,
                    "model_name": display_name,
                    "model_id": model_id,
                    "text": full_text,
                    "usage": usage_info
                }
            except Exception as e:
                err_msg = f"Error: {e}"
                msg_placeholder.error(err_msg)
                current_turn_responses[str(i)] = {
                    "timestamp": timestamp,
                    "model_name": display_name,
                    "model_id": model_id,
                    "text": err_msg,
                    "usage": {"error": str(e)}
                }

    if st.session_state.get("multi_chat_file"):
        new_turn = {"user": prompt, "responses": current_turn_responses}
        history.append(new_turn)

        save_chat(st.session_state["multi_chat_file"], history)

