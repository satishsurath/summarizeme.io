import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    # Configure secret key
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    # Configure database
    #SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.sqlite3')
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configure OAuth for LinkedIn
    LINKEDIN_OAUTH_CLIENT_ID = os.environ.get("LINKEDIN_OAUTH_CLIENT_ID")
    LINKEDIN_OAUTH_CLIENT_SECRET = os.environ.get("LINKEDIN_OAUTH_CLIENT_SECRET")

    # Configure Logging
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT')
    #  email server 
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    ADMINS = ['me@summarizeme.io']
    # Configure file upload
    UPLOAD_FOLDER = 'app/static/uploads'
    UPLOAD_CONTENT = 'app/text2summary/uploads'
    WRITE_JSON_LOCALLY = True
    WRITE_TEXT_LOCALLY = True
    # Configure session options
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = './sessions'
    SESSION_FILE_THRESHOLD = 100
    SESSION_PERMANENT = False
    
    # Configure Environment
    SUMMARIZEME_ENV = os.environ.get('SUMMARIZEME_ENV') or 'development'
        #Toggle to Show / Hide the Banner
    FLAG_SUMMARIZEME_ENV = os.environ.get('FLAG_SUMMARIZEME_ENV') or True

    # Configure Matomo Analytics
    MATOMO_URL = os.environ.get('MATOMO_URL') or 'https://analytics.summarizeme.io/'
    MATOMO_SITE_ID = os.environ.get('MATOMO_SITE_ID') or 1
    
    # Configure YOURLS
    YOURLS_SECRET_TOKEN = os.environ.get('YOURLS_SECRET_TOKEN')