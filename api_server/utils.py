from pathlib import Path
import os
import yaml
import logging
from logging.handlers import RotatingFileHandler
from logging import handlers
from kasa import SmartPlug,SmartStrip
import json
import asyncio
from datetime import datetime, timedelta
import time
import pytz

class ConfigurationError(Exception):
    pass

def validate_config(config_path,config):
    """ Sample Config:
        name: CampSmith
        log_level: INFO
        log_path: /var/log/smartoutletcontroller 
        devices:
            GardenOutletStrip:
                host: 192.168.0.156
                timezone: "America/Los_Angeles"
                type: strip
                children: 
                    TowerGarden:
                        default: 'off'
                        schedule:
                            type: repeating
                            cycle_on: '00:15:00'
                            cycle_off: '00:15:00'
                    Outdoor_Left:
                        default: 'on'
                        schedule:
                            type: daily
                            times: 
                                - cycle_on: '15:00:00'
                                  cycle_off: '15:15:00'
    """
    if 'name' not in config:
        raise ConfigurationError(f"config {config_path} is missing `name`")
    if 'devices' not in config:
        raise ConfigurationError(f"config {config_path} is missing `devices`")
    for device_name,device in config['devices'].items():
        if 'host' not in device:
            raise ConfigurationError(f"config {config_path} has an invalid device configuration.  Device {device_name} is missing `host`. device{json.dumps(device)}")
        if 'timezone' not in device:
            raise ConfigurationError(f"config {config_path} has an invalid device configuration.  Device {device_name} is missing `timezone`. device{json.dumps(device)}")
        if device['timezone'] not in pytz.all_timezones:     
            raise ConfigurationError(f"config {config_path} has an invalid device configuration.  Device {device_name} timezone {device['timezone']} is not valid. device{json.dumps(device)}")
        if 'type' not in device:
            raise ConfigurationError(f"config {config_path} has an invalid device configuration.  Device {device_name} is missing `type`. device{json.dumps(device)}")
        if 'children' not in device:
            raise ConfigurationError(f"config {config_path} has an invalid device configuration.  Device {device_name} is missing `children`. device{json.dumps(device)}")
        if device['type'] not in ['strip']:
            raise ConfigurationError(f"config {config_path} has an invalid device configuration.  Device {device_name} type of {device['type']} is supported. device{json.dumps(device)}")
        for plug_name,plug_config in device['children'].items():
            if 'default' not in plug_config:
                raise ConfigurationError(f"plug configuration for {device_name}/{plug_name} is missing default setting. plug_config: {json.dumps(plug_config)}")
            if 'schedule' in plug_config:
                if plug_config['schedule']['type'] not in ['daily','repeating']:
                    raise ConfigurationError(f"plug configuration for {device_name}/{plug_name} schedule type {plug_config['schedule']['type']} is not supported. plug_config: {json.dumps(plug_config)}")
                if plug_config['schedule']['type']=='daily':
                    if 'times' not in plug_config['schedule']:
                        raise ConfigurationError(f"schedule configuration for {device_name}/{plug_name} is not valid.  It is missing `times` definitions. plug_config: {json.dumps(plug_config)}")
                    if len(plug_config['schedule']['times'])<1:
                        raise ConfigurationError(f"schedule configuration for {device_name}/{plug_name} is not valid.  It is missing `times` definitions. plug_config: {json.dumps(plug_config)}")
                    for time_def in plug_config['schedule']['times']:
                        if 'cycle_on' not in time_def:
                            raise ConfigurationError(f"schedule configuration for {device_name}/{plug_name} is not valid.  Daily time definition is missing `cycle_on`. plug_config: {json.dumps(plug_config)}")
                        if 'cycle_off' not in time_def:
                            raise ConfigurationError(f"schedule configuration for {device_name}/{plug_name} is not valid.  Daily time definition is missing `cycle_off`. plug_config: {json.dumps(plug_config)}")
                        if time.strptime(time_def['cycle_on'], "%H:%M:%S") >= time.strptime(time_def['cycle_off'], "%H:%M:%S"):
                            raise ConfigurationError(f"schedule configuration for {device_name}/{plug_name} is not valid.  The `cycle_on` must be less than `cycle_off`. plug_config: {json.dumps(plug_config)}")
                if plug_config['schedule']['type']=='repeating':
                    if 'cycle_on' not in plug_config['schedule']:
                        raise ConfigurationError(f"schedule configuration for {device_name}/{plug_name} is not valid.  Repeating schedule definition is missing `cycle_on`. plug_config: {json.dumps(plug_config)}")
                    if 'cycle_off' not in plug_config['schedule']:
                        raise ConfigurationError(f"schedule configuration for {device_name}/{plug_name} is not valid.  Repeating schedule definition is missing `cycle_off`. plug_config: {json.dumps(plug_config)}")
    return True

