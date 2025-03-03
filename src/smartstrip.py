# import fire
import logging
import subprocess
import json
import os
import yaml
import time
from pathlib import Path
import sqlite3
import pandas as pd

class ConfigurationError(Exception):
    pass

class UnknownDeviceError(Exception):
    pass

class SmartStrip():
    config = None
    config_path = None
    logger = None
    sqliteConnection = None
    ddl=[
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            device_key VARCHAR(255) UNIQUE NOT NULL,
            current_state INTEGER NOT NULL,
            event_at REAL NOT NULL,
            event VARCHAR(255) NOT NULL,
            created_at REAL DEFAULT (strftime('%s', 'now')),
            created_by INTEGER DEFAULT 1,
            updated_at REAL DEFAULT (strftime('%s', 'now')),
            updated_by INTEGER DEFAULT 1
        );
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_device_key ON events(device_key);"
    ]

    def __init__(self,config_path=None,logger=None):
        if logger is not None:
            self.logger = logger

        if config_path is not None:
            self.config_path = config_path
        self.load_config()
        self.init_db()

    def get_conn(self):
        if self.sqliteConnection is None:
            self.sqliteConnection = sqlite3.connect(self.config["db_path"])
        return self.sqliteConnection
    
    def validate_config(self):
        """ Sample Config:
        name: GardenOutletStrip
        log_level: INFO
        log_path: /var/log/smarthome
        db_path: /var/data/devices.db
        host: 192.168.0.156
        timezone: "America/Los_Angeles"
        type: strip
        plugs: 
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
        if 'name' not in self.config:
            raise ConfigurationError(f"config {self.config_path} is missing `name`")
        if 'host' not in self.config:
            raise ConfigurationError(f"config {self.config_path} is missing `host`")
        if 'log_path' not in self.config:
            raise ConfigurationError(f"config {self.config_path} is missing `log_path`")
        if 'db_path' not in self.config:
            raise ConfigurationError(f"config {self.config_path} is missing `db_path`")
        if 'timezone' not in self.config:
            raise ConfigurationError(f"config {self.config_path} is missing `timezone`")
        if 'type' not in self.config:
            raise ConfigurationError(f"config {self.config_path} is missing `type`")
        if 'plugs' not in self.config:
            raise ConfigurationError(f"config {self.config_path} is missing `plugs`")
        
        if self.config['type'] not in ['strip']:
            raise ConfigurationError(f"{self.config['name']} type {self.config['type']} is not supported")

        device_name=[self.config['name']]
        for plug_name,plug_config in self.config['plugs'].items():
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

    def init_db(self):
        db_path = Path(self.config['db_path'])
        if not db_path.exists():
            if self.logger is not None:
                self.logger.info(f"initializing devices db at {db_path}")
            db_path.parent.mkdir(parents=True,exist_ok=True)
        with self.get_conn() as conn:
            tables_query="SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            cursor = conn.cursor()
            res = cursor.execute(tables_query)
            tables = res.fetchall()
        if tables is None or len(tables)<1:
            self.create_db()

    def create_db(self):
        if self.logger is not None:
            self.logger.info(f"{self.config['db_path']} is not initialized.  initializing schema ...")
        with self.get_conn() as conn:
            for stmt in self.ddl:
                cur = conn.cursor()
                cur.execute(stmt)
                conn.commit()


    def load_config(self):
        if not self.config_path.exists():
            raise ConfigurationError(f"Configuration Missing. config_path={self.config_path.resolve()} ")

        with open(self.config_path, 'r') as config_file:
            config = yaml.safe_load(config_file)
        if config is None:
            raise ConfigurationError(f"Invalid configuration, config is None")
        self.config = config
        self.validate_config()

        if self.logger is not None:
            log_level = logging.INFO
            if  'log_level' in config:
                if config['log_level'] == 'DEBUG':
                    log_level = logging.DEBUG
                elif config['log_level']=='WARNING':
                    log_level = logging.WARNING
                elif config['log_level']=='ERROR':
                    log_level = logging.ERROR
            self.logger.setLevel(log_level)

            if  'log_path' in config:
                Path(config['log_path']).mkdir(parents=True, exist_ok=True)
                log_file = f"{config['log_path']}/{config['name']}.log"
                file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=(1048576*5), backupCount=7)
                logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]: %(message)s")
                file_handler.setFormatter(logFormatter)
                self.logger.addHandler(file_handler)

    def status(self):
        if self.logger is not None:
            self.logger.debug("cmd = status")
        result = subprocess.run(["kasa", "--json", "--host",self.config['host'], "state"], capture_output=True, text=True)
        if result is None:
            return None
        if result.stdout is None:
            return None
        strip = json.loads(result.stdout)
        if 'system' not in strip:
            return None
        if 'get_sysinfo' not in strip['system']:
            return None
        if 'children' not in strip['system']['get_sysinfo']:
            return None
        result = {}
        for plug in strip['system']['get_sysinfo']['children']:
            if 'alias' in plug and 'state' in plug:
                result[plug['alias']]=plug['state']
        return result

    def on(self,plug):
        if self.logger is not None:
            self.logger.debug("cmd = on")
        result = subprocess.run(["kasa", "--json", "--host",self.config['host'], "on","--child",plug], capture_output=True, text=True)
        if result is None:
            if self.logger is not None:
                self.logger.error(f"Unable to set{plug} state.")
            return None
        if result.returncode!= 0:
            if self.logger is not None:
                self.logger.error(f"Error setting {plug} state: [rc={result.returncode}]{result.stderr}")
        return {plug: 1}

    def off(self,plug):
        if self.logger is not None:
            self.logger.debug("cmd = off")
        result = subprocess.run(["kasa", "--json", "--host",self.config['host'], "off","--child",plug], capture_output=True, text=True)
        if result is None:
            if self.logger is not None:
                self.logger.error(f"Unable to set{plug} state.")
            return None
        if result.returncode!= 0:
            if self.logger is not None:
                self.logger.error(f"Error setting {plug} state: [rc={result.returncode}]{result.stderr}")
        return {plug: 0}
    
    def has_events(self,plug):
        key = f"{self.config['name']}/{plug}"
        count=0
        with self.get_conn() as conn:
            count_query = "SELECT count(id) FROM events WHERE device_key = ?"
            cur = conn.cursor()
            count = cur.execute(count_query,(key,)).fetchone()[0]
        return count>0

    def get_default_state(self,plug):
        default = None
        if plug in self.config['plugs']:
            if 'default' in self.config['plugs'][plug]:
                default = self.config['plugs'][plug]['default']
                if self.logger is not None:
                    self.logger.info(f"{plug} default = {default}")
        return 1 if default=='on' else 0

    def get_expected_state(self,plug):
        state = self.get_default_state(plug)
        key = f"{self.config['name']}/{plug}"
        with self.get_conn() as conn:
            get_events_query="SELECT current_state FROM events WHERE device_key = ? ORDER BY event_at ASC LIMIT 1"
            cur = conn.cursor()
            # retrieve events
            state = cur.execute(get_events_query,(key,)).fetchone()[0]
        return int(state)

    def get_current_state(self,plug):
        status = self.status()
        if plug in status:
            return status[plug]
        return None

    def put(self,plug,current_state,event,event_at):
        key = f"{self.config['name']}/{plug}"
        insert_event_query = "INSERT INTO events (device_key,current_state,event,event_at) VALUES(?,?,?,?)"
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(insert_event_query,(key,current_state,json.dumps(event),event_at))
            conn.commit()

    def pop(self,plug,time_mark):
        key = f"{self.config['name']}/{plug}"
        events = []
        # start transaction
        get_events_query="SELECT device_key,event,event_at FROM events WHERE device_key = ? and event_at <= ? ORDER BY event_at DESC"
        delete_events_query="DELETE FROM events WHERE device_key = ? and event_at <= ?"
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute('BEGIN TRANSACTION')

            # retrieve events
            events.extend(cur.execute(get_events_query,(key,time_mark)).fetchall())
            # delete retrieve events
            cur.execute(delete_events_query,(key,time_mark))

        conn.commit()
        return events   #[(device_key,event,event_at),...]
    
    def parse_duration(self,time_span):
        # time_span format is 00:15:00 interpreted as hours:minutes:seconds
        # convert time span into seconds
        time_parts = [int(p) for p in time_span.split(':')]
        if len(time_parts) !=3:
            raise ConfigurationError(f"time_span is not valid.  Expected format `HH:MM:SS` got {time_span}")
        return int(time_parts[0]*60*60)+int(time_parts[1]*60)+time_parts[2]   
         
    def next_event(self,plug_name,current_state,now:int):
        if plug_name not in self.config['plugs']:
            return None
        if 'schedule' not in self.config['plugs'][plug_name]:
            return None
        schedule = self.config['plugs'][plug_name]['schedule']
        if schedule['type'] != 'repeating':
            if self.logger is not None:
                self.logger.error(f"schedule type {schedule['type']} is not supported")

        key = f"{self.config['name']}/{plug_name}"
        duration = 0
        if current_state == 1:
            event = {'set':0}
            duration = self.parse_duration(schedule['cycle_on'])
        if current_state == 0:
            event = {'set':1}
            duration = self.parse_duration(schedule['cycle_off'])
        event_at = now + duration
        return (event,event_at)

    def handle(self,plug_name,time_mark):
        if self.logger is not None:
            self.logger.info(f"handling {plug_name} @ {time_mark}")
        if plug_name not in self.config['plugs']:
            raise UnknownDeviceError(f"{plug_name} not valid")
        # default_state = self.get_default_state(plug_name)
        # expected_state = self.get_expected_state(plug_name)
        # current_state = self.get_current_state(plug_name)

        # check to see if there are events for the device
        if not self.has_events(plug_name):
            # no events for device.  add first event
            current_state = self.get_default_state(plug_name)         
            event,event_at = self.next_event(plug_name,current_state,time_mark)
            self.put(plug_name,current_state,event,event_at)
            if current_state == 1:
                return self.on(plug_name)
            else:
                return self.off(plug_name)
            
        # device has events, pop event
        expected_state = self.get_expected_state(plug_name)
        plug_events = self.pop(plug_name,time_mark)
        if plug_events is not None and len(plug_events)>0:
            retrieved_event = plug_events[0] # events are sorted .  only [0] needs to be processed
            if self.logger is not None:
                self.logger.info(f"retrieved_event: {retrieved_event}")
            device_key = retrieved_event[0]
            event = json.loads(retrieved_event[1])
            expected_state = event['set']
            event_at = retrieved_event[2]
            queue_event,queue_event_at = self.next_event(plug_name,expected_state,event_at)
            self.put(plug_name,expected_state,queue_event,queue_event_at)
        current_state = self.get_current_state(plug_name)
        if current_state != expected_state:
            if expected_state == 1:
                if self.logger is not None:
                    self.logger.info(f"{plug_name} is {expected_state}")
                return self.on(plug_name)
            else:
                if self.logger is not None:
                    self.logger.info(f"{plug_name} is {expected_state}")
                return self.off(plug_name)               
        return {plug_name:current_state}

    def get_events_df(self):    
        with self.get_conn() as conn:
            # Execute an SQL query and store the result in a DataFrame
            return pd.read_sql_query("SELECT * FROM events", conn)
        return None

# def run(cmd,plug=None):
#     logger = logging.getLogger(__name__)
#     logger.setLevel(logging.INFO)
#     formatter = logging.Formatter('%(levelname)s - %(asctime)s - %(message)s')
#     console_handler = logging.StreamHandler()
#     console_handler.setLevel(logging.INFO)
#     console_handler.setFormatter(formatter)
#     logger.addHandler(console_handler)    

#     if 'KASA_OUTLET_CONFIG' in os.environ:
#         strip = SmartStrip(logger=logger,config_path=Path(os.environ['KASA_OUTLET_CONFIG']))
#     else:
#         strip = SmartStrip(logger=logger)
#     if cmd == 'status':
#         result = strip.status()
#         logger.info(json.dumps(result))
#     elif cmd == 'on':
#         if plug is None:
#             raise Exception(f"plug is required")
#         result =  strip.on(plug)
#         if result:
#             logger.info(result)
#     elif cmd == 'off':
#         if plug is None:
#             raise Exception(f"plug is required")
#         result =  strip.off(plug)
#         if result:
#             logger.info(result)

# if __name__=='__main__':
#     fire.Fire(run)