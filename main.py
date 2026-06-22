import io
import sys
import time
import pytz
import pandas as pd
import streamlit as st
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


# To create connection
def get_gsheet_conn():

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
    client = gspread.authorize(creds)
    return client

def connect_gsheet():
    try:
        # Google sheet Connection  
        client = get_gsheet_conn()
        SPREADSHEET_ID = st.secrets["connections"]["gsheets"]["spreadsheet_id"]
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print("Connection successful...!!!")
        return spreadsheet
    except Exception as e:
        print(f"Unable to connect google sheet: {e}")
        show_popup(f"Unable to connect google sheet: {e}", type="error")
        

def show_popup(message, type = "success"):
    if type == "success":
        st.toast(f"✅ {message}")
    elif type == "error" :
        st.toast(f"❌ {message}")
    elif type == "warning":
        st.toast(f"⚠️ {message}")
    elif type == "info":
        st.toast(f"ℹ️ {message}")

def func1(raw_file):
    try:
        spreadsheet = connect_gsheet()

        # Open or create the worksheet
        try:
            detailData_worksheet = spreadsheet.worksheet("Detailed_Data")
        except gspread.WorksheetNotFound:
            detailData_worksheet = spreadsheet.add_worksheet("Detailed_Data", rows=5000, cols=30)
            
        # Clear existing data and write fresh
        detailData_worksheet.clear()

        data = pd.read_excel(raw_file)
        data.columns = data.columns.str.lower().str.replace(" ","_").str.replace(".", "_").str.strip()
        # To select the subset of the dataframe from the complete data
        selected_columns = ["service_id","customer_name","company_name","circle", "customer_type", "call_date", "status_updated_date", "status_code","phone1","provider_phone1"]
        data = data[selected_columns]
        data["service_id"] = data["service_id"].astype(str)
        data["call_date"] = pd.to_datetime(data["call_date"]).dt.normalize()
        data["status_updated_date"] = pd.to_datetime(data["status_updated_date"]).dt.normalize()

        todayDate = pd.to_datetime('today').date()
        data = data[data["call_date"].dt.date != todayDate]
        data = data[data["circle"].str.lower().str.strip() != "india"]

        data["today_date"] = pd.to_datetime(todayDate)
        data["age_from_call_reg"] = data["today_date"] - data["call_date"]
        data["age_from_call_update"] = data["today_date"] - data["status_updated_date"]

        # status_data = pd.read_excel(statuswise_file)
        norms_worksheet = spreadsheet.worksheet("Norms_Data")
        norms_data = norms_worksheet.get_all_records()
        status_data = pd.DataFrame(norms_data)

        status_data.columns = status_data.columns.str.lower().str.strip().str.replace(" ", "_")

        merged_data = data.merge(status_data[["status","team", "number"]], left_on= "status_code", right_on="status", how= "left")
        
        # Adding filter on teams, choosing customer xperience
        merged_data = merged_data[merged_data["team"].str.lower().str.strip() == "customer xperience"]

        merged_data["age_reg_days"] = merged_data["age_from_call_reg"].dt.days 
        merged_data["age_update_days"] = merged_data["age_from_call_update"].dt.days 

        def assign_category(row):
            status = str(row["status"]).strip().lower()
            num = row["number"]

            if pd.isna(num):
                return ""

            # Select correct age column
            age = row["age_reg_days"] if status in ["open", "work_allocated"] else row["age_update_days"]

            if pd.isna(age):
                return ""

            # Special condition as this status norm is zero
            if status in ["open_rejected_false", "open_completed_false"]:
                if age >= num:
                    return "Red Call"
                return ""

            # Default logic
            if age > num:
                return "Red Call"
            elif age == num:
                return "Encroaching1"
            elif age == num - 1:
                return "Encroaching2"
            elif age == num - 2:
                return "Encroaching3"
            return ""

        merged_data["category"] = merged_data.apply(assign_category, axis=1)
        merged_data["red_call_flag"] = (merged_data["category"] == "Red Call").astype(int)
        merged_data["enc1_flag"] = (merged_data["category"] == "Encroaching1").astype(int)
        merged_data["enc2_flag"] = (merged_data["category"] == "Encroaching2").astype(int)
        merged_data["enc3_flag"] = (merged_data["category"] == "Encroaching3").astype(int)
        
        # To write data in google sheet
        if merged_data is not None and not merged_data.empty:
            
            # Convert DataFrame to list of lists
            # data_to_write = [merged_data.columns.tolist()] + merged_data.astype(str).values.tolist()
            data_to_write = [merged_data.columns.tolist()] + merged_data.fillna("").astype(str).values.tolist()
            detailData_worksheet.update(data_to_write)
            
            show_popup("Data stored in the database", type = "success")
        else:
            show_popup("No data found after filtering...!", type = "info")
        return merged_data

    except Exception as e:
        print(f"Error in func1: {e}")
        show_popup(f"Error in function is: {e}", type= "error")

