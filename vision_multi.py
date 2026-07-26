import streamlit as st
import pandas as pd
from PIL import Image
from io import BytesIO
import google.generativeai as genai
import anthropic
import base64
from streamlit_paste_button import paste_image_button
import re

# ==========================================
# 0. 엑셀 변환 로직 (Markdown Table -> Excel)
# ==========================================
def md_to_excel(md_str):
    try:
        lines = md_str.strip().split('\n')
        data_lines = []
        for line in lines:
            line = line.strip()
            if not line or '|' not in line: continue
            content = line.replace('|', '').strip()
            if set(content).issubset({'-', ':', ' '}): continue
            data_lines.append(line)
        
        if len(data_lines) < 2: return None
        
        parsed = []
        for line in data_lines:
            if line.startswith('|'): line = line[1:]
            if line.endswith('|'): line = line[:-1]
            parsed.append([c.strip() for c in line.split('|')])
            
        df = pd.DataFrame(parsed[1:], columns=parsed[0])
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Result')
        return output.getvalue()
    except Exception as e:
        return None

# ==========================================
# 1. 초기 세팅
# ==========================================
def init_app():
    st.set_page_config(page_title="실무 기획/QA 추출기", layout="wide")
    st.title("⚡ 실무 기획 & TC 추출기 v4")
    
    if 'tab1_imgs' not in st.session_state: st.session_state['tab1_imgs'] = []
    if 'tab1_res' not in st.session_state: st.session_state['tab1_res'] = None
    
    if 'tab2_imgs' not in st.session_state: st.session_state['tab2_imgs'] = []
    if 'tab2_res' not in st.session_state: st.session_state['tab2_res'] = None

# ==========================================
# 2. 개별 이미지 삭제 UI 생성 함수 (신규)
# ==========================================
def display_images_with_delete(state_key):
    imgs_list = st.session_state[state_key]
    if not imgs_list: return
    
    # 한 줄에 최대 5개씩 쪼개서 배치 (가독성 방어 및 개별 삭제 버튼 부여)
    cols_per_row = 5
    for i in range(0, len(imgs_list), cols_per_row):
        row_imgs = imgs_list[i:i+cols_per_row]
        cols = st.columns(cols_per_row)
        for j, img in enumerate(row_imgs):
            idx = i + j
            with cols[j]:
                st.image(img, use_container_width=True, caption=f"첨부 {idx+1}")
                if st.button("❌ 삭제", key=f"del_{state_key}_{idx}", use_container_width=True):
                    st.session_state[state_key].pop(idx)
                    st.rerun()

# ==========================================
# 3. AI 호출 로직 (Gemini 모델명 패치)
# ==========================================
def run_gemini(api_key, prompt, images=[]):
    genai.configure(api_key=api_key)
    # 404 에러 방지: 구글 최신 강제 규격 반영
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
    response = model.generate_content([prompt] + images)
    return response.text

def run_claude(api_key, prompt, images=[]):
    client = anthropic.Anthropic(api_key=api_key)
    content = []
    for img in images:
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}})
    content.append({"type": "text", "text": prompt})
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}]
    )
    return response.content[0].text

def generate_content(model, gemini_key, claude_key, prompt, images):
    if not images:
        raise Exception("이미지를 최소 1장 이상 첨부해야 합니다.")
    
    if "Claude" in model:
        if not claude_key: raise Exception("Claude API 키를 입력하세요.")
        return run_claude(claude_key, prompt, images)
    else:
        if not gemini_key: raise Exception("Gemini API 키를 입력하세요.")
        return run_gemini(gemini_key, prompt, images)

# ==========================================
# 4. 결과 출력 컴포넌트
# ==========================================
def display_results(result_text, key_prefix):
    st.success("✅ 추출 완료!")
    excel_data = md_to_excel(result_text)
    if excel_data:
        st.download_button(
            "📊 엑셀 파일로 다운로드", 
            data=excel_data, file_name="기획_TC_추출결과.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            key=f"{key_prefix}_dl"
        )
    st.divider()
    col_preview, col_copy = st.columns(2)
    with col_preview:
        st.markdown("### 👀 화면 미리보기")
        st.markdown(result_text)
    with col_copy:
        st.markdown("### 📋 복사(Ctrl+C) 전용 텍스트")
        st.caption("아래 입력창 안을 클릭하고 `Ctrl+A` (전체선택) 후 `Ctrl+C` 하시면 깔끔하게 복사됩니다.")
        st.text_area("결과 텍스트", value=result_text, height=400, key=f"{key_prefix}_copy", label_visibility="collapsed")