def get_config(logger=None,config_path =Path('/etc/smarthome/campsmith-devices.yml')):
    
    if 'KASA_OUTLET_CONFIG' in os.environ:
        config_path =Path(os.environ['KASA_OUTLET_CONFIG'])
    if not config_path.exists():
        raise ConfigurationError(f"Configuration Missing. config_path={config_path.resolve()} ")

    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
    if config is None:
        raise ConfigurationError(f"Invalid configuration, config is None")

    validate_config(config_path,config)

    if logger is not None:
        log_level = logging.INFO
        if  'log_level' in config:
            if config['log_level'] == 'DEBUG':
                log_level = logging.DEBUG
            elif config['log_level']=='WARNING':
                log_level = logging.WARNING
            elif config['log_level']=='ERROR':
                log_level = logging.ERROR
        logger.setLevel(log_level)

        if  'log_path' in config:
            Path(config['log_path']).mkdir(parents=True, exist_ok=True)
            log_file = f"{config['log_path']}/{config['name']}.log"
            file_handler = handlers.RotatingFileHandler(log_file, maxBytes=(1048576*5), backupCount=7)
            logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]: %(message)s")
            file_handler.setFormatter(logFormatter)
            logger.addHandler(file_handler)

        logger.info(config)

    return config

async def initialize_devices(devices,include_proxy=True,logger=None):
    devices_status={}
    for device_name,device in devices.items():
        if device['type'] not in ['strip']:
            raise ConfigurationError(f"device {device['name']} type {device['type']} is invalid or not yet supported")
        devices_status[device_name]=await initialize(device_name,device,include_proxy=include_proxy,logger=logger)
    return devices_status


async def initialize(device_name,device,include_proxy=True,logger=None):
  """initializes outlet to the default specified.  The outlet parameter has been verified prior to this method call.

  Parameters:
    outlet: a dictionary describing the outlet.  Key fields include 
            `host`, the IP address or hostname of the smart outlet
            `name`, the name of the smart outlet
            `default`, the default state that the outlet should be in.  valid values are `on` or `off`
                   
  """
  device_state={}
  if device['type']=='strip':
    device_info = SmartStrip(device['host'])
    await device_info.update()  # Request the update
    logger.debug(device_info.host)
    for plug in device_info.children:
        device_state[plug.alias]={
            "state":plug.is_on
        }
        if include_proxy:
            device_state[plug.alias]["proxy"]=plug
        logger.debug(f"plug.alias={plug.alias}")
        logger.debug(f"plug.is_on={plug.is_on}")
  return device_state


schedule={} # a global registry for repeating plug to capture when time change should occur