def circlewise_platter(merged_data):
    try:
        spreadsheet = connect_gsheet()

        merged_data1 = merged_data[merged_data["status_code"] != "TO_BE_REJECTED"]

        summary = merged_data1.groupby("circle").agg({
            "red_call_flag": "sum", "enc1_flag": "sum", "enc2_flag": "sum", "enc3_flag": "sum"
        }).reset_index()

        summary = summary.rename(columns={
            "circle": "Circle", "red_call_flag": "Red Call",
            "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
        })

        summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
        summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
        summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]

        col_order = ["Circle", "Red Call", "Encroaching1", "Platter1", "Encroaching2", "Platter2", "Encroaching3", "Platter3"]
        summary = summary[col_order]

        # Sort by Platter1 descending BEFORE adding Total row
        summary = summary.sort_values("Platter1", ascending=False).reset_index(drop=True)

        # Separate TBR data from original dataset
        tbr_data = merged_data[merged_data["status_code"] == "TO_BE_REJECTED"]

        # Aggregate TBR row
        if not tbr_data.empty:
            tbr_summary = tbr_data.agg({
                "red_call_flag": "sum",
                "enc1_flag": "sum",
                "enc2_flag": "sum",
                "enc3_flag": "sum"
            })

            tbr_row = pd.DataFrame([tbr_summary])
            tbr_row = tbr_row.rename(columns={
                "red_call_flag": "Red Call",
                "enc1_flag": "Encroaching1",
                "enc2_flag": "Encroaching2",
                "enc3_flag": "Encroaching3"
            })

            tbr_row["Platter1"] = tbr_row["Red Call"] + tbr_row["Encroaching1"]
            tbr_row["Platter2"] = tbr_row["Platter1"] + tbr_row["Encroaching2"]
            tbr_row["Platter3"] = tbr_row["Platter2"] + tbr_row["Encroaching3"]
            tbr_row["Circle"] = "TO_BE_REJECTED"

            tbr_row = tbr_row[col_order]
        else:
            tbr_row = pd.DataFrame(columns=col_order)

        # Total excluding TBR
        non_tbr_data = merged_data[merged_data["status_code"] != "TO_BE_REJECTED"]

        total_excl = non_tbr_data.agg({
            "red_call_flag": "sum",
            "enc1_flag": "sum",
            "enc2_flag": "sum",
            "enc3_flag": "sum"
        })

        total_excl_row = pd.DataFrame([total_excl])
        total_excl_row = total_excl_row.rename(columns={
            "red_call_flag": "Red Call",
            "enc1_flag": "Encroaching1",
            "enc2_flag": "Encroaching2",
            "enc3_flag": "Encroaching3"
        })

        total_excl_row["Platter1"] = total_excl_row["Red Call"] + total_excl_row["Encroaching1"]
        total_excl_row["Platter2"] = total_excl_row["Platter1"] + total_excl_row["Encroaching2"]
        total_excl_row["Platter3"] = total_excl_row["Platter2"] + total_excl_row["Encroaching3"]
        total_excl_row["Circle"] = "Total (Excl TBR)"

        total_excl_row = total_excl_row[col_order]

        # Grand Total (including everything)
        grand_total = merged_data.agg({
            "red_call_flag": "sum",
            "enc1_flag": "sum",
            "enc2_flag": "sum",
            "enc3_flag": "sum"
        })

        grand_total_row = pd.DataFrame([grand_total])
        grand_total_row = grand_total_row.rename(columns={
            "red_call_flag": "Red Call",
            "enc1_flag": "Encroaching1",
            "enc2_flag": "Encroaching2",
            "enc3_flag": "Encroaching3"
        })

        grand_total_row["Platter1"] = grand_total_row["Red Call"] + grand_total_row["Encroaching1"]
        grand_total_row["Platter2"] = grand_total_row["Platter1"] + grand_total_row["Encroaching2"]
        grand_total_row["Platter3"] = grand_total_row["Platter2"] + grand_total_row["Encroaching3"]
        grand_total_row["Circle"] = "Grand Total"

        grand_total_row = grand_total_row[col_order]

        # FINAL STRUCTURE
        summary = pd.concat([
            summary,
            total_excl_row,
            tbr_row,
            grand_total_row
        ], ignore_index=True)

        # Write to Google Sheet
        try:
            worksheet = spreadsheet.worksheet("Daily Circlewise Platter")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet("Daily Circlewise Platter", rows=5000, cols=30)

        worksheet.clear()
        data_to_write = [summary.columns.tolist()] + summary.astype(str).values.tolist()
        worksheet.update(data_to_write)

        # # Call tracker with circlewise summary
        # tracker(summary)

        show_popup("Circlewise platter report created successfully!", type="success")

    except Exception as e:
        print(f"Error in circlewise platter function: {e}")
        show_popup(f"Error in circlewise_platter is : {e}", type="error") 
        
# def tracker(df):
#     try:
#         spreadsheet = connect_gsheet()
#         # Set timezone to India
#         IST = pytz.timezone('Asia/Kolkata')
#         today_str = datetime.now().strftime("%Y-%m-%d")
#         time_str  = datetime.now(IST).strftime("%H:%M")

#         # --- Get or create Tracker worksheet ---
#         try:
#             worksheet = spreadsheet.worksheet("Tracker")
#         except gspread.WorksheetNotFound:
#             worksheet = spreadsheet.add_worksheet("Tracker", rows=1000, cols=50)

#         # --- Read existing data (returns list of lists) ---
#         existing_data = worksheet.get_all_values()

#         # --- Check if first DATA row has today's date ---
#         if not existing_data or len(existing_data) < 2 or existing_data[1][0] != today_str:
#             worksheet.clear()
#             existing_data = []

