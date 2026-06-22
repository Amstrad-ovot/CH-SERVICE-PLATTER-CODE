import streamlit as st

def apply_sidebar_styles():
    st.markdown("""
        <style>
        /* Sidebar background */
        [data-testid="stSidebar"] {
            background: linear-gradient(160deg, #1e3a5f 0%, #16213e 100%);
        }

        /* ✅ Collapse/expand arrow button - white color */
        [data-testid="stSidebarCollapseButton"] button {
            color: white !important;
            # border-radius: 50% !important;
        }

        [data-testid="stSidebarCollapseButton"] button svg {
            fill: white !important;
            stroke: white !important;
        }

        /* ✅ Also target the arrow on the main page (expand button) */
        [data-testid="stSidebarCollapsedControl"] button {
            color: white !important;
            background-color: #1e3a5f !important;
            border-radius: 50% !important;
        }

        [data-testid="stSidebarCollapsedControl"] button svg {
            fill: white !important;
            stroke: white !important;
        }

        /* Title styling */
        .sidebar-title {
            color: #ffffff;
            font-size: 20px;
            font-weight: 700;
            padding: 10px 0 6px 0;
            letter-spacing: 0.5px;
        }

        .sidebar-subtitle {
            color: #7f9fbf;
            font-size: 11px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            margin-bottom: 5px;
        }

        /* Nav buttons */
        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            background-color: rgba(255,255,255,0.05);
            color: #c8d8e8;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 11px 16px;
            font-size: 13px;
            font-weight: 500;
            text-align: left;
            margin-bottom: 6px;
            transition: all 0.2s ease;
        }

        /* Button hover */
        [data-testid="stSidebar"] .stButton > button:hover {
            background-color: rgba(99, 179, 237, 0.15) !important;
            color: #63b3ed !important;
            border-color: #63b3ed !important;
        }

        /* Button active */
        [data-testid="stSidebar"] .stButton > button:focus {
            background-color: rgba(99, 179, 237, 0.2) !important;
            color: #63b3ed !important;
            border-color: #63b3ed !important;
        }

        /* Divider */
        [data-testid="stSidebar"] hr {
            border-color: rgba(255,255,255,0.1);
            margin: 12px 0;
        }

        /* Caption / footer */
        [data-testid="stSidebar"] .stCaption {
            color: #4a6a8a !important;
            font-size: 11px;
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)


def render_sidebar():
    apply_sidebar_styles()

    with st.sidebar:
        # Title
        st.markdown('<p class="sidebar-title">⚙️ Service App</p>', unsafe_allow_html=True)
        st.markdown('<p class="sidebar-subtitle">Report Management</p>', unsafe_allow_html=True)

        st.divider()

        # Navigation
        # st.markdown('<p class="sidebar-subtitle"> Navigation</p>', unsafe_allow_html=True)
        btn_upload    = st.button("📤  Upload & Create Report")
        # btn_dashboard = st.button("📊  View Dashboard")
        # btn_reports = st.button("📌 View Report")

        st.divider()

        # Footer
        st.caption("© 2025 Service App v1.0")

    # Page state
    if btn_upload:
        st.session_state["page"] = "upload"
    # elif btn_dashboard:
    #     st.session_state["page"] = "dashboard"
    # elif btn_reports:
    #     st.session_state["page"] = "report"

    if "page" not in st.session_state:
        st.session_state["page"] = "upload"

    return st.session_state["page"]