# SmartOutletController

This project implements a solution to control a smart outlet.  Design objectives are that
* The solution should be self healing, meaning that it should recover automatically if there is a power outage
* The solution should not be cloud based, it should operate even when internet connection is not available
* The solution should manage state such that if power is lost, when power is restored, the solution has the correct state of the system
* The solution should automatically recover to the correct state within 5 minutes of recovery.  This means that if a power outage occured while an action was scheduled, the system should recover to the intended state within 5 minutes of power recovery

---

## Design

### Infrastructure

The solution will be implemented using Raspberry Pi.  Raspberry Pi's address the following design objectives:
* Self-Healing: Raspberry Pi's can be configured to boot up automatically when power is available.  They can also be configured to run scripts and programs automatically and at start up, enabling automated recovery
* State management: Raspberry Pi's can be equipped with non-volatile storage enabling them to manage state through power outage
* Local Infrastructure: Raspberry Pi's can interact with devices on the local network and are not reliant on any cloud services.
* Automated recovery: With the above features, scripts and programs can be implemented on the Rapsberry Pi to ensure that the desired intended state is recovered within 5 minutes of startup

### Software Control System

The software control system will be implemented in Python because Python is ubiquitous in the Raspberry Pi ecosystem and has libraries available to control smart outlets.  The main design objectives of the software control system are:
* The software control system should manage state
* The software control system should be able to detect the intended state and the current state and if the intended state is not the same as teh current state, it should be able to change the current state to the intended state within 5 minutes of start up
* The software control system should be a simple design so that it can be robust

### Software Control System Functional Requirements
* Configurable via yaml file
* Able to define a schedule for when an outlet is on.  The main scenario is to control when a pump is running.
    * A default state for an outlet can be defined, either on or off.
    * Only daily schedule is supported.  Configuration only defines time (24 hour clock) to start and how long to run (minutes)
    * Schedule is repeated every day.  Days are not supported, meaning configuration of different schedules by day is not supported.
    * The outlet will be enabled at the specified time and will be disabled after the specified duration has elapsed.
    * If a configuration entry's start time overlaps a previously scheduled entry's duration, it will be ignored and a warning of the conflict will be logged.
    * if a schedule defines the same state as the default state, it is ignored and a warning of the conflict will be logged.


### Software Control System Design
* Designed to be triggered and run via crontab.  crontab is reliable and built into Raspberry Pi's.  This will enable self healing and recovery.
* Logging used to manage log messages and log files
* Yaml used to manage configuration
* python-kasa: a python library to control Kasa devices see ![kasa-python library](https://github.com/python-kasa/python-kasa)

---

### Setup
See `/setup/README.md`

---

## Example Configurations
```yaml
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
```

---

### run api
```
KASA_OUTLET_CONFIG=conf/campsmith-devices-local.yml uvicorn smarthome_api:api --host 0.0.0.0 --port 8000 --reload
```

### healthcheck
```
curl http://127.0.0.1:8000/healthcheck
```

### get plug state
```
curl http://127.0.0.1:8000/plug/TowerGarden
```

### set plug
```
curl --header "Content-Type: application/json" \
  --request POST \
  --data '{"state":1}' \
  http://127.0.0.1:8000/plug/TowerGarden
```

### patch plug
```
curl -X PATCH http://127.0.0.1:8000/plug/TowerGarden
```

## run SmartHome console
```
KASA_OUTLET_CONFIG=conf/campsmith-devices-local.yml streamlit run smarthome_console.py
```

---

## Example CRONTAB configuration
```
* * * * * curl -X PATCH http://127.0.0.1:8000/TowerGarden
```
---

## Contributors

*  **Martin Smith** <span>&nbsp;&nbsp;</span> |
<span>&nbsp;&nbsp;</span> *email:* msmith92663@gmail.com <span>&nbsp;&nbsp;</span>|
<span>&nbsp;&nbsp;</span> [<img src="images/LI-In-Bug.png" alt="in" width="20"/>](https://www.linkedin.com/in/smithmartinp/)


---

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