#         # ================== FILTER TILL TOTAL EXCL TBR ==================

#         df["Circle"] = df["Circle"].astype(str)

#         mask_total_excl = df["Circle"].str.strip().str.upper() == "TOTAL (EXCL TBR)"

#         if mask_total_excl.any():
#             cutoff_index = df[mask_total_excl].index[0]
#             df = df.loc[:cutoff_index].copy()

#         # Rename to "Total"
#         df["Circle"] = df["Circle"].replace({
#             "Total (Excl TBR)": "Total",
#             "TOTAL (EXCL TBR)": "Total"
#         })

#         # =================================================================

#         # --- Extract Circle + Platter1 + Platter2 + Platter3 ---
#         platter_data = df[["Circle", "Platter1", "Platter2", "Platter3"]].copy()
#         platter_data["Circle"]   = platter_data["Circle"].astype(str)
#         platter_data["Platter1"] = pd.to_numeric(platter_data["Platter1"], errors='coerce').fillna(0)
#         platter_data["Platter2"] = pd.to_numeric(platter_data["Platter2"], errors='coerce').fillna(0)
#         platter_data["Platter3"] = pd.to_numeric(platter_data["Platter3"], errors='coerce').fillna(0)

#         new_p1_col = f"{time_str} P1"
#         new_p2_col = f"{time_str} P2"
#         new_p3_col = f"{time_str} P3"

#         # Helper: push Total row(s) to the very bottom
#         def sort_total_to_bottom(df_in):
#             is_total = df_in["Circle"].str.strip().str.lower() == "total"
#             return pd.concat(
#                 [df_in[~is_total], df_in[is_total]],
#                 ignore_index=True
#             )

#         if not existing_data:
#             # --- First run ---
#             header = ["Date", "Circle", new_p1_col, new_p2_col, new_p3_col]
#             rows = [header]

#             for _, row in platter_data.iterrows():
#                 rows.append([
#                     today_str,
#                     str(row["Circle"]),
#                     str(row["Platter1"]),
#                     str(row["Platter2"]),
#                     str(row["Platter3"])
#                 ])

#             worksheet.update(rows)

#         else:
#             # --- Subsequent runs ---
#             existing_df = pd.DataFrame(existing_data[1:], columns=existing_data[0])
#             existing_df["Circle"] = existing_df["Circle"].astype(str)

#             # ✅ Fix: Backfill missing P3 columns for old timestamps (P1/P2 only structure)
#             existing_p2_cols = [col for col in existing_df.columns if col.endswith("P2")]
#             for p2_col in existing_p2_cols:
#                 timestamp = p2_col.replace(" P2", "")
#                 p3_col = f"{timestamp} P3"
#                 if p3_col not in existing_df.columns:
#                     p2_idx = existing_df.columns.tolist().index(p2_col)
#                     existing_df.insert(p2_idx + 1, p3_col, "0")

#             # Build lookup dict
#             platter_dict = {
#                 str(row["Circle"]): (str(row["Platter1"]), str(row["Platter2"]), str(row["Platter3"]))
#                 for _, row in platter_data.iterrows()
#             }

#             # Add new circles if any
#             existing_circles = set(existing_df["Circle"].tolist())
#             new_circles = [c for c in platter_dict if c not in existing_circles]

#             if new_circles:
#                 empty_row = {col: "0" for col in existing_df.columns}
#                 new_rows = []

#                 for circle in new_circles:
#                     row = empty_row.copy()
#                     row["Date"] = today_str
#                     row["Circle"] = circle
#                     new_rows.append(row)

#                 new_rows_df = pd.DataFrame(new_rows)
#                 existing_df = pd.concat([existing_df, new_rows_df], ignore_index=True)

#             # Add new time columns
#             existing_df[new_p1_col] = existing_df["Circle"].map(
#                 lambda c: platter_dict.get(c, ("0", "0", "0"))[0]
#             )
#             existing_df[new_p2_col] = existing_df["Circle"].map(
#                 lambda c: platter_dict.get(c, ("0", "0", "0"))[1]
#             )
#             existing_df[new_p3_col] = existing_df["Circle"].map(
#                 lambda c: platter_dict.get(c, ("0", "0", "0"))[2]
#             )

#             # Move Total to bottom
#             existing_df = sort_total_to_bottom(existing_df)

#             # Convert to list
#             updated_rows = [existing_df.columns.tolist()] + existing_df.values.tolist()

#             # Sort middle rows based on latest P1 (excluding header and last Total row)
#             headers = updated_rows[0]
#             p1_indices = [i for i, h in enumerate(headers) if h.endswith("P1")]
#             latest_p1_idx = p1_indices[-1]

#             middle_rows = sorted(
#                 updated_rows[1:len(updated_rows)-1],
#                 key=lambda x: int(float(x[latest_p1_idx])) if x[latest_p1_idx] not in ("", None) else 0,
#                 reverse=True
#             )

#             new_rows = [headers] + middle_rows + [updated_rows[-1]]

#             worksheet.clear()
#             worksheet.update(new_rows)

#         show_popup("Tracker updated successfully!", type="success")

#     except Exception as e:
#         print(f"Error in tracker function is: {e}")
#         show_popup(f"Error in tracker function is: {e}", type="error")
                

