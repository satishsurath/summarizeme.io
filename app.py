import os, sys

sys.path.append(os.getcwd())




from flask import Flask
application = Flask(__name__)
sys.path.append('app')
from app import app as application

