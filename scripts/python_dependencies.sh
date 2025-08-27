#!/bin/bash

# Install venv support if missing
sudo apt install python3-venv -y

# Create a venv
python3 -m venv ~/myenv

# Activate it
source ~/myenv/bin/activate

# Upgrade pip inside venv
pip install --upgrade pip


pip install -r /home/ubuntu/django-app-v4/requirements.txt