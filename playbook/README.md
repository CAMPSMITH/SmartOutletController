# CAMPSMITH SmartHome setup
The ansible tools in this folder automate the set up of the CAMPSMITH SmartHome server.

## Overview

CAMPSmith SmartHome encompasses the following

* python
* FASTAPI
* Streamlit
* kasa

## Run Setup Playbook
* use the playboon venv
* from root repo
```
ansible-playbook -i conf/hosts.yaml playbook/smarthome-setup.yaml
```

## Run Deploy Playbook
* use the playboon venv
* from root repo
```
ansible-playbook -i conf/hosts.yaml playbook/smarthome-deploy.yaml
```

