#!/bin/bash
set -e

cd /app

echo "-----> Running post-deploy tasks"

echo "-----> Ensuring FAISS directory exists"
mkdir -p /storage/faiss

echo "-----> Discovering and indexing Vision years"
python manage.py index_all_visions

echo "-----> Post-deploy tasks complete"
