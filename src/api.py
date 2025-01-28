from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import httpx
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from .utils import get_config, initialize_devices, get_desired_state
import json
from pydantic import BaseModel



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

config = get_config(logger)

app = FastAPI()

class Plug(BaseModel):
    alias: str
    state: str # on | off

class Trigger(BaseModel):
    time: int # UTC in seconds
    def __str__(self):
        return json.dumps({"time":self.time})

async def process_event(event):
    logger.debug(f"processing event {json.dumps(event)}")
    device = event['device']
    devices_status = await initialize_devices(config['devices'],logger=logger)
    if device in devices_status:
        device_status = devices_status[device]
        # this is the current state of the strip and its plugs
        # for each plug, determine what the current state should be and set to that state if different than current
        if device not in config['devices']:
            logger.error(f"device {device} not found in config. ignoring device in processing trigger ...")
        else:
            for plug_name,plug in device_status.items():
                current_state = 'on' if plug['proxy'].is_on else 'off'
                logger.debug(f"plug {plug_name} is {current_state}")
                if plug_name not in config['devices'][device]['children']:
                    logger.error(f"plug {plug_name} not found in device {device} config. ignoring plug in processing trigger ...")
                    continue
                desired_state = 'on' if get_desired_state(device,config['devices'][device]['timezone'],plug_name,config['devices'][device]['children'][plug_name],logger=logger)=='on' else 'off'
                if desired_state == current_state:
                    logger.info(f"{device}/{plug_name} is already in {desired_state}. no action needed")
                else:
                    logger.info(f"{device}/{plug_name} is {current_state} but should be {desired_state}. setting {device}/{plug_name} {desired_state}")
                    if desired_state=='on':
                        await plug['proxy'].turn_on()
                    else:
                        await plug['proxy'].turn_off()
    else:
        logger.error(f"device ${device} is not found.")

# healthcheck route
@app.get("/api/healthcheck")
async def healthcheck():
    result = {"status":"ok"}
    result['devices'] = await initialize_devices(config['devices'],include_proxy=False,logger=logger)
    return result

@app.exception_handler(500)
async def internal_server_error(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "details": str(exc)}
    )

@app.get("/api/devices")
async def get_devices_state():
    return await initialize_devices(config['devices'],include_proxy=False,logger=logger)

@app.get("/api/device/{device_name:path}")
async def get_device_state(request: Request,device_name:str):
    global config
    if device_name in config['devices']:
        devices_status = await initialize_devices(config['devices'],include_proxy=False,logger=logger)
        if device_name in devices_status:
            return devices_status[device_name]
        else:
            raise HTTPException(status_code=404, detail=f"Device {device_name} not found")
    else:
        raise HTTPException(status_code=404, detail=f"Device {device_name} not found")


@app.get("/api/plug/{device_name:path}/{plug:path}")
async def get_plug_state(request: Request,device_name:str,plug:str):
    global config
    if device_name in config['devices']:
        devices_status = await initialize_devices(config['devices'],include_proxy=False,logger=logger)
        if device_name in devices_status:
            if plug in devices_status[device_name]:
                return devices_status[device_name][plug]
            else:
                raise HTTPException(status_code=404, detail=f"Device {device_name}/{plug} not found")
        else:
            raise HTTPException(status_code=404, detail=f"Device {device_name} not found")
    else:
        raise HTTPException(status_code=404, detail=f"Device {device_name} not found")

@app.post("/api/device/{device_name:path}")
async def update_device(request: Request,device_name:str,plug:Plug):
    """
    curl -X POST http://127.0.0.1:8000/api/device -H "Content-Type: application/json" -d '{"alias":"Oudoor_Left",:"on"}'
    curl -X POST http://127.0.0.1:8000/api/device/GardenOutletStrip -H "Content-Type: application/json" -d '{"alias":"Oudoor_Left","state":"off"}'
    """
    global config
    if device_name in config['devices']:
        devices_status = await initialize_devices(config['devices'],logger=logger)
        if device_name in devices_status:
            logger.info(plug)
            if plug.alias in devices_status[device_name]:
                if plug.state.lower()=='off':
                    await devices_status[device_name][plug.alias]['proxy'].turn_off()
                else:
                    await devices_status[device_name][plug.alias]['proxy'].turn_on()
            return plug
        else:
            raise HTTPException(status_code=404, detail=f"Device {device_name} not found")
    else:
        raise HTTPException(status_code=404, detail=f"Device {device_name} not found")

@app.post("/api/event/{device_name:path}",status_code=202)
async def event(request: Request,device_name:str,trigger:Trigger):
    """
    curl -i -X POST http://127.0.0.1:8000/api/event/GardenOutletStrip -H "Content-Type: application/json" -d '{"time":1738000604}'
    """
    global config
    if device_name in config['devices']:
        event = {
            "device":device_name,
            "time":trigger.time
        }
        await process_event(event)
        return json.dumps(event)
    else:
        raise HTTPException(status_code=404, detail=f"Device {device_name} not found")        