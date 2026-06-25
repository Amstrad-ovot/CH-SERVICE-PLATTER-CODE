import io
import sys
import time
import pytz
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- DATABASE CONNECTION (Cached to avoid repeated handshakes) ---
@st.cache_resource
def get_gsheet_client():
    creds_dict = {
        "type": st.secrets["connections"]["gsheets"]["type"],
        "project_id": st.secrets["connections"]["gsheets"]["project_id"],
        "private_key_id": st.secrets["connections"]["gsheets"]["private_key_id"],
        "private_key": st.secrets["connections"]["gsheets"]["private_key"],
        "client_email": st.secrets["connections"]["gsheets"]["client_email"],
        "client_id": st.secrets["connections"]["gsheets"]["client_id"],
        "auth_uri": st.secrets["connections"]["gsheets"]["auth_uri"],
        "token_uri": st.secrets["connections"]["gsheets"]["token_uri"],
    }
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def connect_gsheet():
    try:
        client = get_gsheet_client()
        SPREADSHEET_ID = st.secrets["connections"]["gsheets"]["spreadsheet_id"]
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"Unable to connect google sheet: {e}")
        show_popup(f"Unable to connect google sheet: {e}", type="error")
        return None

def show_popup(message, type="success"):
    if type == "success":
        st.toast(f"✅ {message}")
    elif type == "error" :
        st.toast(f"❌ {message}")
    elif type == "warning":
        st.toast(f"⚠️ {message}")
    elif type == "info":
        st.toast(f"ℹ️ {message}")

# --- SPEED-OPTIMIZED ENGINE ---
def func1(raw_file):
    try:
        spreadsheet = connect_gsheet()
        if spreadsheet is None:
            raise Exception("Google Sheets connection failed. Cannot fetch Norms.")

        # 1. Fetch Norms Data
        norms_worksheet = spreadsheet.worksheet("Norms_Data")
        norms_data = norms_worksheet.get_all_records()
        status_data = pd.DataFrame(norms_data)
        status_data.columns = status_data.columns.str.lower().str.strip().str.replace(" ", "_")

        # 2. Fast Raw File Ingestion
        data = pd.read_excel(raw_file)
        data.columns = data.columns.str.lower().str.replace(" ","_").str.replace(".", "_").str.strip()
        
        selected_columns = ["service_id","customer_name","company_name","circle", "customer_type", "call_date", "status_updated_date", "status_code","phone1","provider_phone1"]
        data = data[selected_columns].copy()
        
        # Vectorized DateTime handling
        data["service_id"] = data["service_id"].astype(str)
        data["call_date"] = pd.to_datetime(data["call_date"]).dt.normalize()
        data["status_updated_date"] = pd.to_datetime(data["status_updated_date"]).dt.normalize()

        todayDate = pd.to_datetime('today').normalize()
        
        # Fast boolean masking instead of multi-pass assignments
        data = data[
            (data["call_date"] != todayDate) & 
            (data["circle"].str.lower().str.strip() != "india")
        ].copy()

        # Vectorized age calculations (in days)
        data["age_reg_days"] = (todayDate - data["call_date"]).dt.days
        data["age_update_days"] = (todayDate - data["status_updated_date"]).dt.days

        # Merge matching records
        merged_data = data.merge(status_data[["status","team", "number"]], left_on="status_code", right_on="status", how="left")
        merged_data = merged_data[merged_data["team"].str.lower().str.strip() == "customer xperience"].copy()

        if merged_data.empty:
            show_popup("No data found after filtering...!", type="info")
            return merged_data

        # 3. Blazing Fast Vectorized NumPy Rules (Replacing row-by-row .apply)
        status_clean = merged_data["status"].astype(str).str.strip().str.lower()
        num = merged_data["number"]
        
        # Choose target age based on status mask
        age_selector_mask = status_clean.isin(["open", "work_allocated"])
        age = np.where(age_selector_mask, merged_data["age_reg_days"], merged_data["age_update_days"])

        # Default fallback value
        category_arr = np.full(len(merged_data), "", dtype=object)

        # Build condition layouts
        is_special_status = status_clean.isin(["open_rejected_false", "open_completed_false"])
        
        cond_red_special = is_special_status & (age >= num)
        cond_red_normal = (~is_special_status) & (age > num)
        cond_enc1 = (age == num)
        cond_enc2 = (age == num - 1)
        cond_enc3 = (age == num - 2)

        # Cascade assignments down efficiently
        category_arr = np.where(cond_enc3, "Encroaching3", category_arr)
        category_arr = np.where(cond_enc2, "Encroaching2", category_arr)
        category_arr = np.where(cond_enc1, "Encroaching1", category_arr)
        category_arr = np.where(cond_red_normal | cond_red_special, "Red Call", category_arr)
        
        # Clean null values safely
        null_mask = pd.isna(num) | pd.isna(age)
        category_arr[null_mask] = ""

        # Map optimized calculations back to dataframe
        merged_data["category"] = category_arr
        merged_data["red_call_flag"] = (category_arr == "Red Call").astype(int)
        merged_data["enc1_flag"] = (category_arr == "Encroaching1").astype(int)
        merged_data["enc2_flag"] = (category_arr == "Encroaching2").astype(int)
        merged_data["enc3_flag"] = (category_arr == "Encroaching3").astype(int)
        
        show_popup("Data processed successfully in memory!", type="success")
        return merged_data

    except Exception as e:
        print(f"Error in func1: {e}")
        show_popup(f"Error in function is: {e}", type="error")
        return pd.DataFrame()

