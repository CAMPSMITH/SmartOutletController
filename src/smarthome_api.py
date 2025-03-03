from fastapi import FastAPI
from fastapi.exceptions import HTTPException
import logging
import os
from smartstrip import ConfigurationError,UnknownDeviceError,SmartStrip
from pathlib import Path
from pydantic import BaseModel
from datetime import datetime

class PlugSet(BaseModel):
    state: int

# --- Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s: %(asctime)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ---  Check Required Environment Variables
required_env_vars = []

for env_var in required_env_vars:
    if env_var not in os.environ:
        logger.error(f"Environment Variables {env_var} is missing")
        raise ConfigurationError(f"Environment Variables {env_var} is missing")
    logger.info(f"{env_var}={os.environ[env_var]}")

api = FastAPI()

if 'KASA_OUTLET_CONFIG' in os.environ:
    strip = SmartStrip(logger=logger,config_path=Path(os.environ['KASA_OUTLET_CONFIG']))
else:
    strip = SmartStrip(logger=logger)

# healthcheck route
# curl http://127.0.0.1:8000/healthcheck
@api.get("/healthcheck")
async def healthcheck():
    global strip
    return strip.status()

# plug set route
# curl --header "Content-Type: application/json" \
#      --request POST \
#      --data '{"state":1}' \
#      http://127.0.0.1:8000/plug/TowerGarden
@api.post("/plug/{plug_name:path}")
async def set_plug(plug_name:str,plug_set: PlugSet):
    global strip
    result = None
    try:
        if plug_set.state==1:
            result = strip.on(plug_name)
        else:
            result = strip.off(plug_name)
        return result
    except UnknownDeviceError as unk:
        raise HTTPException(status_code=404, detail=str(unk))

@api.get("/plug/{plug_name:path}")
# curl http://127.0.0.1:8000/plug/TowerGarden
async def get_plug(plug_name:str):
    global strip
    try:
        return {plug_name:strip.get_current_state(plug_name)}
    except UnknownDeviceError as unk:
        raise HTTPException(status_code=404, detail=str(unk))

@api.patch("/plug/{plug_name:path}")
# curl -X PATCH http://127.0.0.1:8000/plug/TowerGarden
async def trigger_plug(plug_name:str):
    global strip
    try:
        return strip.handle(plug_name,int(datetime.now().timestamp()))
    except UnknownDeviceError as unk:
        raise HTTPException(status_code=404, detail=str(unk))
