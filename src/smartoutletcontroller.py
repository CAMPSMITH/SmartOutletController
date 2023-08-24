import sys
import logging
from logging.handlers import RotatingFileHandler
from logging import handlers
from datetime import datetime, timedelta
import time
from pathlib import Path
import asyncio
import yaml
import fire
from kasa import SmartPlug,SmartStrip

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s] - %(message)s")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logFormatter)
logger.addHandler(console_handler)

class ConfigError(Exception):
   pass

def is_valid(plug_config,events,new_event,now):
  if len(events)<1:
    return True
  next_day = now.replace(hour=0,minute=0,second=0) + timedelta(days=1)  
  for event in events:
    # if event requests same state as default state, ignore
    if new_event['entry']['state']==plug_config['default']:
      logger.warning(f"{new_event} conflicts with plug default state, it is ignored")
      return False 
    # if new_event conflicts with other events, log warning and ignore by returning False
    if new_event['start'] >= event['start'] and new_event['start'] <= event['end']:
      logger.warning(f"{new_event} conflicts with {event}, it is ignored")
      return False 
    if new_event['end'] >= event['start'] and new_event['end'] <= event['end']:
      logger.warning(f"{new_event} conflicts with {event}, it is ignored")
      return False 
    if new_event['end']>=int(next_day.timestamp()):
      # this entry spans into the following day, need to assess if it conflicts with tomorrow's schedule
      logger.debug(f"{new_event} spans into the following day")
      if new_event['end'] - 24*60*60  >= event['start'] and new_event['end'] - 24*60*60 <= event['end']:
        logger.warning(f"{new_event} conflicts with {event}, it is ignored")
        return False 
  return True

def get_desired_state(plug_config):
  if 'default' not in plug_config:
    raise ConfigError(f"plug configuration for {plug_config['name']} is missing default setting.")
  default = plug_config['default'].strip().lower()=='on' # True if 'on' else False
  if 'schedule' in plug_config:
    # parse schedule and determine desired current state
    now = datetime.now()
    logger.debug(f"now={int(now.timestamp())}")
    events = []
    for entry in plug_config['schedule']:
      if 'start' not in entry:
        raise ConfigError(f"start is missing from schedule configuration for {plug_config['name']}: {entry}")
      if 'duration' not in entry:
        raise ConfigError(f"duration is missing from schedule configuration for {plug_config['name']}: {entry}")
      event_start_time = time.strptime(entry['start'], "%H:%M:%S")
      event_duration_time = time.strptime(entry['duration'], "%H:%M:%S")
      event_start = now.replace(hour=event_start_time.tm_hour,
                                minute=event_start_time.tm_min,
                                second=event_start_time.tm_sec)
      event_end = event_start + timedelta(
        hours=event_duration_time.tm_hour,
        minutes=event_duration_time.tm_min,
        seconds=event_duration_time.tm_sec,
      )
      event = {'entry':entry,'start':int(event_start.timestamp()),'end':int(event_end.timestamp())}
      logger.debug(f"event = {event}")
      if is_valid(plug_config,events,event,now):
        events.append(event)
    logger.debug(events)
    desired_state = default
    for event in events:
      if int(now.timestamp()) >= event['start'] and int(now.timestamp()) < event['end']:
        desired_state = event['entry']['state'].strip().lower()=='on'
    return desired_state
  return default

async def initialize(device,_logger):
  """initializes outlet to the default specified.  The outlet parameter has been verified prior to this method call.

  Parameters:
    outlet: a dictionary describing the outlet.  Key fields include 
            `host`, the IP address or hostname of the smart outlet
            `name`, the name of the smart outlet
            `default`, the default state that the outlet should be in.  valid values are `on` or `off`
                   
  """
  if device['type']=='strip':
    device_info = SmartStrip(device['host'])
    await device_info.update()  # Request the update
    for plug in device_info.children:
      logger.debug(device['children'])
      logger.debug(device_info)
      logger.debug(plug)
      if plug.alias in device['children']:
        # only assess and take action if config exists for device plug
        logger.debug(f"config info found for {plug.alias}: {device['children'][plug.alias]}")
        current_state = plug.is_on
        desired_state = get_desired_state(device['children'][plug.alias])
        logger.info(f"{plug.alias} is currently {'on' if current_state else 'off'}, desired state is {'on' if desired_state else 'off'}")
        if current_state == desired_state:
          logger.debug(f"no action needed for {plug.alias}")
        else:
          logger.debug(f"{plug.alias} to be set to {'on' if desired_state else 'off'}")
          if desired_state:
            await plug.turn_on()
            logger.info(f"{plug.alias} turned on")
          else:
            await plug.turn_off()
            logger.info(f"{plug.alias} turned off")

def run(name="campsmith",debug='false',logPath='/var/log/smartoutletcontroller',configPath='/etc/smartoutletcontroller',):
    log_level = logging.DEBUG if debug.lower().strip()=='true' else logging.INFO
    logger.setLevel(log_level)
    if name is not None:
      file_handler = handlers.RotatingFileHandler(f"{logPath}/{name}.log", maxBytes=(1048576*5), backupCount=7)
      file_handler.setFormatter(logFormatter)
      logger.addHandler(file_handler)
    logger.info('starting ...')
    config = None
    config_path = Path(f"{configPath}/{name}.yml")
    try:
      if not config_path.exists():
        raise ConfigError(f"Invalid configuration. {config_path.absolute()} does not exist")
      if not config_path.is_file():
        raise ConfigError(f"Invalid configuration, expected {config_path.absolute()} to be a file")
      with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
      if config is None:
        raise ConfigError(f"Invalid configuration, config is None")
      logger.debug(config)
      for device in config['devices']:
        logger.debug(device)
        if 'name' not in device:
          raise ConfigError(f"device configuration is missing name: {device}")
        if 'host' not in device:
          raise ConfigError(f"host configuration is missing for {device['name']}")
        if 'type' not in device:
          raise ConfigError(f"type configuration is missing for {device['name']}")
        if device['type'] not in ['strip']:
          raise ConfigError(f"device type of {device['type']} is invalid or not yet supported")
        asyncio.run(initialize(device=device,_logger=logger))
    except ConfigError as err:
      logger.exception(err)   
    except Exception as err:
      logger.exception(err)   
    finally:
      logger.info('done')
    
if __name__ == '__main__':
  fire.Fire(run)