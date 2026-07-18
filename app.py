import streamlit as st
import pandas as pd
import io
import pytz
from datetime import datetime
from main import fetch_and_format_report, func1
from src.sidebar import render_sidebar

# Must be the very first Streamlit command
st.set_page_config(page_title="CH Service Report Generator", layout="wide")

# Persistent data state optimizations
if "processed_df" not in st.session_state:
    st.session_state["processed_df"] = None
if "last_file_name" not in st.session_state:
    st.session_state["last_file_name"] = None
if "excel_binary" not in st.session_state:
    st.session_state["excel_binary"] = None
if "download_filename" not in st.session_state:
    st.session_state["download_filename"] = ""

page = render_sidebar()

if page == "upload":
    st.header("📤 Service Report Management")
    st.caption("Step 1: Upload and process your data. Step 2: Format and download your styled Excel sheet.")

    uploaded_raw_file = st.file_uploader("Choose the Raw Data Excel file", type=["xlsx"])

    if uploaded_raw_file is not None:
        # Reset state cache if a brand new file is swapped in
        if st.session_state["last_file_name"] != uploaded_raw_file.name:
            st.session_state["processed_df"] = None
            st.session_state["excel_binary"] = None
            st.session_state["last_file_name"] = uploaded_raw_file.name

        # -------------------------------------------------------------
        # STEP 1: BUTTON TO PROCESS DATA
        # -------------------------------------------------------------
        st.subheader("Step 1: Run Data Pipeline")
        
        # Highlight processing button with primary color
        if st.button("⚡ Process & Analyze Data", type="primary"):
            with st.spinner("Executing fast vectorized calculations in-memory..."):
                try:
                    # Run func1 calculations and store in session state
                    computed_df = func1(uploaded_raw_file)
                    
                    if isinstance(computed_df, pd.DataFrame) and not computed_df.empty:
                        st.session_state["processed_df"] = computed_df
                        # Pre-build the excel binary data immediately so download is instant
                        st.session_state["excel_binary"] = fetch_and_format_report(uploaded_raw_file)
                        
                        IST = pytz.timezone('Asia/Kolkata')
                        timestamp = datetime.now(IST).strftime('%Y%m%d_%H%M')
                        st.session_state["download_filename"] = f"service_platter_report_{timestamp}.xlsx"
                        
                        st.success("✅ Analytics engine completed! Ready for export layout generation.")
                    else:
                        st.error("The data pipeline returned an empty dataset. Check your filters.")
                except Exception as e:
                    st.error(f"Error processing calculations: {e}")

        # -------------------------------------------------------------
        # STEP 2: BUTTON TO DOWNLOAD DATA (Appears only after Step 1)
        # -------------------------------------------------------------
        if st.session_state["excel_binary"] is not None:
            st.write("---")
            st.subheader("Step 2: Export Clean Document")
            # st.info("Layout styles, column dimensions, and color bands have been mapped successfully.")
            
            st.download_button(
                label="📥 Click here to Download Excel File",
                data=st.session_state["excel_binary"],
                file_name=st.session_state["download_filename"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="isolated_download_action"
            )
            
    else:
        # Clear out state records on file removal
        st.info("💡 Please upload a raw Excel file above to activate processing tools.")
        st.session_state["processed_df"] = None
        st.session_state["excel_binary"] = None
        st.session_state["last_file_name"] = None
        
    st.divider()














# import streamlit as st
# import pandas as pd
# import io
# import pytz
# from datetime import datetime
# from main import fetch_and_format_report, func1
# from src.sidebar import render_sidebar


# # Must be the very first Streamlit command
# st.set_page_config(page_title="CH Service Report Generator", layout="wide")

# # Persistent data state optimizations
# if "processed_df" not in st.session_state:
#     st.session_state["processed_df"] = None
# if "last_file_name" not in st.session_state:
#     st.session_state["last_file_name"] = None
# if "excel_binary" not in st.session_state:
#     st.session_state["excel_binary"] = None
# if "download_filename" not in st.session_state:
#     st.session_state["download_filename"] = ""

# page = render_sidebar()

# if page == "upload":
#     st.header("📤 Service Report Management")
#     st.caption("Step 1: Upload and process your data. Step 2: Format and download your styled Excel sheet.")

#     uploaded_raw_file = st.file_uploader("Choose the Raw Data Excel file", type=["xlsx"])

#     if uploaded_raw_file is not None:
#         # Reset state cache if a brand new file is swapped in
#         if st.session_state["last_file_name"] != uploaded_raw_file.name:
#             st.session_state["processed_df"] = None
#             st.session_state["excel_binary"] = None
#             st.session_state["last_file_name"] = uploaded_raw_file.name

#         # -------------------------------------------------------------
#         # STEP 1: BUTTON TO PROCESS DATA
#         # -------------------------------------------------------------
#         st.subheader("Step 1: Run Data Pipeline")
        
#         # Highlight processing button with primary color
#         if st.button("⚡ Process & Analyze Data", type="primary"):
#             with st.spinner("Executing fast vectorized calculations in-memory..."):
#                 try:
#                     # Run func1 calculations and store in session state
#                     computed_df = func1(uploaded_raw_file)
                    
#                     if isinstance(computed_df, pd.DataFrame) and not computed_df.empty:
#                         st.session_state["processed_df"] = computed_df
#                         # Pre-build the excel binary data immediately so download is instant
#                         st.session_state["excel_binary"] = fetch_and_format_report(uploaded_raw_file)
                        
#                         IST = pytz.timezone('Asia/Kolkata')
#                         timestamp = datetime.now(IST).strftime('%Y%m%d_%H%M')
#                         st.session_state["download_filename"] = f"service_platter_report_{timestamp}.xlsx"
                        
#                         st.success("✅ Analytics engine completed! Ready for export layout generation.")
#                     else:
#                         st.error("The data pipeline returned an empty dataset. Check your filters.")
#                 except Exception as e:
#                     st.error(f"Error processing calculations: {e}")

#         # -------------------------------------------------------------
#         # STEP 2: BUTTON TO DOWNLOAD DATA (Appears only after Step 1)
#         # -------------------------------------------------------------
#         if st.session_state["excel_binary"] is not None:
#             st.write("---")
#             st.subheader("Step 2: Export Clean Document")
#             st.info("Layout styles, column dimensions, and color bands have been mapped successfully.")
            
#             st.download_button(
#                 label="📥 Click here to Download Excel File",
#                 data=st.session_state["excel_binary"],
#                 file_name=st.session_state["download_filename"],
#                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#                 key="isolated_download_action"
#             )
            
#     else:
#         # Clear out state records on file removal
#         st.info("💡 Please upload a raw Excel file above to activate processing tools.")
#         st.session_state["processed_df"] = None
#         st.session_state["excel_binary"] = None
#         st.session_state["last_file_name"] = None
        
#     st.divider()