def statuswise_platter(merged_data):
    try:
        spreadsheet = connect_gsheet()

        summary = merged_data.groupby("status_code").agg({
            "red_call_flag": "sum", "enc1_flag": "sum", "enc2_flag": "sum", "enc3_flag": "sum"
        }).reset_index()

        summary = summary.rename(columns={
            "status_code": "Status", "red_call_flag": "Red Call",
            "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
        })

        summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
        summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
        summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]
        
        col_order = ["Status", "Red Call", "Encroaching1", "Platter1","Encroaching2", "Platter2","Encroaching3", "Platter3"]
        summary = summary[col_order]

    

        # Sort before totals
        summary = summary.sort_values("Platter1", ascending=False).reset_index(drop=True)

        # Separate "To Be Rejected"
        rejected_df = summary[summary["Status"] == "TO_BE_REJECTED"]
        remaining_df = summary[summary["Status"] != "TO_BE_REJECTED"]

        # Ensure ONLY ONE rejected row (aggregate if needed)
        if not rejected_df.empty:
            rejected_sum = rejected_df.select_dtypes(include='number').sum()
            rejected_row = pd.DataFrame([rejected_sum])
            rejected_row["Status"] = "To Be Rejected"
        else:
            rejected_row = pd.DataFrame(columns=summary.columns)

        # Total WITHOUT "To Be Rejected"
        total_excl = remaining_df.select_dtypes(include='number').sum()
        total_excl_row = pd.DataFrame([total_excl])
        total_excl_row["Status"] = "Total (Excl TBR)"

        # Grand Total INCLUDING everything
        grand_total = summary.select_dtypes(include='number').sum()
        grand_total_row = pd.DataFrame([grand_total])
        grand_total_row["Status"] = "Grand Total (Incl TBR)"

        # FINAL ORDER (this is the key part)
        final_df = pd.concat([
            remaining_df,
            total_excl_row,
            rejected_row,
            grand_total_row
        ], ignore_index=True)

        summary = final_df

        # To write data in google sheet
        if summary is not None and not summary.empty:
            try:
                worksheet = spreadsheet.worksheet("Statuswise Platter")
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet("Statuswise Platter", rows=5000, cols=30)
            
            # Clear existing data and write fresh
            worksheet.clear()
            
            # Convert DataFrame to list of lists
            data_to_write = [summary.columns.tolist()] + summary.astype(str).values.tolist()
            worksheet.update(data_to_write)
        
        show_popup("Statuswise platter report created successfully!", type = "success")        
    except Exception as e:
        print(f"Error in statuswise_platter function : {e}")
        show_popup(f"Error in statuswise_platter is : {e}", type = "error")


# def billing_code_status_platter(merged_data):
#     try:
#         spreadsheet = connect_gsheet()

#         # To write data in google sheet
#         try:
#             worksheet = spreadsheet.worksheet("Billing Code")
#         except gspread.WorksheetNotFound:
#             worksheet = spreadsheet.add_worksheet("Billing Code", rows=5000, cols=30)
            
#         # Clear existing data and write fresh
#         worksheet.clear()

#         summary = merged_data[merged_data["status_code"].str.upper().str.strip() == "BILLING_CODE_PROBLEM"]
        
#         if not merged_data.empty:
#             summary = summary.groupby("circle").agg({
#                 "red_call_flag": "sum", "enc1_flag": "sum", "enc2_flag": "sum", "enc3_flag": "sum"
#             }).reset_index()

#             summary = summary.rename(columns={
#                 "circle": "Circle", "red_call_flag": "Red Call",
#                 "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
#             })

#             summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
#             summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
#             summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]
            
#             col_order = ["Circle", "Red Call", "Encroaching1", "Platter1","Encroaching2", "Platter2","Encroaching3", "Platter3"]
#             summary = summary[col_order]
            
#             # Droping the rows where Platter2 is zero
#             summary= summary[summary["Platter2"] != 0]

#             # Sort by Platter1 descending BEFORE adding Total row
#             summary = summary.sort_values("Platter1", ascending=False).reset_index(drop=True)

#             totals = summary.select_dtypes(include='number').sum()
#             total_row = pd.DataFrame([totals])
#             total_row["Circle"] = "Total"
#             summary = pd.concat([summary, total_row], ignore_index=True)
            
#             # Convert DataFrame to list of lists
#             data_to_write = [summary.columns.tolist()] + summary.astype(str).values.tolist()
#             worksheet.update(data_to_write)

#             show_popup("billing code platter report created successfully!", type = "success")
#     except Exception as e:
#         print(f"Error in billing code status platter function: {e}")
#         show_popup(f"Error in billing code status platter function : {e}", type = "error")


# def pdna_status_platter(merged_data):
#     try:
#         spreadsheet = connect_gsheet()

#         # To write data in google sheet
#         # Open or create the worksheet
#         try:
#             worksheet = spreadsheet.worksheet("PDNA")
#         except gspread.WorksheetNotFound:
#             worksheet = spreadsheet.add_worksheet("PDNA", rows=5000, cols=30)
            
#         # Clear existing data and write fresh
#         worksheet.clear()

#         merged_data = merged_data[merged_data["status_code"].str.upper().str.strip() == "PART_DECLARED_NOT_AVAILABLE"]
        
