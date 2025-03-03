# CAMPSMITH SmartHome setup
The ansible tools in this folder automate the set up of the CAMPSMITH SmartHome server.

## Overview

CAMPSmith SmartHome encompasses the following

* python
* FASTAPI
* Streamlit

## Run Setup Playbook
```
ansible-playbook -i hosts.yaml smarthome-setup.yaml
```

## Run Deploy Playbook
```
ansible-playbook -i hosts.yaml smarthome-deploy.yaml
```

