
import os
import json
import hashlib
from app import app, db, login_manager
from app.models import Entry_Post, oAuthUser, Entry_Posts_History
from flask import session
# -------------------- File Operations --------------------


#given the filename and json contents, write to file and save it to os.path.join(app.config['UPLOAD_FOLDER'], filename)
def write_json_to_file(filename, json_contents):
  if (app.config['WRITE_JSON_LOCALLY'] == 'False'):
    return True
  else:
  #wrap in try catch
    try:
      with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'w') as f:
        json.dump(json_contents, f)
      return True
    except:
      return False
    
#given the filename and text2summarize contents, write to file and save it to os.path.join(app.config['UPLOAD_CONTENT'], filename)
def write_content_to_file(filename, content):
  if (app.config['WRITE_TEXT_LOCALLY'] == 'False'):
    return True
  else:
    try:
      with open(os.path.join(app.config['UPLOAD_CONTENT'], filename), 'w') as f:
        f.write(content)
      return True
    except:
      return False


#Given the filename, read the file and return the json, wrap it in try catch
def read_from_file_json(filename):
  if (app.config['WRITE_JSON_LOCALLY'] == 'False'):
    return False
  else:
    try:
      with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'r') as f:
        json_contents = json.load(f)
      return json_contents
    except:
      return False
      
#Given the filename, read the file and return the contents, wrap it in try catch
def read_from_file_content(filename):
  if (app.config['WRITE_TEXT_LOCALLY'] == 'False'):
    return False
  else:
    try:
      with open(os.path.join(app.config['UPLOAD_CONTENT'], filename), 'r') as f:
        content = f.read()
      return content
    except:
      return False

#check if folder os.path.join(app.config['UPLOAD_FOLDER'] exists, if not create it
def check_folder_exists(folder_path):
  try:
    if not os.path.exists(folder_path):
      os.makedirs(folder_path)
    return True
  except:
    return False


# -------------------- Database Operations --------------------


def get_entry_by_hash(text2summarize_hash):
    try:
        return Entry_Post.query.filter_by(text2summarize_hash=text2summarize_hash).first()
    except Exception as e:
        print(f"Error in get_entry_by_hash: {e}")
        return None

def get_user_by_email(email):
    try:
        return oAuthUser.query.filter_by(email=email).first()
    except Exception as e:
        print(f"Error in get_user_by_email: {e}")
        return None

def get_history_entry(entry_id, user_id):
    try:
        return Entry_Posts_History.query.filter_by(entry_post_id=entry_id, oAuthUser_id=user_id).first()
    except Exception as e:
        print(f"Error in get_history_entry: {e}")
        return None

def add_history_entry(entry_id, user_id):
    try:
        new_history_entry = Entry_Posts_History(entry_post_id=entry_id, oAuthUser_id=user_id)
        db.session.add(new_history_entry)
        db.session.commit()
    except Exception as e:
        print(f"Error in add_history_entry: {e}")

# function to check if the hash of text2summarize is already in the database then retun
def check_if_hash_exists(text2summarize_hash):
    entry = get_entry_by_hash(text2summarize_hash)
    if not entry:
        return False

    if not session.get('name', False):
        return True

    user = get_user_by_email(session.get('email'))
    if not user:
        return True

    history_entry = get_history_entry(entry.id, user.id)
    if not history_entry:
        add_history_entry(entry.id, user.id)

    return True


# 
# def check_if_hash_exists(text2summarize_hash):
#   try:
#     entry = Entry_Post.query.filter_by(text2summarize_hash=text2summarize_hash).first()
#     if entry:
#       return True
#     else:
#       return False
#   except:
#     return False

# function to return the Summary if the hash of text2summarize is already in the database
def get_summary_from_hash(text2summarize_hash):
  entry = Entry_Post.query.filter_by(text2summarize_hash=text2summarize_hash).first()
  if entry:
    if entry.openAIsummary == None:
      return False
    else:
      return entry.openAIsummary
  else:
    return False

# function to return the Summary if the hash of text2summarize is already in the database
def get_key_insights_from_hash(text2summarize_hash):
  entry = Entry_Post.query.filter_by(text2summarize_hash=text2summarize_hash).first()
  if entry:
    if entry.openAIkeyInsights == None:
      return False
    else:
      return entry.openAIkeyInsights
  else:
    return False


# function to return the Page Title if the hash of text2summarize is already in the database
def get_title_from_hash(text2summarize_hash):
  entry = Entry_Post.query.filter_by(text2summarize_hash=text2summarize_hash).first()
  if entry:
    if entry.openAItitle == None:
      return False
    else:
      return entry.openAItitle
  else:
    return False


