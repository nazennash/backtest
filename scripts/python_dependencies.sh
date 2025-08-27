#!/bin/bash

# Install venv support if missing
sudo apt install python3-venv -y

# If the venv doesn't exist, create it
if [ ! -d "/home/ubuntu/env" ]; then
    python3 -m venv /home/ubuntu/env
fi

# Activate the venv
source /home/ubuntu/env/bin/activate

# Upgrade pip inside venv
pip install --upgrade pip

# Install project dependencies
pip install -r /home/ubuntu/django-app-v4/requirements.txt
