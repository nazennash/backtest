#!/bin/bash
python3 -m pip install --upgrade pip
virtualenv /home/ubuntu/env
pip3 install -r /home/ubuntu/django-app-v4/requirements.txt
pip3 install gunicorn
