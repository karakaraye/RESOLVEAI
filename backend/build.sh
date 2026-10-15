#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt
python django_manage.py collectstatic --no-input
python django_manage.py migrate
