import streamlit as st
import pandas as pd
import io
import pytz
from datetime import datetime

from main import (
    func1,
    circlewise_platter,
    statuswise_platter,
    fetch_and_format_report,
    # send_email,

)
from src.sidebar import render_sidebar

st.set_page_config(page_title="CH Service Report Generator", layout="wide")

page = render_sidebar()

# --- PAGE: Upload File & Create Report ---
if page == "upload":
    st.header("📤 Upload File & Create Report")

    uploaded_raw_file = st.file_uploader("Choose the Raw Data Excel file", type=["xlsx"])

    if uploaded_raw_file is not None:
        if st.button("Generate Report"):
            with st.spinner("Processing data and pushing to Database..."):
                try:
                    # Step 1: Process raw file → push all sheets to Google Sheets
                    final_df = func1(uploaded_raw_file)

                    if isinstance(final_df, pd.DataFrame):
                        circlewise_platter(final_df)
                        statuswise_platter(final_df)

                        st.success("✅ All data updated in Database!")

                except Exception as e:
                    st.error(f"Error during processing: {e}")
        
    st.divider()

    # --- Download Section (independent of upload) ---
    st.subheader("📥 Download Platter Report")
    st.caption("Fetches latest data directly from Database and downloads as Excel.")

    if st.button("📥 Format Platter Report"):
        with st.spinner("Fetching data from Database and formatting..."):
            report_data = fetch_and_format_report()

            if report_data:
                IST = pytz.timezone('Asia/Kolkata')
                today_str = datetime.now().strftime("%Y-%m-%d")
                time_str  = datetime.now(IST).strftime("%H:%M")
                st.download_button(
                    label="⬇️ Click here to Download",
                    data=report_data,
                    file_name=f"service_platter_report_{datetime.now(IST).strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    st.divider()

    # # --- Download Section (independent of upload) ---
    # st.subheader("📥 Email Reports")

    # if st.button("📧 Send Email Report"):
    #     with st.spinner("Generating and sending email..."):
    #         report_data = fetch_and_format_report()

    #         sender_email = st.secrets["connections"]["gsheets"]["sender_email"]
    #         sender_password = st.secrets["connections"]["gsheets"]["sender_password"]
    #         recipient_email = st.secrets["connections"]["gsheets"]["recipient_email"]
    #         cc_emails = st.secrets["connections"]["gsheets"]["cc_email"]
    #         print(cc_emails)
    #         if report_data:
    #             send_email(
    #                 sender_email,
    #                 sender_password,
    #                 recipient_email,
    #                 cc_emails,
    #                 report_data
    #             )
    #             st.success("✅ Email sent successfully!")
    #         else:
    #             st.error("❌ Failed to generate report")
