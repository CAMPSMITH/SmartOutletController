import streamlit as st
from streamlit.logger import get_logger
from smartstrip import ConfigurationError,UnknownDeviceError,SmartStrip
import os
import pandas as pd
from pathlib import Path
from datetime import datetime

logger = get_logger(__name__)
class ConfigurationError(Exception):
    pass

# ---  Check Required Environment Variables
required_env_vars = []

for env_var in required_env_vars:
    if env_var not in os.environ:
        logger.error(f"Environment Variables {env_var} is missing")
        raise ConfigurationError(f"Environment Variables {env_var} is missing")
    logger.info(f"{env_var}={os.environ[env_var]}")

if 'KASA_OUTLET_CONFIG' in os.environ:
    strip = SmartStrip(logger=logger,config_path=Path(os.environ['KASA_OUTLET_CONFIG']))
else:
    strip = SmartStrip(logger=logger)

# Set page title
st.title('CAMPSmith Smart Home')

with st.expander("config"):
    st.write(strip.config)

df = strip.get_events_df()
df['event_at'] = df['event_at'].astype('str')
df['event time'] = df['event_at'].apply(lambda t: datetime.fromtimestamp(int(float(t))).isoformat())
st.dataframe(df[["device_key","current_state","event","event_at","event time"]],hide_index=True)