# ==========================================
# 5. 메인 UI
# ==========================================
def main():
    init_app()
    with st.sidebar:
        st.header("🔑 API 키 설정")
        gemini_key = st.text_input("Gemini API Key", type="password")
        claude_key = st.text_input("Claude API Key", type="password")

    tab1, tab2 = st.tabs(["🖼️ 1. 빠른 초안 (이미지 전용)", "📝 2. 정밀 분석 (정책 + 이미지)"])

    # ------------------------------------------
    # TAB 1: 이미지 전용 모드
    # ------------------------------------------
    with tab1:
        st.markdown("디자인 시안 캡처본만으로 기획 명세서나 TC 초안을 엑셀로 뽑아냅니다.")
        c_btn, c_clear = st.columns([1, 4])
        with c_btn:
            paste_res1 = paste_image_button(label="📋 화면 붙여넣기", background_color="#FF4B4B", key="btn1")
        with c_clear:
            if st.button("🗑️ 이미지 전체 비우기", key="clear1"):
                st.session_state['tab1_imgs'] = []
                st.rerun()

        # 중복 이미지 도배 방지 로직 (마지막 추가된 이미지와 다를 때만 append)
        if paste_res1.image_data is not None:
            if not st.session_state['tab1_imgs'] or st.session_state['tab1_imgs'][-1] != paste_res1.image_data:
                st.session_state['tab1_imgs'].append(paste_res1.image_data)
                
        # 개별 삭제 버튼이 포함된 이미지 그리드 호출
        display_images_with_delete('tab1_imgs')
        
        st.divider()
        model_t1 = st.radio("🧠 AI 뇌 선택:", ["Claude 3.5 Sonnet (논리력 최강)", "Gemini 1.5 Pro (속도/가성비)"], horizontal=True, key="mod1")
        
        c1, c2 = st.columns(2)
        if c1.button("📄 기능 명세서 뽑기", use_container_width=True, type="primary"):
            prompt = "첨부된 UI 이미지들을 분석하여 기능 명세서를 Markdown 표로 작성해. 컬럼: No, 화면명, UI요소, 타입, 기능상세, 정책. 쓸데없는 설명 없이 마크다운 표만 출력해."
            with st.spinner("명세서 뽑는 중..."):
                try: st.session_state['tab1_res'] = generate_content(model_t1, gemini_key, claude_key, prompt, st.session_state['tab1_imgs'])
                except Exception as e: st.error(e)
                    
        if c2.button("🧪 TC 뽑기", use_container_width=True, type="primary"):
            prompt = "첨부된 UI 이미지들을 분석하여 테스트 케이스(TC)를 Markdown 표로 작성해. 예외/에지 케이스도 집요하게 포함시켜. 컬럼: ID, 화면구분, 테스트 항목, 사전 조건, 테스트 스텝, 기대 결과. 쓸데없는 설명 없이 마크다운 표만 출력해."
            with st.spinner("TC 뽑는 중..."):
                try: st.session_state['tab1_res'] = generate_content(model_t1, gemini_key, claude_key, prompt, st.session_state['tab1_imgs'])
                except Exception as e: st.error(e)

        if st.session_state['tab1_res']:
            display_results(st.session_state['tab1_res'], "tab1")

    # ------------------------------------------
    # TAB 2: 정책 + 이미지 모드
    # ------------------------------------------
    with tab2:
        st.markdown("컨플루언스 정책과 피그마 화면을 교차 검증하여 결함 없는 명세서나 TC를 뽑아냅니다.")
        col_req, col_img = st.columns(2)
        with col_req:
            req_text = st.text_area("기획 명세서 / 정책 복붙", height=300)
        with col_img:
            c_btn2, c_clear2 = st.columns([1, 1])
            with c_btn2:
                paste_res2 = paste_image_button(label="📋 화면 붙여넣기", background_color="#2E86C1", key="btn2")
            with c_clear2:
                if st.button("🗑️ 비우기", key="clear2"):
                    st.session_state['tab2_imgs'] = []
                    st.rerun()
                    
            if paste_res2.image_data is not None:
                if not st.session_state['tab2_imgs'] or st.session_state['tab2_imgs'][-1] != paste_res2.image_data:
                    st.session_state['tab2_imgs'].append(paste_res2.image_data)
                
            # 개별 삭제 버튼이 포함된 이미지 그리드 호출
            display_images_with_delete('tab2_imgs')

        st.divider()
        model_t2 = st.radio("🧠 AI 뇌 선택:", ["Claude 3.5 Sonnet (논리력 최강)", "Gemini 1.5 Pro (속도/가성비)"], horizontal=True, key="mod2")
        
        c3, c4 = st.columns(2)
        if c3.button("📄 교차 검증 명세서 뽑기", use_container_width=True, type="primary"):
            if not req_text: st.warning("정책 텍스트를 입력하세요.")
            else:
                prompt = f"다음 [기획 정책]과 첨부된 [UI 이미지]를 교차 검증하여 기능 명세서를 Markdown 표로 작성해.\n[정책]\n{req_text}\n\n컬럼: No, 화면명, UI요소, 타입, 기능상세, 정책(이미지와 불일치하는 결함 지적 포함). 쓸데없는 설명 없이 표만 출력해."
                with st.spinner("명세서 뽑는 중..."):
                    try: st.session_state['tab2_res'] = generate_content(model_t2, gemini_key, claude_key, prompt, st.session_state['tab2_imgs'])
                    except Exception as e: st.error(e)
                    
        if c4.button("🧪 교차 검증 TC 뽑기", use_container_width=True, type="primary"):
            if not req_text: st.warning("정책 텍스트를 입력하세요.")
            else:
                prompt = f"다음 [기획 정책]과 첨부된 [UI 이미지]를 교차 검증하여 테스트 케이스(TC)를 Markdown 표로 작성해.\n[정책]\n{req_text}\n\n정상 동작뿐만 아니라 극단적 예외 케이스를 집요하게 파고들어. 컬럼: ID, 화면구분, 테스트 항목, 사전 조건, 테스트 스텝, 기대 결과. 쓸데없는 설명 없이 표만 출력해."
                with st.spinner("TC 뽑는 중..."):
                    try: st.session_state['tab2_res'] = generate_content(model_t2, gemini_key, claude_key, prompt, st.session_state['tab2_imgs'])
                    except Exception as e: st.error(e)

        if st.session_state['tab2_res']:
            display_results(st.session_state['tab2_res'], "tab2")

if __name__ == "__main__":
    main()
