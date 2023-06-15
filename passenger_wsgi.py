import os, sys

INTERP = ""

#If we are not in Productionl
# Or Development Mode
# Or Staging Mode 
# - then it loads the Python Path from the .env file

if os.environ['HOME'] == '/home/dh_hjy3j9':
        INTERP = os.path.join(os.environ['HOME'], 'summarizeme.io', 'venv', 'bin', 'python3')
        print("1:"+INTERP)
elif os.environ['HOME'] == '/home/dh_wagsu9':
        INTERP = os.path.join(os.environ['HOME'], 'dev.summarizeme.io', 'venv', 'bin', 'python3')
        print("2:"+INTERP)
elif os.environ['HOME'] == '/home/dh_kzhw5x':
        INTERP = os.path.join(os.environ['HOME'], 'beta.summarizeme.io', 'venv', 'bin', 'python3')
        print("3:"+INTERP)
else:   
        from dotenv import load_dotenv
        load_dotenv()
        if (os.environ.get('INTERP')):
                INTERP = os.environ.get('INTERP')
                print("4:"+INTERP)




if sys.executable != INTERP:
        print("INTERP: ",INTERP)
        print("sys.argv: ",sys.argv)
        print("os.environ['HOME']:", os.environ['HOME'])
        os.execl(INTERP, INTERP, *sys.argv)
sys.path.append(os.getcwd())



from flask import Flask
application = Flask(__name__)
sys.path.append('app')
from app import app as application

