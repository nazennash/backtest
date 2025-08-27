#!/bin/bash


sudo apt update
sudo apt install python3-venv python3-full -y
python3 -m venv /home/ubuntu/env
source /home/ubuntu/env/bin/activate
pip install --upgrade pip
pip install -r /home/ubuntu/django-app-v4/requirements.txt