def circlewise_platter(merged_data):
    try:
        if merged_data.empty: return pd.DataFrame()

        merged_data1 = merged_data[merged_data["status_code"] != "TO_BE_REJECTED"]
        
        # Fast vectorized aggregation group
        summary = merged_data1.groupby("circle", as_index=False)[["red_call_flag", "enc1_flag", "enc2_flag", "enc3_flag"]].sum()
        summary = summary.rename(columns={
            "circle": "Circle", "red_call_flag": "Red Call",
            "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
        })

        summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
        summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
        summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]

        col_order = ["Circle", "Red Call", "Encroaching1", "Platter1", "Encroaching2", "Platter2", "Encroaching3", "Platter3"]
        summary = summary[col_order].sort_values("Platter1", ascending=False).reset_index(drop=True)

        # Assemble summary components array
        append_list = [summary]

        # Non-TBR summary block
        total_excl = summary[["Red Call", "Encroaching1", "Platter1", "Encroaching2", "Platter2", "Encroaching3", "Platter3"]].sum()
        total_excl_df = pd.DataFrame([total_excl])
        total_excl_df["Circle"] = "Total (Excl TBR)"
        append_list.append(total_excl_df[col_order])

        # TBR summary block
        tbr_data = merged_data[merged_data["status_code"] == "TO_BE_REJECTED"]
        if not tbr_data.empty:
            tbr_sum = tbr_data[["red_call_flag", "enc1_flag", "enc2_flag", "enc3_flag"]].sum()
            tbr_row = pd.DataFrame([{
                "Circle": "TO_BE_REJECTED",
                "Red Call": tbr_sum["red_call_flag"], "Encroaching1": tbr_sum["enc1_flag"],
                "Encroaching2": tbr_sum["enc2_flag"], "Encroaching3": tbr_sum["enc3_flag"]
            }])
            tbr_row["Platter1"] = tbr_row["Red Call"] + tbr_row["Encroaching1"]
            tbr_row["Platter2"] = tbr_row["Platter1"] + tbr_row["Encroaching2"]
            tbr_row["Platter3"] = tbr_row["Platter2"] + tbr_row["Encroaching3"]
            append_list.append(tbr_row[col_order])

        # Grand Total calculation block
        gt_sum = merged_data[["red_call_flag", "enc1_flag", "enc2_flag", "enc3_flag"]].sum()
        gt_row = pd.DataFrame([{
            "Circle": "Grand Total",
            "Red Call": gt_sum["red_call_flag"], "Encroaching1": gt_sum["enc1_flag"],
            "Encroaching2": gt_sum["enc2_flag"], "Encroaching3": gt_sum["enc3_flag"]
        }])
        gt_row["Platter1"] = gt_row["Red Call"] + gt_row["Encroaching1"]
        gt_row["Platter2"] = gt_row["Platter1"] + gt_row["Encroaching2"]
        gt_row["Platter3"] = gt_row["Platter2"] + gt_row["Encroaching3"]
        append_list.append(gt_row[col_order])

        return pd.concat(append_list, ignore_index=True)
    except Exception as e:
        print(f"Error in circlewise platter function: {e}")
        return pd.DataFrame()

def statuswise_platter(merged_data):
    try:
        if merged_data.empty: return pd.DataFrame()

        summary = merged_data.groupby("status_code", as_index=False)[["red_call_flag", "enc1_flag", "enc2_flag", "enc3_flag"]].sum()
        summary = summary.rename(columns={
            "status_code": "Status", "red_call_flag": "Red Call",
            "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
        })

        summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
        summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
        summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]
        
        col_order = ["Status", "Red Call", "Encroaching1", "Platter1","Encroaching2", "Platter2","Encroaching3", "Platter3"]
        summary = summary[col_order].sort_values("Platter1", ascending=False).reset_index(drop=True)

        rejected_df = summary[summary["Status"] == "TO_BE_REJECTED"]
        remaining_df = summary[summary["Status"] != "TO_BE_REJECTED"]

        append_list = [remaining_df]

        # Excl Summary Totals
        total_excl = remaining_df.select_dtypes(include='number').sum()
        total_excl_row = pd.DataFrame([total_excl])
        total_excl_row["Status"] = "Total (Excl TBR)"
        append_list.append(total_excl_row)

        # Rejected Row structural normalize
        if not rejected_df.empty:
            rejected_sum = rejected_df.select_dtypes(include='number').sum()
            rejected_row = pd.DataFrame([rejected_sum])
            rejected_row["Status"] = "To Be Rejected"
            append_list.append(rejected_row)

        # Grand Total components inclusion
        grand_total = summary.select_dtypes(include='number').sum()
        grand_total_row = pd.DataFrame([grand_total])
        grand_total_row["Status"] = "Grand Total (Incl TBR)"
        append_list.append(grand_total_row)

        return pd.concat(append_list, ignore_index=True)
    except Exception as e:
        print(f"Error in statuswise_platter function : {e}")
        return pd.DataFrame()