#         if not merged_data.empty:
#             summary = merged_data.groupby("circle").agg({
#                 "red_call_flag": "sum", "enc1_flag": "sum", "enc2_flag": "sum", "enc3_flag": "sum"
#             }).reset_index()

#             summary = summary.rename(columns={
#                 "circle": "Circle", "red_call_flag": "Red Call",
#                 "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
#             })

#             summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
#             summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
#             summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]
            
#             col_order = ["Circle", "Red Call", "Encroaching1", "Platter1","Encroaching2", "Platter2","Encroaching3", "Platter3"]
#             summary = summary[col_order]

#             # Droping the rows where Platter2 is zero
#             summary= summary[summary["Platter2"] != 0]

#             # Sort by Platter1 descending BEFORE adding Total row
#             summary = summary.sort_values("Platter1", ascending=False).reset_index(drop=True)
            
#             totals = summary.select_dtypes(include='number').sum()
#             total_row = pd.DataFrame([totals])
#             total_row["Circle"] = "Total"
#             summary = pd.concat([summary, total_row], ignore_index=True)
            
#             # Convert DataFrame to list of lists
#             data_to_write = [summary.columns.tolist()] + summary.astype(str).values.tolist()
#             worksheet.update(data_to_write)
            
#             show_popup("PDNA platter report created successfully!", type = "success")
#     except Exception as e:
#         print(f"Error in pdna_status_platter function is : {e}")
#         show_popup(f"Error in pdna_status_platter function : {e}", type = "error")
    


# def work_in_progress_status_platter(merged_data):
#     try:
#         spreadsheet = connect_gsheet()

#         # To write data in google sheet
#         # Open or create the worksheet
#         try:
#             worksheet = spreadsheet.worksheet("WORK_IN_PROGRESS")
#         except gspread.WorksheetNotFound:
#             worksheet = spreadsheet.add_worksheet("WORK_IN_PROGRESS", rows=5000, cols=30)

#         # Clear existing data and write fresh
#         worksheet.clear()
        
#         merged_data = merged_data[(merged_data["status_code"].str.upper().str.strip() == "RAN_C_CN_DUE") | (merged_data["status_code"].str.upper().str.strip() == "WORK_IN_PROGRESS")]
        
#         if not merged_data.empty:
#             summary = merged_data.groupby("circle").agg({
#                 "red_call_flag": "sum", "enc1_flag": "sum", "enc2_flag": "sum", "enc3_flag": "sum"
#             }).reset_index()

#             summary = summary.rename(columns={
#                 "circle": "Circle", "red_call_flag": "Red Call",
#                 "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
#             })

#             summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
#             summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
#             summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]
            
#             col_order = ["Circle", "Red Call", "Encroaching1", "Platter1","Encroaching2", "Platter2","Encroaching3", "Platter3"]
#             summary = summary[col_order]

#             # Droping the rows where Platter2 is zero
#             summary= summary[summary["Platter2"] != 0]

#             # Sort by Platter1 descending BEFORE adding Total row
#             summary = summary.sort_values("Platter1", ascending=False).reset_index(drop=True)
            
#             totals = summary.select_dtypes(include='number').sum()
#             total_row = pd.DataFrame([totals])
#             total_row["Circle"] = "Total"
#             summary = pd.concat([summary, total_row], ignore_index=True)
            
#             # Convert DataFrame to list of lists
#             data_to_write = [summary.columns.tolist()] + summary.astype(str).values.tolist()
#             worksheet.update(data_to_write)
            
#             show_popup("WORK_IN_PROGRESS report created successfully!", type = "success")
#     except Exception as e:
#         print(f"Error in ran_cn_due_status_platter function : {e}")
#         show_popup(f"Error in WORK_IN_PROGRESS report function : {e}", type = "error")



# def ran_cn_due_status_platter(merged_data):

#     try:
#         spreadsheet = connect_gsheet()

#         # To write data in google sheet
#         # Open or create the worksheet
#         try:
#             worksheet = spreadsheet.worksheet("RAN_CN_DUE")
#         except gspread.WorksheetNotFound:
#             worksheet = spreadsheet.add_worksheet("RAN_CN_DUE", rows=5000, cols=30)

#         # Clear existing data and write fresh
#         worksheet.clear()
        
#         merged_data = merged_data[(merged_data["status_code"].str.upper().str.strip() == "RAN_C_CN_DUE") | (merged_data["status_code"].str.upper().str.strip() == "RAN_D_CN_DUE")]
        
#         if not merged_data.empty:
#             summary = merged_data.groupby("circle").agg({
#                 "red_call_flag": "sum", "enc1_flag": "sum", "enc2_flag": "sum", "enc3_flag": "sum"
#             }).reset_index()

#             summary = summary.rename(columns={
#                 "circle": "Circle", "red_call_flag": "Red Call",
#                 "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
#             })

#             summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
#             summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
#             summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]
            
#             col_order = ["Circle", "Red Call", "Encroaching1", "Platter1","Encroaching2", "Platter2","Encroaching3", "Platter3"]
#             summary = summary[col_order]

#             # Droping the rows where Platter2 is zero
#             summary= summary[summary["Platter2"] != 0]

#             # Sort by Platter1 descending BEFORE adding Total row
#             summary = summary.sort_values("Platter1", ascending=False).reset_index(drop=True)
            
