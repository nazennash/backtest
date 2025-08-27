#!/bin/bash
sudo cp /home/ubuntu/django-app-v4/gunicorn/gunicorn.socket /etc/systemd/system/gunicorn.socket
sudo cp /home/ubuntu/django-app-v4/gunicorn/gunicorn.service /etc/systemd/system/gunicorn.service

sudo systemctl start gunicorn.socket
sudo systemctl enable gunicorn.socket
sudo systemctl status gunicorn.socket
sudo systemctl restart gunicorn