def get_desired_state(device,device_timezone,plug_name,plug_config,logger=None):
    global schedule
    default = plug_config['default'].strip().lower()

    # simple case ... no schedule defined
    if 'schedule' not in plug_config:
        return default

    # when schedules are defined, current time is needed to determine desired state
    tzinfo = pytz.timezone(device_timezone)
    now = datetime.now(tzinfo)
    now_ts = now.timestamp()
    if logger is not None:
        logger.debug(f"now={int(now.timestamp())}")

    if plug_config['schedule']['type']=='daily':
        # these define a set of time blocks, a time to turn on and then a time to turn off
        desired_state = 'off'
        for time_def in plug_config['schedule']['times']:
            cycle_on = time.strptime(time_def['cycle_on'], "%H:%M:%S")
            cycle_off = time.strptime(time_def['cycle_off'], "%H:%M:%S")
            start = now.replace(hour=cycle_on.tm_hour, minute=cycle_on.tm_min,second=cycle_on.tm_sec,microsecond=0)
            start = start.replace(tzinfo=tzinfo)
            start = int(start.timestamp())
            end = now.replace(hour=cycle_off.tm_hour, minute=cycle_off.tm_min,second=cycle_off.tm_sec,microsecond=0)
            end = end.replace(tzinfo=tzinfo)
            end = int(end.timestamp())
            if logger is not None:
                logger.debug(f"tzinfo={tzinfo}")
                logger.debug(f"now_ts={now_ts}")
                logger.debug(f"cycle_on={cycle_on}")
                logger.debug(f"start={start}")
                logger.debug(f"cycle_off={cycle_off}")
                logger.debug(f"end={end}")
                logger.debug(f"now_ts<start?{now_ts<start}")
                logger.debug(f"now_ts>=end?{now_ts>=end}")
                logger.debug(f"start<=now_ts<end?{start}<={now_ts}>{end}")
            if now_ts >= end or now_ts < start:
                if logger is not None:
                    logger.debug(f"now_ts={now_ts} not in range.  start={start}, end={end}")
                continue
            if now_ts >= start and now_ts < end:
                desired_state = 'on'
                if logger is not None:
                    logger.debug(f"now_ts={now_ts} >= start={start} AND  < end={end}, {device}/{plug_name} should be {desired_state}")
                break
        if logger is not None:
            logger.debug(f"Based on schedule config {device}/{plug_name} should be {desired_state}")
        return desired_state
    
    if plug_config['schedule']['type']=='repeating':
        if device not in schedule:
            schedule[device]={}
        if plug_name not in schedule[device]:
            # since this is a new initialization
            # set desired state to on
            # schedule the off to be now + cycle_off
            cycle_on = time.strptime(plug_config['schedule']['cycle_on'], "%H:%M:%S")
            duration = cycle_on.tm_hour*3600+cycle_on.tm_min*60+cycle_on.tm_sec
            end = int(now_ts + duration)
            schedule[device][plug_name]={
                "time":end,
                "state":"off"
            }
            return 'on'
        plug_schedule = schedule[device][plug_name]
        if 'time' not in plug_schedule:
            if logger is not None:
                logger.error(f"plug_schedule is missing `time`: {json.dumps(plug_schedule)}")
            return default
        if 'state' not in plug_schedule:
            if logger is not None:
                logger.error(f"plug_schedule is missing `state`: {json.dumps(plug_schedule)}")
            return default
        if logger is not None:
            logger.debug(f"now_ts={now_ts}")
            logger.debug(f"schedule = {json.dumps(schedule)}")
            logger.debug(f"plug_schedule = {json.dumps(plug_schedule)}")
        if now_ts > plug_schedule['time']:
            if logger is not None:
                # time has come to change state of repeating device plug
                # set device to specified state
                # schedule next event to be now + cycle_on or cycle_off based on desired state
                logger.info(f"time to change {device}/{plug_name} to {plug_schedule['state']}: {json.dumps(plug_schedule)}")
            if plug_schedule['state']=='on':
                cycle_on = time.strptime(plug_config['schedule']['cycle_on'], "%H:%M:%S")
                duration = cycle_on.tm_hour*3600+cycle_on.tm_min*60+cycle_on.tm_sec
                end = int(now_ts + duration)
                schedule[device][plug_name]={
                    "time":end,
                    "state":"off"
                }
                return 'on'
            else:
                cycle_off = time.strptime(plug_config['schedule']['cycle_off'], "%H:%M:%S")
                duration = cycle_off.tm_hour*3600+cycle_off.tm_min*60+cycle_off.tm_sec
                end = int(now_ts + duration)
                schedule[device][plug_name]={
                    "time":end,
                    "state":"on"
                }
                return 'off'
        else:
            return 'on' if plug_schedule['state']=='off' else 'off'
    return default