#             totals = summary.select_dtypes(include='number').sum()
#             total_row = pd.DataFrame([totals])
#             total_row["Circle"] = "Total"
#             summary = pd.concat([summary, total_row], ignore_index=True)

            
#             # Convert DataFrame to list of lists
#             data_to_write = [summary.columns.tolist()] + summary.astype(str).values.tolist()
#             worksheet.update(data_to_write)
            
#             show_popup("RAN_CN_DUE report created successfully!", type = "success")
#     except Exception as e:
#         print(f"Error in ran_cn_due_status_platter function : {e}")
#         show_popup(f"Error in RAN_CN_DUE report function : {e}", type = "error")



# def dealerwise_platter(merged_data):
#     try:
#         spreadsheet = connect_gsheet()

#         # To write data in google sheet
#         # Open or create the worksheet
#         try:
#             worksheet = spreadsheet.worksheet("Dealer Platter")
#         except gspread.WorksheetNotFound:
#             worksheet = spreadsheet.add_worksheet("Dealer Platter", rows=5000, cols=30)

#         # Clear existing data and write fresh
#         worksheet.clear()

#         filtered_data = merged_data[
#         (merged_data["status_code"].str.upper().str.strip().isin(["RAN_C_CN_DUE", "RAN_D_CN_DUE"])) |
#         (~merged_data["status_code"].str.upper().str.strip().isin(["RAN_C_CN_DUE", "RAN_D_CN_DUE"]) & 
#         (merged_data["customer_type"].str.lower().str.strip() == "dealer"))
#         ]

#         if not filtered_data.empty:
#             summary = filtered_data.groupby("circle").agg({
#                 "red_call_flag": "sum", "enc1_flag": "sum", "enc2_flag": "sum", "enc3_flag": "sum"
#             }).reset_index()

#             summary = summary.rename(columns={
#                 "circle": "Circle", "red_call_flag": "Red Call",
#                 "enc1_flag": "Encroaching1", "enc2_flag": "Encroaching2", "enc3_flag": "Encroaching3"
#             })

#             summary["Platter1"] = summary["Red Call"] + summary["Encroaching1"]
#             summary["Platter2"] = summary["Platter1"] + summary["Encroaching2"]
#             summary["Platter3"] = summary["Platter2"] + summary["Encroaching3"]
            
#             col_order = ["Circle", "Red Call", "Encroaching1", "Platter1","Encroaching2", "Platter2","Encroaching3", "Platter3"]
#             summary = summary[col_order]
            
#             # Droping the rows where Platter2 is zero
#             summary= summary[summary["Platter2"] != 0]

#             # Sort by Platter1 descending BEFORE adding Total row
#             summary = summary.sort_values("Platter1", ascending=False).reset_index(drop=True)


#             totals = summary.select_dtypes(include='number').sum()
#             total_row = pd.DataFrame([totals])
#             total_row["Circle"] = "Total"
#             summary = pd.concat([summary, total_row], ignore_index=True)
            
#             # Convert DataFrame to list of lists
#             data_to_write = [summary.columns.tolist()] + summary.astype(str).values.tolist()
#             worksheet.update(data_to_write)

#             show_popup("dealerwise_platter report created successfully!", type = "success")
#     except Exception as e:
#         print(f"Error in dealerwise_platter function : {e}")
#         show_popup(f"Error in dealerwise_platter report function : {e}", type = "error")


def apply_formatting(workbook, worksheet, summary, title_text):
    try:
        fmt_header     = workbook.add_format({'bold': True, 'bg_color': '#FFFF00', 'border': 1, 'align': 'center'})
        fmt_main_title = workbook.add_format({'bold': True, 'bg_color': '#FFFF00', 'border': 1, 'align': 'center', 'font_size': 14})
        fmt_red        = workbook.add_format({'bold': True, 'bg_color': "#FF0000", 'border': 1, 'align': 'center'})
        fmt_orange     = workbook.add_format({'bg_color': "#FFBF00", 'border': 1, 'align': 'center', 'bold': True})
        fmt_green      = workbook.add_format({'bg_color': "#8BF58B", 'border': 1, 'align': 'center', 'bold': True})
        fmt_white      = workbook.add_format({'border': 1, 'align': 'center', 'bold': True})

        # Single format for entire Total row
        fmt_total = workbook.add_format({'bold': True, 'bg_color': '#1F4E79', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})

        # 1. Write Main Title
        report_date = datetime.now().strftime("%d-%b-%Y")
        worksheet.merge_range('A1:H1', f"{title_text} --- {report_date}", fmt_main_title)

        total_row_idx = len(summary) - 1

        # # 2. Apply Data Formatting
        # for row_num in range(2, len(summary) + 2):
        #     df_row_idx = row_num - 2
        #     is_total   = (df_row_idx == total_row_idx)

        #     for col_num in range(6):
        #         value = summary.iloc[df_row_idx, col_num]

        #         if is_total:
        #             # Same color for all 6 columns in total row
        #             worksheet.write(row_num, col_num, value, fmt_total)
        #         else:
        #             fmt = [fmt_white, fmt_red, fmt_orange, fmt_green, fmt_orange, fmt_green][col_num]
        #             worksheet.write(row_num, col_num, value, fmt)


        for row_num in range(2, len(summary) + 2):
            df_row_idx = row_num - 2

            status_value = str(summary.iloc[df_row_idx, 0]).upper()
            is_total = "TOTAL" in status_value   # ✅ key change

            for col_num in range(8):
                value = summary.iloc[df_row_idx, col_num]

                if is_total:
                    worksheet.write(row_num, col_num, value, fmt_total)
                else:
                    fmt = [fmt_white, fmt_red, fmt_orange, fmt_green, fmt_orange, fmt_green, fmt_orange, fmt_green][col_num]
                    worksheet.write(row_num, col_num, value, fmt)
                    
        # 3. Write Column Headers
        for col_num, value in enumerate(summary.columns.values):
            worksheet.write(1, col_num, value, fmt_header)

        worksheet.set_column('A:F', 18)

    except Exception as e:
        print(f"Error in Formatting {worksheet} is : {e}")
        show_popup(f"Error in Formatting {worksheet} is : {e}", type="error")


