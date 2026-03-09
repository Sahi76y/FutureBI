import json
import streamlit as st
import google.generativeai as genai
import pandas as pd
import sqlite3
import plotly.express as px

# --- CONFIGURATION ---
# Replace with your fresh API Key
API_KEY = "AIzaSyBG86-t48233KLv0lenPLU3YqIQAPoOOPU"
genai.configure(api_key=API_KEY)

# --- HELPER: CONVERSATIONAL AGENT LOGIC ---
def ask_gemini_analyst(user_prompt, schema_info, chat_history):
    # Prepare history for the AI to understand context
    history_text = ""
    for msg in chat_history[-6:]: # Include last 3 exchanges
        role = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role}: {msg['content']}\n"

    context = f"""
    You are a Data Analyst. The user has uploaded a dataset with these columns: {schema_info}
    
    Previous Conversation Context:
    {history_text}
    
    Current User Request: {user_prompt}
    
    Based on the history and request, return a JSON object with:
    1. 'sql': A valid SQLite query. Use 'table_data' as the table name.
    2. 'chart_type': One of ['bar', 'line', 'pie', 'metric', 'table'].
    3. 'explanation': A very brief summary of what you are showing.
    
    Return ONLY raw JSON. No markdown formatting.
    """
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(context)
    
    try:
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)
    except Exception:
        return {
            "sql": "SELECT * FROM table_data LIMIT 10", 
            "chart_type": "table", 
            "explanation": "I had trouble generating the specific query, here is a preview of the data."
        }

# --- STREAMLIT UI ---
st.set_page_config(layout="wide", page_title="FutureBI")
st.title("💬 FutureBI")
st.markdown("Upload your file and ask questions. I remember our conversation, so you can ask follow-up questions!")

# Initialize Chat History in Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for File Upload
uploaded_file = st.sidebar.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"])

if uploaded_file:
    # Load Data into Session State so it doesn't reload on every click
    if "df" not in st.session_state:
        try:
            if uploaded_file.name.endswith('.csv'):
                try:
                    st.session_state.df = pd.read_csv(uploaded_file)
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    st.session_state.df = pd.read_csv(uploaded_file, encoding='ISO-8859-1')
            else:
                st.session_state.df = pd.read_excel(uploaded_file)
            st.sidebar.success("File Ready!")
        except Exception as e:
            st.error(f"Error loading file: {e}")

    if "df" in st.session_state:
        # Prepare SQL Environment
        conn = sqlite3.connect(':memory:', check_same_thread=False)
        st.session_state.df.to_sql('table_data', conn, index=False, if_exists='replace')
        schema = ", ".join([f"{col}" for col in st.session_state.df.columns])

        # Display Chat History
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "df_result" in message:
                    st.dataframe(message["df_result"], use_container_width=True)
                if "fig" in message:
                    st.plotly_chart(message["fig"], use_container_width=True)

        # Chat Input Area
        if prompt := st.chat_input("Ask about the data (e.g., 'Show me total claims by year')"):
            # 1. Show User Message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # 2. Generate Assistant Response
            with st.chat_message("assistant"):
                with st.spinner("Analyzing data..."):
                    ai_response = ask_gemini_analyst(prompt, schema, st.session_state.messages)
                    
                    try:
                        # Execute the SQL
                        res_df = pd.read_sql_query(ai_response['sql'], conn)
                        explanation = ai_response['explanation']
                        chart_type = ai_response['chart_type']
                        
                        st.markdown(explanation)
                        st.dataframe(res_df, use_container_width=True)

                        # Create Chart if applicable
                        fig = None
                        if chart_type != 'table' and not res_df.empty and len(res_df.columns) >= 2:
                            x_col, y_col = res_df.columns[0], res_df.columns[1]
                            
                            if chart_type == 'bar':
                                fig = px.bar(res_df, x=x_col, y=y_col, title=explanation)
                            elif chart_type == 'line':
                                fig = px.line(res_df, x=x_col, y=y_col, markers=True, title=explanation)
                            elif chart_type == 'pie':
                                fig = px.pie(res_df, names=x_col, values=y_col, hole=0.3)
                            
                            if fig:
                                st.plotly_chart(fig, use_container_width=True)

                        # Save response to history
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": explanation,
                            "df_result": res_df,
                            "fig": fig
                        })

                    except Exception as e:
                        err_msg = f"I encountered an error analyzing that: {e}"
                        st.error(err_msg)
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
else:
    st.info("Please upload a file in the sidebar to start chatting.")