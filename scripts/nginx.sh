#!/bin/bash
sudo systemctl daemon-reload
sudo rm -f /etc/nginx/sites-enabled/default

sudo cp /home/ubuntu/django-app-v4/nginx/nginx.conf /etc/nginx/sites-available/django-app-v4
sudo ln -s /etc/nginx/sites-available/django-app-v4 /etc/nginx/sites-enabled/

# sudo nginx -t
sudo gpasswd -a www-data ubuntu
sudo systemctl restart nginx
