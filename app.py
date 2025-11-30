import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import io
import time
import random
from pypdf import PdfReader

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="JLP x Google | Growth Engine",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. LUXURY RETAIL x GOOGLE CSS ---
st.markdown("""
<style>
    /* IMPORTS */
    @import url('https://fonts.googleapis.com/css2?family=Gill+Sans+MT&family=Google+Sans:wght@400;500;700&display=swap');

    /* BASE THEME */
    html, body, [class*="css"] {
        font-family: 'Google Sans', sans-serif;
        background-color: #ffffff;
        color: #1c1c1c;
    }

    /* REMOVE CLUTTER */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}

    /* CHAT INTERFACE */
    .stChatInput {
        border-radius: 30px !important;
        border: 1px solid #e0e0e0 !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .stChatMessage {
        background-color: #f8f9fa;
        border: none;
        border-radius: 12px;
        padding: 20px;
        font-size: 15px;
        line-height: 1.6;
    }
    
    /* LINK BUTTONS (CTA) */
    .file-link {
        display: inline-block;
        background-color: #1c1c1c; /* JLP Black */
        color: #ffffff !important;
        padding: 12px 24px;
        border-radius: 0px; 
        text-decoration: none;
        font-weight: 500;
        font-size: 14px;
        letter-spacing: 1px;
        margin-top: 15px;
        transition: all 0.3s ease;
        text-transform: uppercase;
    }
    .file-link:hover {
        background-color: #4285F4;
        box-shadow: 0 4px 10px rgba(66, 133, 244, 0.3);
        transform: translateY(-2px);
    }

    /* SIDEBAR CARD */
    .tip-card {
        background-color: #f4f4f4;
        padding: 20px;
        border-left: 4px solid #4285F4;
        margin-bottom: 20px;
        border-radius: 0 8px 8px 0;
    }
    
    /* JLP LOGO RECREATION (CSS) */
    .jlp-logo-box {
        font-family: 'Gill Sans', 'Gill Sans MT', Calibri, sans-serif;
        color: #000;
        text-align: right;
        line-height: 1;
        text-transform: uppercase;
    }
    .jlp-main {
        font-size: 32px;
        font-weight: 600;
        letter-spacing: 2px;
        display: block;
    }
    .jlp-sub {
        font-size: 14px;
        font-weight: 400;
        letter-spacing: 3px;
        margin-top: 5px;
        display: block;
    }
    
    /* VERTICAL ALIGNMENT HELPER */
    div[data-testid="column"] {
        display: flex;
        align-items: center; 
        justify-content: center;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. CREDENTIALS ---
FOLDER_ID = "1km4pPoH4Gqa47Aug0tW1DR4ElkRvh72k" 
GEMINI_API_KEY = "AIzaSyB4ZO0yEI2ApKb4XBKN1idyUEjav8FuFCI"
CLIENT_PASSWORD = "Google2025!" 

# --- 4. BACKEND LOGIC ---
@st.cache_resource
def get_drive_service():
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    if os.path.exists("service_account.json"):
        creds = service_account.Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
    elif "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    else: return None
    return build('drive', 'v3', credentials=creds)

def get_working_model():
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in all_models:
            if 'flash' in m.lower() and '8b' not in m.lower(): return genai.GenerativeModel(m)
        for m in all_models:
            if 'pro' in m.lower() and 'exp' not in m.lower(): return genai.GenerativeModel(m)
        return genai.GenerativeModel('gemini-1.5-flash-001')
    except: return genai.GenerativeModel('gemini-1.5-flash-001')

def list_files(service, folder_id):
    try:
        results = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="files(id, name, mimeType, webViewLink)").execute()
        return results.get('files', [])
    except: return []

def read_file(service, file_id, mime_type):
    try:
        content = None; data_type = "unknown"
        if "spreadsheet" in mime_type or mime_type.endswith("sheet"):
            if "application/vnd.google-apps.spreadsheet" in mime_type:
                request = service.files().export_media(fileId=file_id, mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else: request = service.files().get_media(fileId=file_id)
            data = request.execute()
            content = pd.read_excel(io.BytesIO(data))
            data_type = "dataframe"
        elif "presentation" in mime_type or "pdf" in mime_type:
            if "presentation" in mime_type: request = service.files().export_media(fileId=file_id, mimeType="application/pdf")
            else: request = service.files().get_media(fileId=file_id)
            data = request.execute()
            reader = PdfReader(io.BytesIO(data))
            text = "".join([page.extract_text() + "\n" for page in reader.pages])
            content = text
            data_type = "text"
        return content, data_type
    except: return None, "error"

def find_best_file_local(user_query, file_list):
    query_words = user_query.lower().split()
    best_file = None; best_score = 0
    for f in file_list:
        score = 0; name = f['name'].lower()
        for word in query_words:
            if word in name and len(word) > 3: score += 10
        if score > best_score: best_score = score; best_file = f
    return best_file if best_file else (file_list[0] if file_list else None)

def generate_with_backoff(model, prompt):
    for attempt in range(4): 
        try:
            return model.generate_content(prompt).text
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                wait_time = (attempt + 1) * 6
                with st.spinner(f"⚡ High Traffic: Waiting {wait_time}s..."):
                    time.sleep(wait_time)
            elif "404" in error_msg: return "⚠️ Model Error. Restart app."
            else: return f"Error: {str(e)}"
    return "⚠️ Server busy. Please wait 1 min."

# --- 5. THE EXPERIENCE (UI) ---
def main():
    if "authenticated" not in st.session_state: st.session_state.authenticated = False

    # GOOGLE LOGO (This one is reliable)
    google_logo = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Google_2015_logo.svg/368px-Google_2015_logo.svg.png"

    # --- LOGIN SCREEN ---
    if not st.session_state.authenticated:
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            # LOGO LOCKUP
            lc1, lc2, lc3 = st.columns([4, 1, 3])
            with lc1:
                # TYPOGRAPHIC JLP LOGO (Cannot Break)
                st.markdown("""
                <div class="jlp-logo-box">
                    <span class="jlp-main">JOHN LEWIS</span>
                    <span class="jlp-sub">& PARTNERS</span>
                </div>
                """, unsafe_allow_html=True)
            with lc2:
                 st.markdown("<h1 style='text-align: center; color: #ccc; margin:0;'>&times;</h1>", unsafe_allow_html=True)
            with lc3:
                st.image(google_logo, width=140)
            
            st.markdown("<br><p style='text-align: center; color: #666; letter-spacing: 2px; font-size: 12px; text-transform: uppercase;'>Strategic Growth Portal</p><br>", unsafe_allow_html=True)
            
            pwd = st.text_input("Enter Access Key", type="password", placeholder="••••••••")
            if pwd == CLIENT_PASSWORD:
                st.session_state.authenticated = True; st.rerun()
        return

    # --- MAIN DASHBOARD ---
    service = get_drive_service()
    if "model" not in st.session_state: st.session_state.model = get_working_model()

    # SIDEBAR
    with st.sidebar:
        st.markdown("### 📈 Growth Academy")
        tips = [
            "**Did you know?**\nCampaigns limited by budget miss out on 20% of converting traffic on average.",
            "**Pro Tip:**\nUse 'Target ROAS' with uncapped budgets to capture all profitable demand, not just the cheap clicks.",
            "**Holiday Insight:**\nSearch demand spikes 48h before a sale. Uncap budgets early to feed the algorithm."
        ]
        daily_tip = random.choice(tips)
        st.markdown(f"""<div class="tip-card">{daily_tip}</div>""", unsafe_allow_html=True)
        st.divider()
        if st.button("🔒 Logout"): st.session_state.authenticated = False; st.rerun()

    # HERO HEADER (LOGO LOCKUP)
    h1, h2, h3, h4 = st.columns([3, 0.5, 1.5, 4]) 
    with h1:
        # TYPOGRAPHIC JLP LOGO (Cannot Break)
        st.markdown("""
        <div class="jlp-logo-box">
            <span class="jlp-main">JOHN LEWIS</span>
            <span class="jlp-sub">& PARTNERS</span>
        </div>
        """, unsafe_allow_html=True)
    with h2:
        st.markdown("<h2 style='text-align: center; color: #ccc; margin:0;'>&times;</h2>", unsafe_allow_html=True)
    with h3:
        st.image(google_logo, width=130)
    
    st.markdown("## Welcome to your Growth Command Center")
    st.markdown("Ask questions about your media spend, missed opportunities, and demand trends.")
    st.divider()

    # CHAT HISTORY
    if "messages" not in st.session_state: st.session_state.messages = [{"role": "assistant", "content": "Welcome. I have analyzed your secure data. How can we drive growth today?"}]
    for msg in st.session_state.messages: 
        with st.chat_message(msg["role"]): st.markdown(msg["content"], unsafe_allow_html=True)

    # INPUT
    if query := st.chat_input("E.g., What was my missed opportunity last week?"):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"): st.markdown(query)

        with st.chat_message("assistant"):
            step_box = st.status("⚡ Analyzing Partnership Data...", expanded=True)
            files = list_files(service, FOLDER_ID)
            supported = [f for f in files if any(x in f['mimeType'] for x in ['spreadsheet', 'presentation', 'pdf', 'sheet'])]
            
            step_box.write("🔍 Identifying relevant insights...")
            target_file = find_best_file_local(query, supported)
            
            if target_file:
                step_box.write(f"📂 Accessing: **{target_file['name']}**")
                content, type_ = read_file(service, target_file['id'], target_file['mimeType'])
                
                step_box.write("🧠 Synthesizing strategy...")
                data_preview = content.to_string() if type_ == "dataframe" else content
                
                final_prompt = f"""
                You are a Strategic Growth Partner for John Lewis & Google.
                USER STATUS: Verified Admin.
                DATA CONTEXT: {data_preview[:15000]}
                USER QUESTION: {query}
                INSTRUCTIONS:
                1. Answer the question using the data.
                2. IMPORTANT: If data shows "Limited by Budget", suggest uncapping to capture full demand.
                3. Tone: Premium, Strategic, Encouraging.
                """
                
                ans_text = generate_with_backoff(st.session_state.model, final_prompt)
                
                step_box.update(label="Analysis Complete", state="complete", expanded=False)
                
                file_link = target_file.get('webViewLink', '#')
                st.markdown(f"### ✦ Insight Source: {target_file['name']}")
                st.markdown(f"<a href='{file_link}' target='_blank' class='file-link'>VIEW ORIGINAL ASSET &rarr;</a><br><br>", unsafe_allow_html=True)
                st.markdown(ans_text)
                
                st.session_state.messages.append({"role": "assistant", "content": f"**Source: {target_file['name']}** <a href='{file_link}' target='_blank'>[Open File]</a>\n\n{ans_text}"})
                
                if type_ == "dataframe": 
                    with st.expander("View Data Ledger"): st.dataframe(content)
            else:
                step_box.update(label="No Data", state="error")
                st.markdown("I couldn't find a report matching that query.")

if __name__ == "__main__": main()