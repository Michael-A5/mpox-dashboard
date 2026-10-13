"""
db.py
Database connection setup.
- Local development: builds a local PostgreSQL connection from .env.
- Hosted deployment: reads DB_CONNECTION_STRING from Streamlit secrets, if you add one.
- If neither exists, is_configured() is False and the app runs in demo mode
  (reads data/demo_line_list.parquet, uploads disabled).
"""
import os

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()


def get_connection_string():
    # 1. Streamlit secrets (only present if added on a hosted deployment)
    try:
        if "DB_CONNECTION_STRING" in st.secrets:
            return st.secrets["DB_CONNECTION_STRING"]
    except Exception:
        pass

    # 2. Local PostgreSQL, from .env
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if all([host, port, name, user, password]):
        return URL.create(
            "postgresql+pg8000",
            username=user,
            password=password,
            host=host,
            port=int(port),
            database=name,
        )

    return None


def is_configured():
    return get_connection_string() is not None


@st.cache_resource
def get_engine():
    connection = get_connection_string()
    if connection is None:
        raise RuntimeError("No database configured.")
    return create_engine(connection)