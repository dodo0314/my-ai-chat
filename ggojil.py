import streamlit as st
import google.generativeai as genai
from PIL import Image

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="꼬질이 탐지기",
    page_icon="🐶",
    layout="centered"
)

# 제목 및 설명
st.title("🐶 꼬질이 탐지기")
st.write("우리 집 강아지, 지금 미용해야 할까요? AI 전문가가 냉정하게 판단해 드립니다!")

# 2. API 키 설정 (Streamlit Secrets에서 가져오기)
# 배포 후 Settings -> Secrets 에 GEMINI_API_KEY를 등록해야 합니다.
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    # 로컬 테스트용 또는 키 미설정 시
    api_key = st.text_input("Gemini API 키를 입력하세요", type="password")

if api_key:
    genai.configure(api_key=api_key)

    # 3. 이미지 업로드
    uploaded_file = st.file_uploader("강아지의 정면 또는 측면 사진을 올려주세요 📸", type=["jpg", "jpeg", "png"])

    if uploaded_file is not None:
        # 이미지 화면에 표시
        image = Image.open(uploaded_file)
        st.image(image, caption='분석 대기 중...', use_container_width=True)

        # 분석 버튼
        if st.button("🔍 꼬질도 진단 시작"):
            with st.spinner("AI 원장님이 돋보기 쓰고 보는 중..."):
                try:
                    # 모델 호출 (속도 빠른 1.5 Flash 사용)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # 프롬프트: 페르소나와 분석 기준 설정
                    prompt = """
                    너는 20년 경력의 세계적인 반려견 미용 전문가야. 
                    말투는 약간 까칠하고 직설적이지만, 강아지를 걱정하는 마음이 깔려있어.
                    
                    이 사진을 보고 다음 항목을 분석해줘:
                    
                    1. **꼬질 지수 (0~100점)**: 
                       - 100점에 가까울수록 털이 엉망이고 미용이 시급한 상태.
                       - 30점 이하는 깔끔한 상태.
                       
                    2. **상태 분석**:
                       - 눈 주변 털이 시야를 가리는지
                       - 털 엉킴이 보이는지
                       - 빗질이 필요한지 등
                       
                    3. **원장님의 한마디**:
                       - 견주에게 전하는 재치 있는 독설 혹은 칭찬.
                       
                    출력 형식은 반드시 아래와 같은 마크다운 포맷을 지켜줘:
                    
                    ## 📊 꼬질 지수: OO점
                    ### 🩺 상태 진단
                    (여기에 구체적인 분석 내용)
                    
                    ### 💬 원장님의 한마디
                    "..."
                    """
                    
                    # AI 응답 생성
                    response = model.generate_content([prompt, image])
                    st.markdown(response.text)
                    
                    # --- [Phase 2] 추후 지도 기능이 들어갈 자리 ---
                    # 만약 점수가 높으면 주변 미용실 검색 버튼 노출 로직 추가 예정
                    # ---------------------------------------------

                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")
                    st.info("API 키가 정확한지, 혹은 이미지가 손상되지 않았는지 확인해주세요.")
else:
    st.info("👈 먼저 API 키를 설정해주세요. (배포 시 Secrets 설정 권장)")

# 하단 푸터
st.markdown("---")
st.caption("Powered by Google Gemini 1.5 Flash & Streamlit")