# --- FORMATTING STYLING PROCESSOR (Optimized to loop over structures cleanly) ---
def apply_formatting(workbook, worksheet, summary, title_text):
    try:
        fmt_header     = workbook.add_format({'bold': True, 'bg_color': '#FFFF00', 'border': 1, 'align': 'center'})
        fmt_main_title = workbook.add_format({'bold': True, 'bg_color': '#FFFF00', 'border': 1, 'align': 'center', 'font_size': 14})
        fmt_red        = workbook.add_format({'bold': True, 'bg_color': "#FF0000", 'border': 1, 'align': 'center'})
        fmt_orange     = workbook.add_format({'bg_color': "#FFBF00", 'border': 1, 'align': 'center', 'bold': True})
        fmt_green      = workbook.add_format({'bg_color': "#8BF58B", 'border': 1, 'align': 'center', 'bold': True})
        fmt_white      = workbook.add_format({'border': 1, 'align': 'center', 'bold': True})
        fmt_total      = workbook.add_format({'bold': True, 'bg_color': '#1F4E79', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})

        report_date = datetime.now().strftime("%d-%b-%Y")
        worksheet.merge_range('A1:H1', f"{title_text} --- {report_date}", fmt_main_title)

        # Pre-cache column formatting arrays instead of inline recalculations
        color_formats = [fmt_white, fmt_red, fmt_orange, fmt_green, fmt_orange, fmt_green, fmt_orange, fmt_green]

        # Speed up iterations by extraction values to primitive structures
        status_values = summary.iloc[:, 0].astype(str).str.upper().values
        summary_values = summary.values

        for row_num in range(2, len(summary) + 2):
            df_row_idx = row_num - 2
            is_total = "TOTAL" in status_values[df_row_idx]

            for col_num in range(8):
                value = summary_values[df_row_idx, col_num]
                fmt = fmt_total if is_total else color_formats[col_num]
                worksheet.write(row_num, col_num, value, fmt)
                    
        for col_num, value in enumerate(summary.columns.values):
            worksheet.write(1, col_num, value, fmt_header)

        worksheet.set_column('A:F', 18)
    except Exception as e:
        print(f"Error in Formatting: {e}")

def fetch_and_format_report(uploaded_file):
    try:
        if uploaded_file is None: return None
        output = io.BytesIO()

        # Step 1: Run the fast vectorized numpy data pipeline 
        final_df = func1(uploaded_file)
        if final_df.empty: return None

        # Step 2: Extract summaries out of the dataframe in-memory
        circle_summary_df = circlewise_platter(final_df)
        status_summary_df = statuswise_platter(final_df)

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            
            # --- Sheet 1: Daily Circlewise Platter ---
            if not circle_summary_df.empty:
                sheet_name = "Daily Circlewise Platter"
                circle_summary_df.iloc[:, 1:] = circle_summary_df.iloc[:, 1:].apply(pd.to_numeric, errors='coerce').fillna(0).astype(int)
                circle_summary_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
                apply_formatting(writer.book, writer.sheets[sheet_name], circle_summary_df, "All Circlewise Platter And Targets")

            # --- Sheet 2: Statuswise Platter ---
            if not status_summary_df.empty:
                sheet_name = "Statuswise Platter"
                status_summary_df.iloc[:, 1:] = status_summary_df.iloc[:, 1:].apply(pd.to_numeric, errors='coerce').fillna(0).astype(int)
                status_summary_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
                apply_formatting(writer.book, writer.sheets[sheet_name], status_summary_df, "Statuswise Platter And Targets")

            # --- Sheet 3: Detailed Raw Data ---
            raw_df = final_df[["circle","status_code","service_id", "customer_name","phone1","company_name","provider_phone1","category"]].copy()
            raw_df = raw_df[raw_df["category"].isin(["Red Call", "Encroaching1", "Encroaching2", "Encroaching3"])].copy()
            raw_df["category"] = pd.Categorical(
                raw_df["category"],
                categories=["Red Call", "Encroaching1", "Encroaching2", "Encroaching3"],
                ordered=True
            )
            raw_df = raw_df.sort_values("category")
            raw_df.to_excel(writer, sheet_name="Raw_Data", index=False)

        return output.getvalue()
    except Exception as e:
        print(f"Error in fetch_and_format_report: {e}")
        return None

