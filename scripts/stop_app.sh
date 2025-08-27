#!/bin/bash
sudo systemctl stop gunicorn.socket
sudo systemctl disable gunicorn.socket
sudo systemctl stop nginx