# Function to write to the database
def write_entry_to_db(posttype, url, text2summarizedb, openAIsummarydb, openAItitledb):
    try:
        # Check for an existing entry with the same openAIkeyInsights
        existing_entry = Entry_Post.query.filter_by(openAIsummary=openAIsummarydb).first()

        if existing_entry and not session.get('content_written', False):
            # Update the openAIkeyInsights for the existing entry
            existing_entry.openAIkeyInsights = openAIsummarydb
            db.session.commit()
        elif not session.get('content_written', False):
            text2summarize_hash = hashlib.sha256(text2summarizedb.encode('utf-8')).hexdigest()
            entry = Entry_Post(posttype=posttype, url=url, text2summarize=text2summarizedb, openAIsummary=openAIsummarydb, text2summarize_hash=text2summarize_hash, openAItitle=openAItitledb)
            db.session.add(entry)
            db.session.commit()

            # Check if user is logged in
            if session.get('linkedin_id', False):
                user_linkedin = session['linkedin_id']
                user = oAuthUser.query.filter_by(linkedin_id=user_linkedin).first()
                if user:
                    # User exists, write to entry_history table
                    entry_history = Entry_Posts_History(oAuthUser_id=user.id, entry_post_id=entry.id)
                    db.session.add(entry_history)
                    db.session.commit()

            session['content_written'] = True
            return True
    except Exception as e:  # Catch the exception
        db.session.rollback()  # Rollback the session
        print("Error occurred. Could not write to database.")
        print(f"Error details: {e}")  # Print the details of the error
        app.logger.error("Error occurred. Could not write to database.")
        app.logger.error(f"Error details: {e}")  # Log the details of the error
        return False
    finally:
        db.session.close()

# Function to write to the database
def write_insights_to_db(posttype, url, text2summarizedb, openAIkeyInsightsdb, openAItitledb):
    try:
        text2summarize_hash = hashlib.sha256(text2summarizedb.encode('utf-8')).hexdigest()
        existing_entry = Entry_Post.query.filter_by(text2summarize_hash=text2summarize_hash).first()

        if existing_entry and not session.get('content_written', False):
            # Update the openAIkeyInsights for the existing entry
            existing_entry.openAIkeyInsights = openAIkeyInsightsdb
            db.session.commit()
        elif not session.get('content_written', False):
            entry = Entry_Post(posttype=posttype, url=url, text2summarize=text2summarizedb, openAIkeyInsights=openAIkeyInsightsdb, text2summarize_hash=text2summarize_hash, openAItitle=openAItitledb)
            db.session.add(entry)
            db.session.commit()

            # Check if user is logged in
            if session.get('linkedin_id', False):
                user_linkedin = session['linkedin_id']
                user = oAuthUser.query.filter_by(linkedin_id=user_linkedin).first()
                if user:
                    # User exists, write to entry_history table
                    entry_history = Entry_Posts_History(oAuthUser_id=user.id, entry_post_id=entry.id)
                    db.session.add(entry_history)
                    db.session.commit()

            session['content_written'] = True
            return True
    except Exception as e:  # Catch the exception
        db.session.rollback()  # Rollback the session
        print("Error occurred. Could not write to database.")
        print(f"Error details: {e}")  # Print the details of the error
        app.logger.error("Error occurred. Could not write to database.")
        app.logger.error(f"Error details: {e}")  # Log the details of the error
        return False
    finally:
        db.session.close()

# delete_entry_from_db(entry_id)
def delete_entry_from_db(entry_id):
  try:
    entry = Entry_Post.query.filter_by(id=entry_id).first()
    if entry:
      db.session.delete(entry)
      db.session.commit()
      db.session.close()
      entry_history = Entry_Posts_History.query.filter_by(entry_id=entry_id).first()
      if entry_history:
        db.session.delete(entry_history)
        db.session.commit()
        db.session.close()
      return True
    else:
      return False
  except:
    return False
  
#given the text2summarize_hash, return the entire entry
def get_entry_from_hash(text2summarize_hash):
  try:
    entry = Entry_Post.query.filter_by(text2summarize_hash=text2summarize_hash).first()
    if entry:
      return entry
    else:
      return False
  except:
    return False
    

#Given the linkedin.get("me").json, sanitize, verify the JSON file and then save the user info to the database to oAuth table
#check if user exists in  database to oAuth table, if not create a new user and add to database
def write_user_to_db():
  try:
    user_linkedin = session['linkedin_id']
    user = oAuthUser.query.filter_by(linkedin_id=user_linkedin).first()
    if user:
      #User exists, update the session variables
      Print("Welcome back")
      return True
    else:
      #User does not exist, create a new user and add to database
      user = oAuthUser(name=session['name'], email=session['email'], linkedin_id=session['linkedin_id'])
      db.session.add(user)
      db.session.commit()
      db.session.close()
      return True
  except Exception as e:  # Catch the exception:
    print("Error occurred. Could not write to database.")
    print(f"Error details: {e}")  # Print the details of the error
    app.logger.error("Error occurred. Could not write to database.")
    app.logger.error(f"Error details: {e}")  # Log the details of the error
    return False

#check if user exists in  database to oAuth table, if not create a new user and add to database
def check_if_user_exists(user_email):   
  try:
    user = oAuthUser.query.filter_by(email=user_email).first()
    if user:
      return True
    else:
      return False
  except:
    return False