# def apply_tracker_excel_formatting(workbook, worksheet, df, title_text):
#     try:
#         # --- Formats ---
#         fmt_title   = workbook.add_format({'bold': True, 'bg_color': "#EA98B9", 'border': 1, 'align': 'center', 'font_size': 14})
#         fmt_header  = workbook.add_format({'bold': True, 'bg_color': "#8CB2ED", 'border': 1, 'align': 'center'})
#         fmt_default = workbook.add_format({'bold': True, 'bg_color': "#F2E7DE", 'border': 1, 'align': 'center'})
#         fmt_green   = workbook.add_format({'bg_color': '#8BF58B', 'border': 1, 'align': 'center', 'bold': True})
#         fmt_blue    = workbook.add_format({'bg_color': '#63B3ED', 'border': 1, 'align': 'center', 'bold': True})

#         # Single format for entire Total row
#         fmt_total   = workbook.add_format({'bold': True, 'bg_color': '#1F4E79', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})

#         headers  = df.columns.tolist()
#         num_cols = len(headers)
#         total_row_idx = len(df) - 1   # Last row = Total row

#         # --- Merge title row across all columns ---
#         last_col_letter = chr(ord('A') + num_cols - 1)
#         report_date = datetime.now().strftime("%d-%b-%Y")
#         worksheet.merge_range(f'A1:{last_col_letter}1', f"{title_text} --- {report_date}", fmt_title)

#         # --- Write headers in row 2 ---
#         for col_idx, col_name in enumerate(headers):
#             worksheet.write(1, col_idx, col_name, fmt_header)

#         # --- Find P1 and P2 column indices ---
#         p1_cols = [i for i, h in enumerate(headers) if h.endswith("P1")]
#         p2_cols = [i for i, h in enumerate(headers) if h.endswith("P2")]

#         # --- Write data rows with conditional formatting ---
#         for row_idx in range(len(df)):
#             is_total = (row_idx == total_row_idx)   # Check if Total row

#             for col_idx in range(num_cols):
#                 value = df.iloc[row_idx, col_idx]

#                 # Total row → same color for all columns
#                 if is_total:
#                     fmt = fmt_total

#                 elif col_idx in p1_cols:
#                     pair_idx = p1_cols.index(col_idx)
#                     p2_idx   = p2_cols[pair_idx] if pair_idx < len(p2_cols) else None
#                     try:
#                         p1_val = int(float(value))
#                         p2_val = int(float(df.iloc[row_idx, p2_idx])) if p2_idx else 1
#                     except:
#                         p1_val, p2_val = 1, 1

#                     if p1_val == 0 and p2_val == 0:
#                         fmt = fmt_green
#                     elif p1_val == 0:
#                         fmt = fmt_blue
#                     else:
#                         fmt = fmt_default

#                 elif col_idx in p2_cols:
#                     pair_idx = p2_cols.index(col_idx)
#                     p1_idx   = p1_cols[pair_idx] if pair_idx < len(p1_cols) else None
#                     try:
#                         p2_val = int(float(value))
#                         p1_val = int(float(df.iloc[row_idx, p1_idx])) if p1_idx else 1
#                     except:
#                         p1_val, p2_val = 1, 1

#                     if p1_val == 0 and p2_val == 0:
#                         fmt = fmt_green
#                     # elif p1_val == 0:
#                     #     fmt = fmt_blue
#                     else:
#                         fmt = fmt_default

#                 else:
#                     fmt = fmt_default

#                 worksheet.write(row_idx + 2, col_idx, str(value), fmt)

#         # --- Set column widths ---
#         worksheet.set_column(0, 0, 12)
#         worksheet.set_column(1, 1, 15)
#         worksheet.set_column(2, num_cols - 1, 12)

#     except Exception as e:
#         print(f"Error in apply_tracker_excel_formatting: {e}")
#         show_popup(f"Error in tracker Excel formatting: {e}", type="error")


