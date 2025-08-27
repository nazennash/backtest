#!/bin/bash

# sudo apt update
# sudo apt install python3-full -y

python3 -m venv /home/ubuntu/env

source /home/ubuntu/env/bin/activate

/home/ubuntu/env/bin/pip install --upgrade pip

/home/ubuntu/env/bin/pip install -r /home/ubuntu/django-app-v4/requirements.txt

/home/ubuntu/env/bin/pip install gunicorn