def fetch_and_format_report():
    try:
        spreadsheet = connect_gsheet()
        output = io.BytesIO()

        # Regular sheets with standard formatting
        sheet_configs = [
            {"sheet": "Daily Circlewise Platter", "title": "All Circlewise Platter And Targets"},
            {"sheet": "Statuswise Platter",        "title": "Statuswise Platter And Targets"},
            # {"sheet": "Billing Code",              "title": "Billing Code Problem"},
            # {"sheet": "PDNA",                      "title": "PDNA"},
            # {"sheet": "RAN_CN_DUE",                "title": "RAN_C/D_CN_DUE Calls On The Platter And Targets"},
            # {"sheet": "WORK_IN_PROGRESS","title": "WORK_IN_PROGRESS Calls On The Platter And Targets"},
            # {"sheet": "Dealer Platter",            "title": "Dealer Circlewise Platter And Targets"},
        ]

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

            # --- Standard sheets ---
            for config in sheet_configs:
                sheet_name = config["sheet"]
                title_text = config["title"]
                try:
                    ws       = spreadsheet.worksheet(sheet_name)
                    raw_data = ws.get_all_values()

                    if not raw_data or len(raw_data) < 2:
                        print(f"No data found in sheet: {sheet_name}")
                        continue

                    df = pd.DataFrame(raw_data[1:], columns=raw_data[0])

                    # Convert numeric columns
                    for col in df.columns[1:]:
                        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

                    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
                    apply_formatting(writer.book, writer.sheets[sheet_name], df, title_text)
                    print(f"✅ Sheet written: {sheet_name}")

                except gspread.WorksheetNotFound:
                    print(f"⚠️ Sheet not found, skipping: {sheet_name}")
                    continue

            # # --- Tracker sheet (special formatting) ---
            # try:
            #     tracker_ws   = spreadsheet.worksheet("Tracker")
            #     tracker_data = tracker_ws.get_all_values()

            #     if tracker_data and len(tracker_data) >= 2:
            #         tracker_df = pd.DataFrame(tracker_data[1:], columns=tracker_data[0])

            #         tracker_df.to_excel(writer, sheet_name="Tracker", index=False, startrow=1)

            #         # ✅ Use special tracker formatting
            #         apply_tracker_excel_formatting(
            #             writer.book,
            #             writer.sheets["Tracker"],
            #             tracker_df,
            #             "Daily Tracker"
            #         )
            #         print("✅ Tracker sheet written")
            #     else:
            #         print("⚠️ No data in Tracker sheet")

            # except gspread.WorksheetNotFound:
            #     print("⚠️ Tracker sheet not found, skipping")

            # ----- Detailed Raw Data -----
            try:
                raw_ws = spreadsheet.worksheet("Detailed_Data")
                raw_data = raw_ws.get_all_values()
                
                if raw_data and len(raw_data) >= 2:
                    raw_df = pd.DataFrame(raw_data[1:], columns=raw_data[0])

                    raw_df = raw_df[["circle","status_code","service_id", "customer_name","phone1","company_name","provider_phone1","category"]]

                    raw_df = raw_df[(raw_df["category"] == "Red Call") | (raw_df["category"] == "Encroaching1") | (raw_df["category"] == "Encroaching2") | (raw_df["category"] == "Encroaching3")]

                    raw_df = raw_df[raw_df["category"].isin(["Red Call", "Encroaching1", "Encroaching2", "Encroaching3"])]

                    raw_df["category"] = pd.Categorical(
                        raw_df["category"],
                        categories=["Red Call", "Encroaching1", "Encroaching2", "Encroaching3"],
                        ordered=True
                    )

                    raw_df= raw_df.sort_values("category")

                    raw_df.to_excel(writer, sheet_name="Raw_Data", index=False)
                    print("✅ Raw Data sheet written")
                else:
                    print("No raw data found !!")

            except  gspread.WorksheetNotFound:
                print("⚠️ Detailed_Data sheet not found, skipping")

        show_popup("Platter report ready to download!", type="success")
        return output.getvalue()

    except Exception as e:
        print(f"Error in fetch_and_format_report: {e}")
        show_popup(f"Error generating report: {e}", type="error")
        return None


# def send_email(sender_email, app_password, recipient_email, cc_emails, file_bytes):
#     IST = pytz.timezone('Asia/Kolkata')
#     msg = MIMEMultipart()
#     msg['From'] = sender_email

#     # Ensure recipient_email is list
#     if isinstance(recipient_email, str):
#         recipient_email = [recipient_email]

#     if isinstance(cc_emails, str):
#         cc_emails = [cc_emails]

#     # Set headers properly
#     msg['To'] = ", ".join(recipient_email)
#     msg['Cc'] = ", ".join(cc_emails)
#     msg["Subject"] = "Daily Platter Report"

#     # Email body
#     html = "<html><body>Hello, <p>PFA report.</p></body></html>"
#     msg.attach(MIMEText(html, "html"))

#     # 📎 Attachment
#     attachment = MIMEApplication(file_bytes, _subtype="xlsx")
#     attachment.add_header(
#         'Content-Disposition',
#         'attachment',
#         # filename="service_platter_report.xlsx"
#         filename=f"service_platter_report_{datetime.now(IST).strftime('%Y%m%d_%H%M')}.xlsx"
#     )
#     msg.attach(attachment)

#     # Combine all recipients
#     all_recipients = recipient_email + cc_emails

#     try:

#         server = smtplib.SMTP("smtp.gmail.com", 587)
#         server.ehlo()
#         server.starttls()
#         server.ehlo()
#         server.login(sender_email, app_password)
#         print("Login successful...!!!")
#         server.sendmail(sender_email, all_recipients, msg.as_string())

#         print("✅ Email sent with attachment!")

#     except Exception as e:
#         print(f"❌ Error: {e}")

#     finally:
#         try:
#             server.quit()
#         except:
#             pass

