import os
#import openai
import json
import trafilatura
import tiktoken
import nltk
import time
import random
import hashlib
import promptlayer
import rollbar
from nltk.tokenize import sent_tokenize
from app import app, db, login_manager, linkedin_bp
from app.forms import SummarizeFromText, SummarizeFromURL, openAI_debug_form, UploadPDFForm, SummarizeFromYouTube
from app.models import Entry_Post, oAuthUser, Entry_Posts_History
from app.db_file_operations import write_json_to_file, write_content_to_file, read_from_file_json, read_from_file_content, check_folder_exists
from app.db_file_operations import check_if_hash_exists, get_summary_from_hash, get_key_insights_from_hash, get_title_from_hash, write_entry_to_db, write_insights_to_db, delete_entry_from_db, get_entry_from_hash, write_user_to_db, check_if_user_exists, get_entry_by_hash, get_user_by_email, get_history_entry, add_history_entry 
from app.utility_functions import num_tokens_from_string, avg_sentence_length, nl2br, preferred_locale_value, get_short_url, get_existing_short_url, extract_video_id 
from flask import render_template, flash, redirect, url_for, request, session
from trafilatura import extract
from trafilatura.settings import use_config
from flask_sqlalchemy import SQLAlchemy, Pagination
from sqlalchemy import Table, Column, Float, Integer, String, MetaData, ForeignKey
from sqlalchemy.orm import joinedload
from flask_migrate import Migrate
from flask_login import login_required, current_user, UserMixin
from flask_login import login_user, logout_user, login_required
from flask_wtf.csrf import generate_csrf
from werkzeug.utils import secure_filename
from pdfminer.high_level import extract_text
from io import BytesIO
from flask_dance.contrib.linkedin import linkedin
from collections.abc import Sequence
from youtube_transcript_api import YouTubeTranscriptApi


#--------------------- Rollbar for Logging ---------------------

rollbar.init(
  access_token='a816379fa9e84950a560a7e10d7f2982',
  environment=app.config['ROLLBAR_ENV'],
  code_version='1.0'
)
rollbar.report_message('Rollbar is configured correctly', 'info')


# -------------------- Utility functions --------------------


#Used to inject the enumerate function into the templates
@app.context_processor
def inject_enumerate():
    return dict(enumerate=enumerate)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf())

class CustomPagination(Sequence):
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.total // self.per_page + 1):
            if num <= left_edge or (num > self.page - left_current - 1 and num < self.page + right_current) or num > self.total // self.per_page - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num    

# -------------------- Basic Admin Authentication --------------------

#Define the Username and Password to access the Logs
summarizeMeUser = os.getenv("summarizeMeUser") or "user1"
summarizeMePassword = os.getenv("summarizeMePassword") or "pass1"
users = {summarizeMeUser:{'pw':summarizeMePassword}}
 
class User(UserMixin):
  pass

#Define the Username and Password to access the Logs and Debugging  
@login_manager.user_loader
def user_loader(username):
  if username not in users:
    return

  user = User()
  user.id = username
  return user

@login_manager.request_loader
def request_loader(request):
  username = request.form.get('username')
  if username not in users:
    return
  user = User()
  user.id = username
  user.is_authenticated = request.form['pw'] == users[username]['pw']
  return user


# -------------------- Flask app configurations --------------------
app.jinja_env.filters['nl2br'] = nl2br

promptlayer.api_key = os.getenv("PROMPTLAYER_API_KEY")
openai = promptlayer.openai
openai.api_key = os.getenv("OPENAI_API_KEY")


nltk.download('punkt')

# -------------------- Global variables --------------------

openAI_summary = "" 
openAI_summary_JSON = ""
text2summarize = ""
url = ""
global_is_trimmed = False
global_form_prompt = ""
global_number_of_chunks = 0
content_written = False
global_pdf_filename = ""


# -------------------- Routes --------------------


# write a function to get emailaddress, name from linkedin and store it in the session
@app.before_request
def before_request():
  if not session.get('name', False):
    if linkedin.authorized:
      resp = linkedin.get("me")
      assert resp.ok
      data = resp.json()
      resp_email = linkedin.get("emailAddress?q=members&projection=(elements*(handle~))")
      assert resp_email.ok
      data_email = resp_email.json()
      email = data_email['elements'][0]['handle~']['emailAddress']         
      #print(data)
      name = "{first} {last}".format(first=data['localizedFirstName'], last=data['localizedLastName'])
      #email = data['emailAddress']
      session['name'] = name
      session['email'] = email
      session['linkedin_id'] = data['id']
      if check_if_user_exists(session['email']) == False:
        write_user_to_db()
      else:
        #print("User already exists in the database")
        pass
  else:
      pass



# -------------------- Summarize Routes --------------------
@app.route('/')
@app.route('/index')
def index():
  if session.get('name', False):
    return render_template('index.html', name=session['name'])  
  return render_template('index.html')

@app.route('/privacy-policy')
def privacypolicy():
    return render_template('privacy.html')

@app.route('/summarizeText', methods=['GET', 'POST'])
def summarizeText():
    form = SummarizeFromText()
    if form.validate_on_submit():
        text2summarize = form.summarize.data
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
        #Check if the text has already been summarized
        if check_if_hash_exists(text2summarize_hash):
            #Get the summary from the database
            openAI_summary = get_summary_from_hash(text2summarize_hash)
            summary_page_title = get_title_from_hash(text2summarize_hash)
            #Support for Legacy Database entries without title
            if not summary_page_title:
               summary_page_title = openAI_page_title(openAI_summary)
            openAI_summary_JSON = read_from_file_json(text2summarize_hash + ".json")
            session['openAI_summary_JSON'] = openAI_summary_JSON
            session['is_trimmed'] = False
            session['form_prompt'] = text2summarize
            session['number_of_chunks'] = "Retrieved from Database"
        else:
            #Summarize the text using OpenAI API
            openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_summarize_chunk(text2summarize)
            session['openAI_summary_JSON'] = openAI_summary_JSON
            openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
            summary_page_title = openAI_page_title(openAI_summary)
        # Now, we have all the data, Save the summary to the Session variables
        session['openAI_summary'] = openAI_summary
        session['openAI_summary_JSON'] = openAI_summary_JSON
        session['text2summarize'] = text2summarize
        session['url'] = ""
        session['content_written'] = False
        session['content_display_Text'] = False
        session['summary_page_title'] = summary_page_title              
        # Reload the page so we can process the template with all the Session Variables
        return redirect(url_for('summarizeText'))
    # Check if Session variables are set
    if session.get('openAI_summary') and not session.get('content_display_Text', False):
        text2summarize = session.get('text2summarize')
        #Recheck if the text2summarize is not None
        if text2summarize is not None:
            text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
        else:
            #If the text2summarize is None, then we have an Error. Let the user know
            flash("Unable to extract content from the provided Text. Please try Again")
            return redirect(url_for('summarizeText'))
        #Check if the text has already been written to Database or if it exists in the database
        if not check_if_hash_exists(text2summarize_hash) and not session.get('content_written', False):
            #Write the content to the database
            write_entry_to_db(0, "0", text2summarize, session['openAI_summary'], session.get('summary_page_title', "Error: Could not Generate Title"))
            #Write the json to the file
            write_json_to_file(text2summarize_hash + ".json", session['openAI_summary_JSON'])
            if check_folder_exists(app.config['UPLOAD_CONTENT']):
                #Write the content to the file
                write_content_to_file(text2summarize_hash + ".txt", text2summarize)
            #Set the content_written to True
            session['content_written'] = True
        token_count = num_tokens_from_string(text2summarize)
        avg_tokens_per_sentence = avg_sentence_length(text2summarize)
        #Check if the openAI_summary_JSON is not None
        #summary_page_title = openAI_page_title(session.get('openAI_summary'))
        #session['summary_page_title'] = summary_page_title
        if session['openAI_summary_JSON']:
            openAI_summary_str = json.dumps(session['openAI_summary_JSON'], indent=4)
        else:
            #If the openAI_summary_JSON is None, then we don't have the JSON. Let the user know
            openAI_summary_str = "Retrieved from Database"
        if not session.get('name', False):
          #If the user is not logged in, then we don't need to show the email address
          session['content_display_Text'] = True
          return render_template(
              'summarizeText.html',
              title='Summarize Text',
              form=form,
              text2summarize=text2summarize.split('\n'),
              openAI_summary=session['openAI_summary'].split('\n'),
              token_count=token_count, avg_tokens_per_sentence=avg_tokens_per_sentence,
              openAI_json=openAI_summary_str,
              is_trimmed=session.get('is_trimmed', False),
              form_prompt_nerds=session['form_prompt'],
              number_of_chunks=session['number_of_chunks'],
              text2summarize_hash=text2summarize_hash,
              summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
          )
        else:
          #If the user is logged in, then we need to show the email address
          session['content_display_Text'] = True
          return render_template(
              'summarizeText.html',
              title='Summarize Text',
              form=form,
              text2summarize=text2summarize.split('\n'),
              openAI_summary=session['openAI_summary'].split('\n'),
              token_count=token_count, avg_tokens_per_sentence=avg_tokens_per_sentence,
              openAI_json=openAI_summary_str,
              is_trimmed=session.get('is_trimmed', False),
              form_prompt_nerds=session['form_prompt'],
              number_of_chunks=session['number_of_chunks'],
              text2summarize_hash=text2summarize_hash,
              summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
              name=session['name']
          )           
    else:
        clear_session()
        session['content_written'] = False
        if not session.get('name', False):
          return render_template('summarizeText.html', title='Summarize Text', form=form)
        else:
          return render_template('summarizeText.html', title='Summarize Text', form=form, name=session['name'])

#New funciton to summarize the youtube video transcript
@app.route('/summarizeYouTube', methods=['GET', 'POST'])
def summarizeYouTube():
    form = SummarizeFromYouTube()
    if form.validate_on_submit() and request.method == 'POST':
        video_id = extract_video_id(form.youtube_url.data)
        #print("1: video_id:" + video_id)
        if video_id is None:
            flash("Unable to extract video ID from the provided URL. Please try another URL.")
            return redirect(url_for('summarizeYouTube'))
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            transcript_text = ' '.join([item['text'] for item in transcript_list])
            #print("2: transcript_text:" + transcript_text)
        except:
            flash("Unable to download transcript from the provided YouTube video. Please try another video.")
            rollbar.report_message('Unable to download transcript from the provided YouTube video. Please try another video.', 'error')
            rollbar.report_exc_info()
            return redirect(url_for('summarizeYouTube'))

        # Perform the summarization and other necessary tasks similar to the summarizeURL function
        text2summarize_hash = hashlib.sha256(transcript_text.encode('utf-8')).hexdigest()
        #print("3: text2summarize_hash:" + text2summarize_hash)

        #check if the hash exists in the Local Database, before calling the OpenAI API
        if check_if_hash_exists(text2summarize_hash):
            openAI_summary = get_summary_from_hash(text2summarize_hash)
            summary_page_title = get_title_from_hash(text2summarize_hash)
            #Support for Legacy Database entries without title
            if not summary_page_title:
                summary_page_title = openAI_page_title(openAI_summary)
            openAI_summary_JSON = read_from_file_json(text2summarize_hash + ".json")
            session['openAI_summary_JSON'] = openAI_summary_JSON
            session['is_trimmed'] = False
            session['form_prompt'] = transcript_text
            session['number_of_chunks'] = "Retrieved from Database"
        else:
          #print("Calling OpenAI API")
          openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_summarize_chunk(transcript_text)
          app.logger.info("openAI_summary_JSON:" + str(openAI_summary_JSON))
          #print("openAI_summary_JSON:" + str(openAI_summary_JSON))
          session['openAI_summary_JSON'] = openAI_summary_JSON
          openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
          #print("openAI_summary:" + openAI_summary)
          summary_page_title = openAI_page_title(openAI_summary)

        session['openAI_summary_YT'] = openAI_summary
        session['openAI_summary_YT_JSON'] = openAI_summary_JSON
        session['text2summarize_YT'] = transcript_text
        session['youtube_url'] = form.youtube_url.data
        session['content_written_YT'] = False
        session['content_display_YT'] = False
        session['summary_page_title'] = summary_page_title
        #print("4: summary_page_title:" + summary_page_title)
        #print("5: openAI_summary:" + openAI_summary)
        #print("6: openAI_summary_JSON:" + str(openAI_summary_JSON))
        #print("7: session['is_trimmed']:" + str(session['is_trimmed']))
        #print("8: session['form_prompt']:" + session['form_prompt'])
        #print("9: session['number_of_chunks']:" + session['number_of_chunks'])

        return redirect(url_for('summarizeYouTube'))
    # Check if Session variables are set and display the content
    if session.get('openAI_summary_YT') and not session.get('content_display_YT', False):
        text2summarize = session.get('text2summarize_YT')
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
        
        #Check if the text has already been written to Database or if it exists in the database
        if not check_if_hash_exists(text2summarize_hash) and not session.get('content_written_YT', False):
            write_entry_to_db(3, session['youtube_url'], text2summarize, session['openAI_summary_YT'], session.get('summary_page_title', "Error: Could not Generate Title"))
            write_json_to_file(text2summarize_hash + ".json", session['openAI_summary_YT_JSON'])

            if check_folder_exists(app.config['UPLOAD_CONTENT']):
                write_content_to_file(text2summarize_hash + ".txt", text2summarize)

            session['content_written_YT'] = True

        token_count = num_tokens_from_string(text2summarize)
        avg_tokens_per_sentence = avg_sentence_length(text2summarize)

        summary = session['openAI_summary_YT']
        summary_page_title = session['summary_page_title']
        session['content_display_YT'] = True
        if session['openAI_summary_YT_JSON']:
           openAI_summary_str= json.dumps(session['openAI_summary_YT_JSON'], indent=4, sort_keys=True)
        else:
           openAI_summary_str = "Retrieved from Database"

        if not session.get('name', False):
          return render_template(
            'summarizeYoutube.html', 
            form=form, 
            text2summarize=session['text2summarize_YT'].split("\n"), 
            openAI_summary=summary.split('\n'),
            openAI_json=openAI_summary_str,
            summary_page_title=summary_page_title, 
            token_count=token_count, 
            avg_tokens_per_sentence=avg_tokens_per_sentence,
            is_trimmed=session.get('is_trimmed', False),
            form_prompt_nerds=session.get('form_prompt', False),
            number_of_chunks=session.get('number_of_chunks', False),
            text2summarize_hash=text2summarize_hash
          )
        else:
          return render_template(
            'summarizeYoutube.html', 
            form=form, 
            text2summarize=session['text2summarize_YT'].split("\n"), 
            openAI_summary=summary.split('\n'),
            openAI_json=openAI_summary_str,
            summary_page_title=summary_page_title, 
            token_count=token_count, 
            avg_tokens_per_sentence=avg_tokens_per_sentence,
            is_trimmed=session.get('is_trimmed', False),
            form_prompt_nerds=session.get('form_prompt', False),
            number_of_chunks=session.get('number_of_chunks', False),
            text2summarize_hash=text2summarize_hash,
            name=session['name']
          )

    if not session.get('name', False):
      return render_template('summarizeYoutube.html', form=form)
    else:
      return render_template('summarizeYoutube.html', form=form, name=session['name'])

@app.route('/summarizeURL', methods=['GET', 'POST'])
def summarizeURL():
    form = SummarizeFromURL()
    if form.validate_on_submit() and request.method == 'POST':
      newconfig = use_config()
      newconfig.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
      downloaded = trafilatura.fetch_url(form.summarize.data)
      if downloaded is None:
        
        flash("Unable to download content from the provided URL. Please try another URL.")
        return redirect(url_for('summarizeURL'))
      
      session['url'] = form.summarize.data
      
      text2summarize = extract(downloaded, config=newconfig)
      
      if text2summarize is not None:
        
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
      else:
        
        flash("Unable to extract content from the provided URL. Please try another URL.")
        return redirect(url_for('summarizeURL'))
      #check if the hash exists in the Local Database, before calling the OpenAI API
      if check_if_hash_exists(text2summarize_hash):
        
        #Get the summary from the database
        openAI_summary = get_summary_from_hash(text2summarize_hash)
        summary_page_title = get_title_from_hash(text2summarize_hash)
        #Support for Legacy Database entries without title
        if not summary_page_title:
            summary_page_title = openAI_page_title(openAI_summary)        
        openAI_summary_JSON = read_from_file_json(text2summarize_hash+".json")
        session['is_trimmed'] = False
        session['form_prompt'] = text2summarize
        session['number_of_chunks'] = "Retrieved from Database"
      else:
        
        #Summarize the URL using OpenAI API
        openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_summarize_chunk(text2summarize)
        openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
        summary_page_title = openAI_page_title(openAI_summary)
        # Now, we have all the data, Save the summary to the Session variables
        
      session['openAI_summary_URL'] = openAI_summary
      session['openAI_summary_URL_JSON'] = openAI_summary_JSON
      session['text2summarize_URL'] = text2summarize
      session['url'] = form.summarize.data
      session['content_written'] = False
      session['content_display_URL'] = False
      
      session['summary_page_title'] = summary_page_title            
        
      # Reload the page so we can process the template with all the Session Variables
      return redirect(url_for('summarizeURL'))
    
    # Check if Session variables are set
    if session.get('openAI_summary_URL') and not session.get('content_display_URL', False):
      text2summarize = session.get('text2summarize_URL')
     
      #Recheck if the text2summarize is not None
      if text2summarize is not None:
        
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
      else:
        #print("summarizeURL - 15")
        #If the text2summarize is None, then we have an Error. Let the user know
        flash("Unable to extract content from the provided URL. Please try another URL.")
        return redirect(url_for('summarizeURL'))
      
      #Check if the text has already been written to Database or if it exists in the database         
      if not check_if_hash_exists(text2summarize_hash) and not session.get('content_written', False):
        #print("summarizeURL - 16")
        #Write the content to the database
        write_entry_to_db(1, session['url'], text2summarize, session['openAI_summary_URL'],session.get('summary_page_title', "Error: Could not Generate Title"))
        #Write the json to the file
        write_json_to_file(text2summarize_hash + ".json", session['openAI_summary_URL_JSON'])
        #print("summarizeURL - 17")
        if check_folder_exists(app.config['UPLOAD_CONTENT']):
          #print("summarizeURL - 18")
          #Write the content to the file
          write_content_to_file(text2summarize_hash + ".txt", text2summarize)
        #Set the content_written to True
        session['content_written'] = True
      token_count = num_tokens_from_string(text2summarize)
      avg_tokens_per_sentence = avg_sentence_length(text2summarize)
      #check if the openAI_summary_JSON is not None
     
     
      if session['openAI_summary_URL_JSON']:
        #print("summarizeURL - 19")
        openAI_summary_str = json.dumps(session['openAI_summary_URL_JSON'], indent=4)
      else:
        #print("summarizeURL - 20")
        #If the openAI_summary_JSON is None, then we don't have the JSON. Let the user know
        openAI_summary_str = "Retrieved from Database"
      #Now that we have the summary, we can render the page
      if not session.get('name', False):
        #print("summarizeURL - 21")
        #If the user is not logged in, then we don't need to show the name
        session['content_display_URL'] = True   
        return render_template(
          'summarizeURL.html',
          title='Summarize Webpage',
          form=form,
          text2summarize=session['text2summarize_URL'].split('\n'),
          openAI_summary=session['openAI_summary_URL'].split('\n'),
          token_count=token_count,
          avg_tokens_per_sentence=avg_tokens_per_sentence,
          openAI_json=openAI_summary_str,
          is_trimmed=session.get('is_trimmed', False),
          form_prompt_nerds=session['form_prompt'],
          number_of_chunks=session['number_of_chunks'],
          text2summarize_hash=text2summarize_hash,
          summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
        )
      else:
        #print("summarizeURL - 22")
        #if the user is logged in, then we need to show the name
        session['content_display_URL'] = True  
        return render_template(
          'summarizeURL.html',
          title='Summarize Webpage',
          form=form,
          text2summarize=session['text2summarize_URL'].split('\n'),
          openAI_summary=session['openAI_summary_URL'].split('\n'),
          token_count=token_count,
          avg_tokens_per_sentence=avg_tokens_per_sentence,
          openAI_json=openAI_summary_str,
          is_trimmed=session.get('is_trimmed', False),
          form_prompt_nerds=session['form_prompt'],
          number_of_chunks=session['number_of_chunks'],
          text2summarize_hash=text2summarize_hash,
          summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
          name=session['name']
        )             
    else:
      #print("summarizeURL - 23")
      clear_session()
      session['content_written'] = False
      if not session.get('name', False):
        #print("summarizeURL - 24")
        return render_template('summarizeURL.html', title='Summarize Webpage', form=form)
      else:
        #print("summarizeURL - 25")
        return render_template('summarizeURL.html', title='Summarize Webpage', form=form, name=session['name'])

@app.route('/summarizePDF', methods=['GET', 'POST'])
def summarizePDF():
    print("summarizePDF - 1")
    form = UploadPDFForm()
    if not session.get('content_written', False):
        print("summarizePDF - 2")
        if form.validate_on_submit():
            print("summarizePDF - 3")
            # Get the uploaded PDF file
            pdf_file = form.pdf.data
            print("summarizePDF - 4")
            # Read the PDF contents
            text2summarize = extract_text(BytesIO(pdf_file.read()))
            app.logger.info("text2summarize:" + str(text2summarize))
            # Protect against empty or whitespace-only input
            if len(text2summarize) <= 0 or text2summarize.isspace():
                flash("Unable to extract content from the provided PDF. Please try another PDF.")
                clear_session()
                print("summarizePDF - 4.2 - text2summarize is None ")
                return redirect(url_for('keyInsightsPDF'))
            # # Protect against empty or whitespace-only input
            # Calculate the hash of the text2summarize                          
            text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
            print("summarizePDF - 5")
            # Save the PDF file to the uploads folder
            filename = secure_filename(text2summarize_hash + pdf_file.filename)
            session['pdf_filename'] = filename
            print("summarizePDF - 5")
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Seek to the beginning of the file before saving, then save the file
            pdf_file.seek(0)
            # Check if folder exists:
            if check_folder_exists(app.config['UPLOAD_FOLDER']):
                pdf_file.save(pdf_path)
                print("summarizePDF - 6")
            # Check if the hash exists in the Local Database, before calling the OpenAI API
            if check_if_hash_exists(text2summarize_hash):
                print("summarizePDF - 7")
                openAI_summary = get_summary_from_hash(text2summarize_hash)
                openAI_summary_JSON = read_from_file_json(text2summarize_hash + ".json")
                summary_page_title = get_title_from_hash(text2summarize_hash)
                #Support for Legacy Database entries without title
                if not summary_page_title:
                  summary_page_title = openAI_page_title(openAI_summary)                
                session['is_trimmed'] = False
                session['form_prompt'] = text2summarize
                session['number_of_chunks'] = "Retrieved from Database"
            else:
              try:
                print("summarizePDF - 8")
                openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_summarize_chunk(text2summarize)
                openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
                summary_page_title = openAI_page_title(openAI_summary)
                write_json_to_file(text2summarize_hash + ".json", openAI_summary_JSON)
                if check_folder_exists(app.config['UPLOAD_CONTENT']):
                  write_content_to_file(text2summarize_hash + ".txt", text2summarize)
              except Exception as e:
                flash("Unable to summarize the provided PDF. Please try another PDF.")
                app.logger.error(f"Unable to summarize the provided PDF. Please try another PDF. Error: {e}")
                rollbar.report_message('Unable to summarize the provided PDF. Please try another PDF.', 'error')
                clear_session()
                return redirect(url_for('keyInsightsPDF'))
            print("summarizePDF - 9")
            session['openAI_summary_PDF'] = openAI_summary
            session['openAI_summary_JSON_PDF'] = openAI_summary_JSON
            session['text2summarize_PDF'] = text2summarize
            session['summary_page_title'] = summary_page_title  
            return redirect(url_for('summarizePDF'))

        # Now that we have the summary, we can render the page
        if session.get('openAI_summary_PDF'):
            print("summarizePDF - 10")
            text2summarize = session.get('text2summarize_PDF')
            if text2summarize is not None:
              text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
            else:
                flash("Unable to extract content from the provided URL. Please try another URL.")
                return redirect(url_for('summarizePDF'))           
            # If we calculated the summary with OpenAI API, we need to write it to the database
            if not check_if_hash_exists(text2summarize_hash):
                print("summarizePDF - 11")
                write_entry_to_db(2, session['pdf_filename'], text2summarize, session['openAI_summary_PDF'],session.get('summary_page_title', "Error: Could not Generate Title"))
                #Write the json to the file
                write_json_to_file(text2summarize_hash + ".json", session['openAI_summary_JSON_PDF'])
                #print("summarizeURL - 17")
                if check_folder_exists(app.config['UPLOAD_CONTENT']):
                  #print("summarizeURL - 18")
                  #Write the content to the file
                  write_content_to_file(text2summarize_hash + ".txt", text2summarize)
                # Calculate token count and average tokens per sentence
                token_count = num_tokens_from_string(text2summarize)
                avg_tokens_per_sentence = avg_sentence_length(text2summarize)
                openAI_summary_str = json.dumps(session['openAI_summary_JSON_PDF'], indent=4)
                summary_page_title = openAI_page_title(session.get('openAI_summary_PDF'))
                session['summary_page_title'] = summary_page_title  
                if not session.get('name', False):
                  # If we are not logged in, we don't want to show the Name                
                  return render_template(
                      'summarizePDF.html',
                      title='Summarize PDF',
                      form=form,
                      text2summarize=text2summarize.split('\n'),
                      openAI_summary=session['openAI_summary_PDF'].split('\n'),
                      token_count=token_count,
                      avg_tokens_per_sentence=avg_tokens_per_sentence,
                      openAI_json=openAI_summary_str,
                      is_trimmed=session.get('is_trimmed', False),
                      form_prompt_nerds=session.get('form_prompt', False),
                      number_of_chunks=session.get('number_of_chunks', False),
                      text2summarize_hash=text2summarize_hash,
                      summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
                    )
                else:
                  # If we are logged in, we want to show the Name                  #                   
                  return render_template(
                      'summarizePDF.html',
                      title='Summarize PDF',
                      form=form,
                      text2summarize=text2summarize.split('\n'),
                      openAI_summary=session['openAI_summary_PDF'].split('\n'),
                      token_count=token_count,
                      avg_tokens_per_sentence=avg_tokens_per_sentence,
                      openAI_json=openAI_summary_str,
                      is_trimmed=session.get('is_trimmed', False),
                      form_prompt_nerds=session.get('form_prompt', False),
                      number_of_chunks=session.get('number_of_chunks', False),
                      text2summarize_hash=text2summarize_hash,
                      summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
                      name=session['name']
                    )
            else:
              print("summarizePDF - 12")
              #the summary was retrieved from the database, so we don't need to write it to DB again
              # Calculate token count and average tokens per sentence
              token_count = num_tokens_from_string(text2summarize)
              avg_tokens_per_sentence = avg_sentence_length(text2summarize)
              if not session['openAI_summary_JSON_PDF']:
                openAI_summary_str = "Retrived from Database"
              else:
                openAI_summary_str = json.dumps(session['openAI_summary_JSON_PDF'], indent=4)
              if not session.get('name', False):
                # If we are not logged in, we don't want to show the Name   
                return render_template(
                  'summarizePDF.html',
                  title='Summarize PDF',
                  form=form,
                  text2summarize=text2summarize.split('\n'),
                  openAI_summary=session['openAI_summary_PDF'].split('\n'),
                  token_count=token_count,
                  avg_tokens_per_sentence=avg_tokens_per_sentence,
                  openAI_json=openAI_summary_str,
                  is_trimmed=session.get('is_trimmed', False),
                  form_prompt_nerds=session.get('form_prompt', False),
                  number_of_chunks=session.get('number_of_chunks', False),
                  text2summarize_hash=text2summarize_hash,
                  summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
                )
              else:
                # If we are logged in, we want to show the Name
                return render_template(
                  'summarizePDF.html',
                  title='Summarize PDF',
                  form=form,
                  text2summarize=text2summarize.split('\n'),
                  openAI_summary=session['openAI_summary_PDF'].split('\n'),
                  token_count=token_count,
                  avg_tokens_per_sentence=avg_tokens_per_sentence,
                  openAI_json=openAI_summary_str,
                  is_trimmed=session.get('is_trimmed', False),
                  form_prompt_nerds=session.get('form_prompt', False),
                  number_of_chunks=session.get('number_of_chunks', False),
                  text2summarize_hash=text2summarize_hash,
                  summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
                  name=session['name']
                )
        else:
            clear_session()
            print("summarizePDF - 13")
            session['content_written'] = False
            if not session.get('name', False):
              return render_template('summarizePDF.html',title='Summarize PDF', form=form)
            else:
              return render_template('summarizePDF.html',title='Summarize PDF', form=form, name=session['name'])
    else:      
      session['content_written'] = False
      clear_session()
      if not session.get('name', False):
        return render_template('summarizePDF.html',title='Summarize PDF', form=form)
      else:
        return render_template('summarizePDF.html',title='Summarize PDF', form=form, name=session['name'])
    

# -------------------- Key Instights Routes --------------------



@app.route('/keyInsightsText', methods=['GET', 'POST'])
def keyInsightsText():
    form = SummarizeFromText()
    if form.validate_on_submit():
        text2summarize = form.summarize.data
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
        #Check if the text has already been summarized
        if get_key_insights_from_hash(text2summarize_hash):
            #Get the summary from the database
            openAI_summary = get_key_insights_from_hash(text2summarize_hash) #get_summary_from_hash
            summary_page_title = get_title_from_hash(text2summarize_hash)
            #Support for Legacy Database entries without title
            if not summary_page_title:
               summary_page_title = openAI_page_title(openAI_summary)
            openAI_summary_JSON = read_from_file_json(text2summarize_hash + "_insights.json")
            session['is_trimmed'] = False
            session['form_prompt'] = text2summarize
            session['number_of_chunks'] = "Retrieved from Database"
        else:
            #Summarize the text using OpenAI API
            openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_keyInsights_chunk(text2summarize)
            openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
            summary_page_title = openAI_page_title(openAI_summary)
        # Now, we have all the data, Save the summary to the Session variables
        session['openAI_summary'] = openAI_summary
        session['openAI_summary_JSON'] = openAI_summary_JSON
        session['text2summarize'] = text2summarize
        session['url'] = ""
        session['content_written'] = False
        session['content_display_Text'] = False
        session['summary_page_title'] = summary_page_title              
        # Reload the page so we can process the template with all the Session Variables
        return redirect(url_for('keyInsightsText'))
    # Check if Session variables are set
    if session.get('openAI_summary') and not session.get('content_display_Text', False):
        text2summarize = session.get('text2summarize')
        #Recheck if the text2summarize is not None
        if text2summarize is not None:
            text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
        else:
            #If the text2summarize is None, then we have an Error. Let the user know
            flash("Unable to extract content from the provided Text. Please try Again")
            return redirect(url_for('keyInsightsText'))
        #Check if the text has already been written to Database or if it exists in the database
        if not get_key_insights_from_hash(text2summarize_hash) and not session.get('content_written', False):
            #Write the content to the database
            write_insights_to_db(4, "0", text2summarize, session['openAI_summary'], session.get('summary_page_title', "Error: Could not Generate Title"))
            #Write the json to the file
            write_json_to_file(text2summarize_hash + "_insights.json", session['openAI_summary_JSON'])
            if check_folder_exists(app.config['UPLOAD_CONTENT']):
                #Write the content to the file
                write_content_to_file(text2summarize_hash + ".txt", text2summarize)
            #Set the content_written to True
            session['content_written'] = True
        token_count = num_tokens_from_string(text2summarize)
        avg_tokens_per_sentence = avg_sentence_length(text2summarize)
        #Check if the openAI_summary_JSON is not None
        #summary_page_title = openAI_page_title(session.get('openAI_summary'))
        #session['summary_page_title'] = summary_page_title
        if session['openAI_summary_JSON']:
            openAI_summary_str = json.dumps(session['openAI_summary_JSON'], indent=4)
        else:
            #If the openAI_summary_JSON is None, then we don't have the JSON. Let the user know
            openAI_summary_str = "Retrieved from Database"
        if not session.get('name', False):
          #If the user is not logged in, then we don't need to show the email address
          session['content_display_Text'] = True
          return render_template(
              'keyInsightsText.html',
              title='keyInsights Text',
              form=form,
              text2summarize=text2summarize.split('\n'),
              openAI_summary=session['openAI_summary'].split('\n'),
              token_count=token_count, avg_tokens_per_sentence=avg_tokens_per_sentence,
              openAI_json=openAI_summary_str,
              is_trimmed=session.get('is_trimmed', False),
              form_prompt_nerds=session['form_prompt'],
              number_of_chunks=session['number_of_chunks'],
              text2summarize_hash=text2summarize_hash,
              summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
          )
        else:
          #If the user is logged in, then we need to show the email address
          session['content_display_Text'] = True
          return render_template(
              'keyInsightsText.html',
              title='keyInsights Text',
              form=form,
              text2summarize=text2summarize.split('\n'),
              openAI_summary=session['openAI_summary'].split('\n'),
              token_count=token_count, avg_tokens_per_sentence=avg_tokens_per_sentence,
              openAI_json=openAI_summary_str,
              is_trimmed=session.get('is_trimmed', False),
              form_prompt_nerds=session['form_prompt'],
              number_of_chunks=session['number_of_chunks'],
              text2summarize_hash=text2summarize_hash,
              summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
              name=session['name']
          )           
    else:
        clear_session()
        session['content_written'] = False
        if not session.get('name', False):
          return render_template('keyInsightsText.html', title='keyInsights Text', form=form)
        else:
          return render_template('keyInsightsText.html', title='keyInsights Text', form=form, name=session['name'])

#New funciton to summarize the youtube video transcript
@app.route('/keyInsightsYouTube', methods=['GET', 'POST'])
def keyInsightsYouTube():
    form = SummarizeFromYouTube()
    if form.validate_on_submit() and request.method == 'POST':
        video_id = extract_video_id(form.youtube_url.data)
        #print("1: video_id:" + video_id)
        if video_id is None:
            flash("Unable to extract video ID from the provided URL. Please try another URL.")
            return redirect(url_for('keyInsightsYouTube'))
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            transcript_text = ' '.join([item['text'] for item in transcript_list])
            #print("2: transcript_text:" + transcript_text)
        except:
            flash("Unable to download transcript from the provided YouTube video. Please try another video.")
            rollbar.report_message('Unable to download transcript from the provided YouTube video. Please try another video.', 'error')
            rollbar.report_exc_info()
            return redirect(url_for('keyInsightsYouTube'))

        # Perform the summarization and other necessary tasks similar to the summarizeURL function
        text2summarize_hash = hashlib.sha256(transcript_text.encode('utf-8')).hexdigest()
        #print("3: text2summarize_hash:" + text2summarize_hash)

        #check if the hash exists in the Local Database, before calling the OpenAI API
        if get_key_insights_from_hash(text2summarize_hash):
            openAI_summary = get_key_insights_from_hash(text2summarize_hash)
            summary_page_title = get_title_from_hash(text2summarize_hash)
            #Support for Legacy Database entries without title
            if not summary_page_title:
                summary_page_title = openAI_page_title(openAI_summary)
            openAI_summary_JSON = read_from_file_json(text2summarize_hash + "_insights.json")
            session['is_trimmed'] = False
            session['form_prompt'] = transcript_text
            session['number_of_chunks'] = "Retrieved from Database"
        else:
          #print("Calling OpenAI API")
          openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_keyInsights_chunk(transcript_text)
          #print("openAI_summary_JSON:" + str(openAI_summary_JSON))
          openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
          #print("openAI_summary:" + openAI_summary)
          summary_page_title = openAI_page_title(openAI_summary)

        session['openAI_summary_YT'] = openAI_summary
        session['openAI_summary_YT_JSON'] = openAI_summary_JSON
        session['text2summarize_YT'] = transcript_text
        session['youtube_url'] = form.youtube_url.data
        session['content_written_YT'] = False
        session['content_display_YT'] = False
        session['summary_page_title'] = summary_page_title
        #print("4: summary_page_title:" + summary_page_title)
        #print("5: openAI_summary:" + openAI_summary)
        #print("6: openAI_summary_JSON:" + str(openAI_summary_JSON))
        #print("7: session['is_trimmed']:" + str(session['is_trimmed']))
        #print("8: session['form_prompt']:" + session['form_prompt'])
        #print("9: session['number_of_chunks']:" + session['number_of_chunks'])

        return redirect(url_for('keyInsightsYouTube'))
    # Check if Session variables are set and display the content
    if session.get('openAI_summary_YT') and not session.get('content_display_YT', False):
        text2summarize = session.get('text2summarize_YT')
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
        
        #Check if the text has already been written to Database or if it exists in the database
        if not get_key_insights_from_hash(text2summarize_hash) and not session.get('content_written_YT', False):
            write_insights_to_db(7, session['youtube_url'], text2summarize, session['openAI_summary_YT'], session.get('summary_page_title', "Error: Could not Generate Title"))
            write_json_to_file(text2summarize_hash + "_insights.json", session['openAI_summary_YT_JSON'])

            if check_folder_exists(app.config['UPLOAD_CONTENT']):
                write_content_to_file(text2summarize_hash + ".txt", text2summarize)

            session['content_written_YT'] = True

        token_count = num_tokens_from_string(text2summarize)
        avg_tokens_per_sentence = avg_sentence_length(text2summarize)

        summary = session['openAI_summary_YT']
        summary_page_title = session['summary_page_title']
        session['content_display_YT'] = True
        if session['openAI_summary_YT_JSON']:
           openAI_summary_str= json.dumps(session['openAI_summary_YT_JSON'], indent=4, sort_keys=True)
        else:
           openAI_summary_str = "Retrieved from Database"

        if not session.get('name', False):
          return render_template(
            'keyInsightsYoutube.html', 
            form=form, 
            text2summarize=session['text2summarize_YT'].split("\n"), 
            openAI_summary=summary.split('\n'),
            openAI_json=openAI_summary_str,
            summary_page_title=summary_page_title, 
            token_count=token_count, 
            avg_tokens_per_sentence=avg_tokens_per_sentence,
            is_trimmed=session.get('is_trimmed', False),
            form_prompt_nerds=session.get('form_prompt', False),
            number_of_chunks=session.get('number_of_chunks', False),
            text2summarize_hash=text2summarize_hash
          )
        else:
          return render_template(
            'keyInsightsYoutube.html', 
            form=form, 
            text2summarize=session['text2summarize_YT'].split("\n"), 
            openAI_summary=summary.split('\n'),
            openAI_json=openAI_summary_str,
            summary_page_title=summary_page_title, 
            token_count=token_count, 
            avg_tokens_per_sentence=avg_tokens_per_sentence,
            is_trimmed=session.get('is_trimmed', False),
            form_prompt_nerds=session.get('form_prompt', False),
            number_of_chunks=session.get('number_of_chunks', False),
            text2summarize_hash=text2summarize_hash,
            name=session['name']
          )

    if not session.get('name', False):
      return render_template('keyInsightsYoutube.html', form=form)
    else:
      return render_template('keyInsightsYoutube.html', form=form, name=session['name'])

@app.route('/keyInsightsURL', methods=['GET', 'POST'])
def keyInsightsURL():
    form = SummarizeFromURL()
    if form.validate_on_submit() and request.method == 'POST':
      newconfig = use_config()
      newconfig.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
      downloaded = trafilatura.fetch_url(form.summarize.data)
      if downloaded is None:
        
        flash("Unable to download content from the provided URL. Please try another URL.")
        return redirect(url_for('keyInsightsURL'))
      
      session['url'] = form.summarize.data
      
      text2summarize = extract(downloaded, config=newconfig)
      
      if text2summarize is not None:
        
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
      else:
        
        flash("Unable to extract content from the provided URL. Please try another URL.")
        return redirect(url_for('keyInsightsURL'))
      #check if the hash exists in the Local Database, before calling the OpenAI API
      if get_key_insights_from_hash(text2summarize_hash):
        
        #Get the summary from the database
        openAI_summary = get_key_insights_from_hash(text2summarize_hash)
        summary_page_title = get_title_from_hash(text2summarize_hash)
        #Support for Legacy Database entries without title
        if not summary_page_title:
            summary_page_title = openAI_page_title(openAI_summary)        
        openAI_summary_JSON = read_from_file_json(text2summarize_hash+"_insights.json")
        session['is_trimmed'] = False
        session['form_prompt'] = text2summarize
        session['number_of_chunks'] = "Retrieved from Database"
      else:
        
        #Summarize the URL using OpenAI API
        openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_keyInsights_chunk(text2summarize)
        openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
        summary_page_title = openAI_page_title(openAI_summary)
        # Now, we have all the data, Save the summary to the Session variables
        
      session['openAI_summary_URL'] = openAI_summary
      session['openAI_summary_URL_JSON'] = openAI_summary_JSON
      session['text2summarize_URL'] = text2summarize
      session['url'] = form.summarize.data
      session['content_written'] = False
      session['content_display_URL'] = False
      
      session['summary_page_title'] = summary_page_title            
        
      # Reload the page so we can process the template with all the Session Variables
      return redirect(url_for('keyInsightsURL'))
    
    # Check if Session variables are set
    if session.get('openAI_summary_URL') and not session.get('content_display_URL', False):
      text2summarize = session.get('text2summarize_URL')
     
      #Recheck if the text2summarize is not None
      if text2summarize is not None:
        
        text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
      else:
        #print("summarizeURL - 15")
        #If the text2summarize is None, then we have an Error. Let the user know
        flash("Unable to extract content from the provided URL. Please try another URL.")
        return redirect(url_for('summarizeURL'))
      
      #Check if the text has already been written to Database or if it exists in the database         
      if not get_key_insights_from_hash(text2summarize_hash) and not session.get('content_written', False):
        #print("summarizeURL - 16")
        #Write the content to the database
        write_insights_to_db(5, session['url'], text2summarize, session['openAI_summary_URL'],session.get('summary_page_title', "Error: Could not Generate Title"))
        #Write the json to the file
        write_json_to_file(text2summarize_hash + "_insights.json", session['openAI_summary_URL_JSON'])
        #print("summarizeURL - 17")
        if check_folder_exists(app.config['UPLOAD_CONTENT']):
          #print("summarizeURL - 18")
          #Write the content to the file
          write_content_to_file(text2summarize_hash + ".txt", text2summarize)
        #Set the content_written to True
        session['content_written'] = True
      token_count = num_tokens_from_string(text2summarize)
      avg_tokens_per_sentence = avg_sentence_length(text2summarize)
      #check if the openAI_summary_JSON is not None
     
     
      if session['openAI_summary_URL_JSON']:
        #print("summarizeURL - 19")
        openAI_summary_str = json.dumps(session['openAI_summary_URL_JSON'], indent=4)
      else:
        #print("summarizeURL - 20")
        #If the openAI_summary_JSON is None, then we don't have the JSON. Let the user know
        openAI_summary_str = "Retrieved from Database"
      #Now that we have the summary, we can render the page
      if not session.get('name', False):
        #print("summarizeURL - 21")
        #If the user is not logged in, then we don't need to show the name
        session['content_display_URL'] = True   
        return render_template(
          'keyInsightsURL.html',
          title='keyInsights Webpage',
          form=form,
          text2summarize=session['text2summarize_URL'].split('\n'),
          openAI_summary=session['openAI_summary_URL'].split('\n'),
          token_count=token_count,
          avg_tokens_per_sentence=avg_tokens_per_sentence,
          openAI_json=openAI_summary_str,
          is_trimmed=session.get('is_trimmed', False),
          form_prompt_nerds=session['form_prompt'],
          number_of_chunks=session['number_of_chunks'],
          text2summarize_hash=text2summarize_hash,
          summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
        )
      else:
        #print("summarizeURL - 22")
        #if the user is logged in, then we need to show the name
        session['content_display_URL'] = True  
        return render_template(
          'keyInsightsURL.html',
          title='keyInsights Webpage',
          form=form,
          text2summarize=session['text2summarize_URL'].split('\n'),
          openAI_summary=session['openAI_summary_URL'].split('\n'),
          token_count=token_count,
          avg_tokens_per_sentence=avg_tokens_per_sentence,
          openAI_json=openAI_summary_str,
          is_trimmed=session.get('is_trimmed', False),
          form_prompt_nerds=session['form_prompt'],
          number_of_chunks=session['number_of_chunks'],
          text2summarize_hash=text2summarize_hash,
          summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
          name=session['name']
        )             
    else:
      #print("summarizeURL - 23")
      clear_session()
      session['content_written'] = False
      if not session.get('name', False):
        #print("summarizeURL - 24")
        return render_template('keyInsightsURL.html', title='keyInsights Webpage', form=form)
      else:
        #print("summarizeURL - 25")
        return render_template('keyInsightsURL.html', title='keyInsights Webpage', form=form, name=session['name'])

@app.route('/keyInsightsPDF', methods=['GET', 'POST'])
def keyInsightsPDF():
    print("summarizePDF - 1")
    form = UploadPDFForm()
    if not session.get('content_written', False):
        print("summarizePDF - 2")
        if form.validate_on_submit():
            print("summarizePDF - 3")
            # Get the uploaded PDF file
            pdf_file = form.pdf.data
            print("summarizePDF - 4")
            # Read the PDF contents
            text2summarize = extract_text(BytesIO(pdf_file.read()))
            print(f"summarizePDF - 4.1 text2summarize: {text2summarize} ")
            print(f"summarizePDF - 4.2 len(text2summarize): {len(text2summarize)} ")
            # Check if the PDF was empty
            if len(text2summarize) <= 0 or text2summarize.isspace():
                flash("Unable to extract content from the provided PDF. Please try another PDF.")
                clear_session()
                print("summarizePDF - 4.2 - text2summarize is None ")
                return redirect(url_for('keyInsightsPDF'))
            text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
            print("summarizePDF - 5")
            # Save the PDF file to the uploads folder
            filename = secure_filename(text2summarize_hash + pdf_file.filename)
            session['pdf_filename'] = filename
            print("summarizePDF - 5")
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Seek to the beginning of the file before saving, then save the file
            pdf_file.seek(0)
            # Check if folder exists:
            if check_folder_exists(app.config['UPLOAD_FOLDER']):
                pdf_file.save(pdf_path)
                print("summarizePDF - 6")
            # Check if the hash exists in the Local Database, before calling the OpenAI API
            if get_key_insights_from_hash(text2summarize_hash):
                print("summarizePDF - 7")
                openAI_summary = get_key_insights_from_hash(text2summarize_hash)
                openAI_summary_JSON = read_from_file_json(text2summarize_hash + "_insights.json")
                summary_page_title = get_title_from_hash(text2summarize_hash)
                #Support for Legacy Database entries without title
                if not summary_page_title:
                  summary_page_title = openAI_page_title(openAI_summary)                
                session['is_trimmed'] = False
                session['form_prompt'] = text2summarize
                session['number_of_chunks'] = "Retrieved from Database"
            else:
                print("summarizePDF - 8")
                #print text2summarize to logs
                app.logger.info(text2summarize)
                print("summarizePDF - 8.1")
                openAI_summary_JSON, session['is_trimmed'], session['form_prompt'], session['number_of_chunks'] = openAI_keyInsights_chunk(text2summarize)
                openAI_summary = openAI_summary_JSON["choices"][0]['message']['content']
                summary_page_title = openAI_page_title(openAI_summary)
                write_json_to_file(text2summarize_hash + ".json", openAI_summary_JSON)
                if check_folder_exists(app.config['UPLOAD_CONTENT']):
                  write_content_to_file(text2summarize_hash + ".txt", text2summarize)
            print("summarizePDF - 9")
            session['openAI_summary_PDF'] = openAI_summary
            session['openAI_summary_JSON_PDF'] = openAI_summary_JSON
            session['text2summarize_PDF'] = text2summarize
            session['summary_page_title'] = summary_page_title  
            return redirect(url_for('keyInsightsPDF'))

        # Now that we have the summary, we can render the page
        if session.get('openAI_summary_PDF'):
            print("summarizePDF - 10")
            text2summarize = session.get('text2summarize_PDF')
            if text2summarize is not None:
              text2summarize_hash = hashlib.sha256(text2summarize.encode('utf-8')).hexdigest()
            else:
                flash("Unable to extract content from the provided URL. Please try another URL.")
                return redirect(url_for('keyInsightsPDF'))           
            # If we calculated the summary with OpenAI API, we need to write it to the database
            if not get_key_insights_from_hash(text2summarize_hash) and not session.get('content_written', False):
                print("summarizePDF - 11")
                write_insights_to_db(6, session['pdf_filename'], text2summarize, session['openAI_summary_PDF'],session.get('summary_page_title', "Error: Could not Generate Title"))
                #Write the json to the file
                write_json_to_file(text2summarize_hash + "_insights.json", session['openAI_summary_JSON_PDF'])
                #print("summarizeURL - 17")
                if check_folder_exists(app.config['UPLOAD_CONTENT']):
                  #print("summarizeURL - 18")
                  #Write the content to the file
                  write_content_to_file(text2summarize_hash + ".txt", text2summarize)
                #Set the content_written to True
                session['content_written'] = True
                # Calculate token count and average tokens per sentence
                token_count = num_tokens_from_string(text2summarize)
                avg_tokens_per_sentence = avg_sentence_length(text2summarize)
                openAI_summary_str = json.dumps(session['openAI_summary_JSON_PDF'], indent=4)
                summary_page_title = openAI_page_title(session.get('openAI_summary_PDF'))
                session['summary_page_title'] = summary_page_title  
                if not session.get('name', False):
                  # If we are not logged in, we don't want to show the Name                
                  return render_template(
                      'keyInsightsPDF.html',
                      title='keyInsights PDF',
                      form=form,
                      text2summarize=text2summarize.split('\n'),
                      openAI_summary=session['openAI_summary_PDF'].split('\n'),
                      token_count=token_count,
                      avg_tokens_per_sentence=avg_tokens_per_sentence,
                      openAI_json=openAI_summary_str,
                      is_trimmed=session.get('is_trimmed', False),
                      form_prompt_nerds=session.get('form_prompt', False),
                      number_of_chunks=session.get('number_of_chunks', False),
                      text2summarize_hash=text2summarize_hash,
                      summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
                    )
                else:
                  # If we are logged in, we want to show the Name                  #                   
                  return render_template(
                      'keyInsightsPDF.html',
                      title='keyInsights PDF',
                      form=form,
                      text2summarize=text2summarize.split('\n'),
                      openAI_summary=session['openAI_summary_PDF'].split('\n'),
                      token_count=token_count,
                      avg_tokens_per_sentence=avg_tokens_per_sentence,
                      openAI_json=openAI_summary_str,
                      is_trimmed=session.get('is_trimmed', False),
                      form_prompt_nerds=session.get('form_prompt', False),
                      number_of_chunks=session.get('number_of_chunks', False),
                      text2summarize_hash=text2summarize_hash,
                      summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
                      name=session['name']
                    )
            else:
              print("summarizePDF - 12")
              #the summary was retrieved from the database, so we don't need to write it to DB again
              # Calculate token count and average tokens per sentence
              token_count = num_tokens_from_string(text2summarize)
              avg_tokens_per_sentence = avg_sentence_length(text2summarize)
              if not session['openAI_summary_JSON_PDF']:
                openAI_summary_str = "Retrived from Database"
              else:
                openAI_summary_str = json.dumps(session['openAI_summary_JSON_PDF'], indent=4)
              if not session.get('name', False):
                # If we are not logged in, we don't want to show the Name   
                return render_template(
                  'keyInsightsPDF.html',
                  title='Summarize PDF',
                  form=form,
                  text2summarize=text2summarize.split('\n'),
                  openAI_summary=session['openAI_summary_PDF'].split('\n'),
                  token_count=token_count,
                  avg_tokens_per_sentence=avg_tokens_per_sentence,
                  openAI_json=openAI_summary_str,
                  is_trimmed=session.get('is_trimmed', False),
                  form_prompt_nerds=session.get('form_prompt', False),
                  number_of_chunks=session.get('number_of_chunks', False),
                  text2summarize_hash=text2summarize_hash,
                  summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title")
                )
              else:
                # If we are logged in, we want to show the Name
                return render_template(
                  'keyInsightsPDF.html',
                  title='Summarize PDF',
                  form=form,
                  text2summarize=text2summarize.split('\n'),
                  openAI_summary=session['openAI_summary_PDF'].split('\n'),
                  token_count=token_count,
                  avg_tokens_per_sentence=avg_tokens_per_sentence,
                  openAI_json=openAI_summary_str,
                  is_trimmed=session.get('is_trimmed', False),
                  form_prompt_nerds=session.get('form_prompt', False),
                  number_of_chunks=session.get('number_of_chunks', False),
                  text2summarize_hash=text2summarize_hash,
                  summary_page_title=session.get('summary_page_title', "Error: Could not Generate Title"),
                  name=session['name']
                )
        else:
            clear_session()
            print("summarizePDF - 13")
            session['content_written'] = False
            if not session.get('name', False):
              return render_template('keyInsightsPDF.html',title='Summarize PDF', form=form)
            else:
              return render_template('keyInsightsPDF.html',title='Summarize PDF', form=form, name=session['name'])
    else:      
      session['content_written'] = False
      clear_session()
      if not session.get('name', False):
        return render_template('keyInsightsPDF.html',title='Summarize PDF', form=form)
      else:
        return render_template('keyInsightsPDF.html',title='Summarize PDF', form=form, name=session['name'])
    


# -------------------- Other  Routes --------------------

@app.route('/share/<hash>', methods=['GET', 'POST'])
def share(hash):
    #check if the hash exists in the Local Database, before calling the OpenAI API
    if check_if_hash_exists(hash):
        host = request.host
        share_url = f"https://{host}/share/{hash}"
        short_url = get_existing_short_url(share_url)
        
        if short_url is None:
            short_url = get_short_url(hash, host)       
        openAI_summary = get_summary_from_hash(hash)
        summary_page_title = get_title_from_hash(hash)
        #Support for Legacy Database entries without title
        if not summary_page_title:
            summary_page_title = openAI_page_title(openAI_summary)

        #short_url = get_short_url(hash)

        return render_template(
            'share.html',
            openAI_summary=openAI_summary.split('\n'),
            summary_page_title=summary_page_title,
            hash=hash,
            short_url=short_url,
        )
    else:
        return render_template('404.html'), 404

# Routes for the login and logout pages
@app.route('/admin-login', methods=['GET', 'POST'])
def adminlogin():
  if request.method == 'POST':
    username = request.form.get('username')
    if request.form.get('pw') == users.get(username, {}).get('pw'):
      user = User()
      user.id = username
      login_user(user)
      return redirect(url_for('logs'))
  if not session.get('name', False):  
    return render_template('adminlogin.html')
  else:
     return render_template('adminlogin.html', name=session['name'])

@app.route('/logout')
def logout():
  logout_user()
  session.clear()  # Clear session data
  return redirect(url_for('index'))

#rewriting the logs to show user's entries if session.get('name', False) is True
@app.route('/logs2', methods=['GET', 'POST'])
def logs2():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    if current_user.is_authenticated:
        entry_post_history = Entry_Posts_History.query \
            .options(joinedload(Entry_Posts_History.entry_post)) \
            .options(joinedload(Entry_Posts_History.oAuthUser)) \
            .order_by(Entry_Posts_History.entry_post_id.desc())

        all_entry_posts = Entry_Post.query.order_by(Entry_Post.id.desc()).all()

        final_results = []

        for entry_post in all_entry_posts:
            entry_post_history_item = next((item for item in entry_post_history if item.entry_post_id == entry_post.id), None)
            if entry_post_history_item:
                final_results.append({
                    'id': entry_post.id,
                    'timestamp': entry_post.timestamp,
                    'url': entry_post.url,
                    'text2summarize': entry_post.text2summarize,
                    'text2summarize_hash': entry_post.text2summarize_hash,
                    'openAIsummary': entry_post.openAIsummary,
                    'posttype': entry_post.posttype,
                    'email': entry_post_history_item.oAuthUser.email,
                    'name': entry_post_history_item.oAuthUser.name,
                })
            else:
                final_results.append({
                    'id': entry_post.id,
                    'timestamp': entry_post.timestamp,
                    'url': entry_post.url,
                    'text2summarize': entry_post.text2summarize,
                    'text2summarize_hash': entry_post.text2summarize_hash,
                    'openAIsummary': entry_post.openAIsummary,
                    'posttype': entry_post.posttype,
                    'email': 'N/A',
                    'name': 'N/A',
                })

        entries = CustomPagination(final_results, page, per_page, len(final_results))

    elif session.get('name', False):
        user = oAuthUser.query.filter_by(linkedin_id=session['linkedin_id']).first()
        if user:
            entry_post_history = Entry_Posts_History.query.filter_by(oAuthUser_id=user.id).order_by(Entry_Posts_History.id.desc()).paginate(page=page, per_page=per_page)
            entry_post_list = [entry.entry_post for entry in entry_post_history.items]
            entries = CustomPagination(entry_post_list, entry_post_history.page, entry_post_history.per_page, entry_post_history.total)
        else:
            entries = None
    else:
        return redirect(url_for('adminlogin'))

    if not session.get('name', False):
        return render_template('logs.html', entries=entries, is_authenticated=current_user.is_authenticated)
    else:
        return render_template('logs.html', entries=entries, is_authenticated=current_user.is_authenticated, name=session['name'])


# Assuming Entry_Posts_History and Entry_Post models are defined with SQLAlchemy

@app.route('/logs', methods=['GET', 'POST'])
def logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    if current_user.is_authenticated:
        # Directly paginate the query instead of fetching all and filtering in Python
        entry_post_history_paginated = Entry_Posts_History.query \
            .join(Entry_Posts_History.entry_post) \
            .join(Entry_Posts_History.oAuthUser) \
            .order_by(Entry_Posts_History.entry_post_id.desc()) \
            .paginate(page=page, per_page=per_page)

        final_results = [
            {
                'id': item.entry_post.id,
                'timestamp': item.entry_post.timestamp,
                'url': item.entry_post.url,
                'text2summarize': item.entry_post.text2summarize,
                'text2summarize_hash': item.entry_post.text2summarize_hash,
                'openAIsummary': item.entry_post.openAIsummary,
                'posttype': item.entry_post.posttype,
                'email': item.oAuthUser.email,
                'name': item.oAuthUser.name,
            } for item in entry_post_history_paginated.items
        ]

        entries = CustomPagination(final_results, page, per_page, entry_post_history_paginated.total)

    elif session.get('name', False):
        user = oAuthUser.query.filter_by(linkedin_id=session['linkedin_id']).first()
        if user:
            entry_post_history_paginated = Entry_Posts_History.query.filter_by(oAuthUser_id=user.id) \
                .order_by(Entry_Posts_History.id.desc()) \
                .paginate(page=page, per_page=per_page)

            entry_post_list = [entry.entry_post for entry in entry_post_history_paginated.items]
            entries = CustomPagination(entry_post_list, page, entry_post_history_paginated.page, entry_post_history_paginated.per_page, entry_post_history_paginated.total)
        else:
            entries = None
    else:
        return redirect(url_for('adminlogin'))

    return render_template('logs.html', entries=entries, is_authenticated=current_user.is_authenticated, name=session.get('name'))



# writing route for url_for('delete_entry', entry_id=entry.id) 
@app.route('/delete_entry/<entry_id>', methods=['GET', 'POST'])
@login_required
def delete_entry(entry_id):
  # delete the entry from the database
  delete_entry_from_db(entry_id)
  return redirect(url_for('logs')) 

#writing a route for a login required page where the hash is passed as a parameter and it loads the content from the json and content files
@app.route('/view/<hash>', methods=['GET', 'POST'])
@login_required
def view(hash):
  #check if the hash exists in the Local Database, before calling the OpenAI API
  if check_if_hash_exists(hash):
    openAI_summary = get_summary_from_hash(hash)
    text2summarize = read_from_file_content(hash+".txt")
    openAI_json = read_from_file_json(hash+".json")
    openAI_json_str = json.dumps(openAI_json, indent=4)
    summary_page_title = get_title_from_hash(hash)
    #Support for Legacy Database entries without title
    if not summary_page_title:
        summary_page_title = openAI_page_title(openAI_summary)    
    return render_template(
      'view.html',
      openAI_summary=openAI_summary.split('\n'),
      text2summarize=text2summarize.split('\n'),
      openAI_json=openAI_json_str,
      summary_page_title=summary_page_title,
      hash=hash
    )
  else:
    return render_template('404.html'), 404

@app.route('/openAI-debug', methods=['GET', 'POST'])
@login_required
def openAI_debug():
    clear_session()
    form = openAI_debug_form()
    global openAI_summary
    global text2summarize
    if form.validate_on_submit():
      openai_api_form_prompt = form.openAI_debug_form_prompt.data
      openai_api_form_key = form.openAI_debug_form_key.data
      text2summarize = openai_api_form_prompt
      openAI_summary = openAI_summarize_debug(openai_api_form_key, openai_api_form_prompt)
      return redirect(url_for('openAI_debug'))
    if (openAI_summary):
      openAI_summary_str = json.dumps(openAI_summary, indent=4)
      return render_template('openai-debug.html', title='openAI-debug', form=form,openai_key = os.getenv("OPENAI_API_KEY"), text2summarize=text2summarize, openAI_summary=openAI_summary_str, just_summary = openAI_summary["choices"][0]['message']['content'] )
    else:
        return render_template('openai-debug.html', title='openAI-debug', form=form, openai_key = os.getenv("OPENAI_API_KEY"))

@app.route("/signin", methods=['GET', 'POST'])
def signin():
    if not linkedin.authorized:
        return redirect(url_for("linkedin.login"))
    resp = linkedin.get("me")
    #get email 
    
    assert resp.ok
    data = resp.json()
    print(data)
    name = "{first} {last}".format(
        first=preferred_locale_value(data["firstName"]),
        last=preferred_locale_value(data["lastName"]),
    )
    return "You are {name} on LinkedIn".format(name=name)

#Signout route for blueprints
@app.route('/signout')
def signout():
  logout_user()
  session.clear()  # Clear session data
  linkedin_bp.token = None
  return redirect(url_for('index'))


# Write a function to check linkedin.authorized, 





# -------------------- OpenAI API Functions --------------------

def openAI_summarize_debug(form_openai_key, form_prompt):
    openai.api_key = form_openai_key
    message = {"role": "user", "content": form_prompt}
    response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages=[message],
      temperature=0.7,
      max_tokens=2000,
      top_p=1.0,
      frequency_penalty=0.0,
      presence_penalty=1
      )
    print(json.dumps(response, indent=4)) 
    return response


#function that takes the text2summarize chunks it to make sure its within the max token limit and then openAI API to with a custom prompt
def openAI_page_title(form_prompt):
    #if form_prompt:
    #  print("openAI_page_title:" + form_prompt)
    #else:
    #  print("openAI_page_title: form_prompt is empty")
    global_prompt = "Given the summary of the Article, Suggest a Title. treat every thing below as the article summary: \n\n"
    # Count tokens in the form_prompt
    token_count = num_tokens_from_string(form_prompt)
    # max_tokens = 3500 #original
    max_tokens = 4000
    
    # Trim the form_prompt if the token count exceeds the model's maximum limit
    if token_count > max_tokens:
        #print("prompt is too long, trimming...")
        form_prompt_chunks = []
        chunks = [sentence for sentence in sent_tokenize(form_prompt)]
        title_prompt = ''
        for sentence in chunks:
            if num_tokens_from_string(title_prompt + sentence) < max_tokens:
                title_prompt += sentence
    else:
       title_prompt = form_prompt
        # The prompt is not too long (its within the max token limit), so we can just call the API
    message = {"role": "user", "content": global_prompt + title_prompt}
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[message],
        temperature=0.7,
        max_tokens=500,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    openai_response = response["choices"][0]['message']['content']
    return openai_response

# Define a retry decorator with exponential backoff
def retry_with_exponential_backoff(func):
    def wrapper(*args, **kwargs):
        max_retries = 5
        retry_delay = 1  # Initial delay in seconds
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except (openai.error.ServiceUnavailableError) as e:
                error_type = "Rate limit exceeded" if isinstance(e, openai.error.RateLimitError) else "Service unavailable"
                print(f"{error_type}. Retrying after delay... (Attempt {attempt + 1} of {max_retries})")
                rollbar.report_message(f'{error_type}. Retrying after delay... {str(e)}', 'warning')
                rollbar.report_exc_info()
                time.sleep(retry_delay)
                # Increase the delay for the next retry with some random jitter
                retry_delay *= 2 * random.uniform(0.8, 1.2)
            except (openai.error.RateLimitError) as e:
                error_type = "Rate limit exceeded" if isinstance(e, openai.error.RateLimitError) else "Service unavailable"
                print(f"{error_type}. Retrying after delay... (Attempt {attempt + 1} of {max_retries})")
                rollbar.report_message(f'{error_type}. Retrying after delay... {str(e)}', 'warning')
                rollbar.report_exc_info()
                time.sleep(retry_delay)
                # Increase the delay for the next retry with some random jitter
                retry_delay *= 2 * random.uniform(0.8, 1.2)                
            except openai.error.OpenAIError as e:
                # Handle other OpenAI-specific errors
                print(f"An OpenAI error occurred: {e}")
                rollbar.report_message(f"An OpenAI error occurred: {e}", 'error')
                rollbar.report_exc_info()
                break  # Break out of retry loop for non-retryable errors
            except Exception as e:
                # Handle other unforeseen errors
                print(f"An unexpected error occurred: {e}")
                rollbar.report_message(f"An unexpected error occurred: {e}", 'error')
                rollbar.report_exc_info()
                break  # Break out of retry loop for non-retryable errors
        raise Exception("API call failed even after retries.")
    return wrapper

# Apply the retry decorator to the original function
@retry_with_exponential_backoff
# Functions to call the OpenAI API
def openAI_summarize_chunk(form_prompt):
    # This prompt is being used locally, so no need to declare it as global
    global_prompt = "Summarize the below text into a few short bullet points in English. Treat everything below this sentence as text to be summarized: \n\n"
    
    # Debug: Check the form_prompt at the start
    app.logger.debug(f"Received form_prompt: {form_prompt}")

    # Protect against empty or whitespace-only input
    if not form_prompt or form_prompt.isspace():
        app.logger.error("Received empty or whitespace-only input.")
        rollbar.report_message("Received empty or whitespace-only input.", 'error')
        return None, None, None, None
    
    # Step 1: Call the Moderation Endpoint First
    try:
        moderation_response = openai.Moderation.create(input=form_prompt)
        app.logger.info(f"Moderation response: {moderation_response}")
        print(moderation_response)
    except Exception as e:
        print(f"Moderation API call failed with error: {e}")
        app.logger.error(f"Moderation API call failed with error: {e}")
        rollbar.report_message(f"Moderation API call failed with error: {e}", 'error')
        rollbar.report_exc_info()
        return None, None, None, None
    
    # Step 2: Check the Moderation Result
    if moderation_response["results"][0]["flagged"]:
        # Construct a similar response structure indicating content violation
        app.logger.info("Content flagged by moderation.")
        response = {
            "choices": [{
                "message": {
                    "content": "Content does not comply with OpenAI's usage policies"
                }
            }]
        }
        return response, None, form_prompt, None

    # Step 3: Proceed as Normal if Content is Not Flagged   
    # Count tokens in the form_prompt
    token_count = num_tokens_from_string(form_prompt)
    app.logger.info(f"Token count for the 'form_prompt': {token_count}")
    max_tokens = 3500 #original
    # max_tokens = 2400
    # max_tokens = 1000
    is_trimmed = False
    
    # Trim the form_prompt if the token count exceeds the model's maximum limit
    if token_count > max_tokens:
        app.logger.info("Trimming the prompt as token count exceeds the limit.")
        form_prompt_chunks = []
        chunks = [sentence for sentence in sent_tokenize(form_prompt)]
        temp_prompt = ''
        
        # for sentence in chunks:
        #     if num_tokens_from_string(temp_prompt) < max_tokens:
        #         temp_prompt += sentence
        #     else:
        #         form_prompt_chunks.append(temp_prompt.strip())
        #         temp_prompt = sentence
        #         # Break the loop if the sentence still exceeds max_tokens after trimming
        #         if num_tokens_from_string(temp_prompt) > max_tokens:
        #             break
        
        # if temp_prompt != '':
        #     form_prompt_chunks.append(temp_prompt.strip())

        for sentence in chunks:
          # Check if adding the next sentence will exceed max_tokens
          if num_tokens_from_string(temp_prompt + sentence + global_prompt) <= max_tokens:
              temp_prompt += sentence
          else:
              form_prompt_chunks.append(temp_prompt.strip())
              temp_prompt = sentence
          
          # Handle the scenario where a single sentence exceeds max_tokens after including global_prompt
          while num_tokens_from_string(temp_prompt + global_prompt) > max_tokens:
              words = temp_prompt.split()
              partial_sentence = ''
              while words and num_tokens_from_string(partial_sentence + ' '.join(words[:1]) + global_prompt) <= max_tokens:
                  partial_sentence += words.pop(0) + ' '
              if not partial_sentence:
                  print(f"Unable to split sentence further: {temp_prompt}")
                  break
              form_prompt_chunks.append(partial_sentence.strip())
              temp_prompt = ' '.join(words)

        if temp_prompt:
          form_prompt_chunks.append(temp_prompt.strip())
        is_trimmed = True
        completed_messages = []
        openai_responses = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        app.logger.info(f"Total number of chunks: {len(form_prompt_chunks)}")
        app.logger.info(f"form_prompt_chunks: {form_prompt_chunks}")

        #check if the first element in form_prompt_chunks is an empty string, if so, remove it
        if form_prompt_chunks[0] == '':
          form_prompt_chunks.pop(0)
        
        for chunk in form_prompt_chunks:
            message = {"role": "user", "content": global_prompt + chunk}
            # Added try-except block for API call
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",#changed from 16k
                    messages=[message],
                    temperature=0.7,
                    max_tokens=1000,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=1
                )
                app.logger.info(f"API call succeeded with response: {response}")
            except Exception as e:
                print(f"API call failed with error: {e}")
                rollbar.report_message(f"API call failed with error: {e}", 'error')
                rollbar.report_exc_info()
                app.logger.error(f"API call failed with error: {e}")
                return None, None, None, None
                
            # Check if 'choices' and 'message' keys exist in the response
            if 'choices' in response and 'message' in response['choices'][0]:
                completed_messages.extend(response["choices"][0]['message']['content'].split('\n')[:-1])
            openai_responses.append(response)
            for key in total_usage:
                total_usage[key] += response["usage"][key]
                
        completed_messages.append(response["choices"][0]['message']['content'].split('\n')[-1])
        openai_response = openai_responses[-1].copy()
        openai_response["choices"] = [{"message": {"content": '\n'.join(completed_messages)}}]
        openai_response["usage"] = total_usage
        number_of_chunks = len(form_prompt_chunks)
        return openai_response, is_trimmed, form_prompt, number_of_chunks
    else:
        message = {"role": "user", "content": global_prompt + form_prompt}
        
        # Added try-except block for API call
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo", #changed from 16k
                messages=[message],
                temperature=0.7,
                max_tokens=1000,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=1
            )
        except Exception as e:
            print(f"API call failed with error: {e}")
            rollbar.report_message(f"API call failed with error: {e}", 'error')
            rollbar.report_exc_info()
            app.logger.error(f"API call failed with error: {e}")
            return None, None, None, None
        
        number_of_chunks = 1
        return response, is_trimmed, form_prompt, number_of_chunks



# Apply the retry decorator to the original function
@retry_with_exponential_backoff
# Functions to call the OpenAI API
def openAI_keyInsights_chunk(form_prompt):
    # This prompt is being used locally, so no need to declare it as global
    global_prompt = "What are the Key Insights from this text chunk below. Organize the response by sections dividing the article. The response should be in bullet points of keywords. Start giving the Insights directly; do not respond beginning with 'Key Insights...'. Be as concise as possible without losing the essence. Treat everything below this sentence as text to give Key Insights from: \n\n"
    
    # Protect against empty or whitespace-only input
    if not form_prompt or form_prompt.isspace():
        app.logger.error("Received empty or whitespace-only input.")
        rollbar.report_message("Received empty or whitespace-only input.", 'error')        
        return None, None, None, None
    
    # Step 1: Call the Moderation Endpoint First
    try:
        moderation_response = openai.Moderation.create(input=form_prompt)
        print(moderation_response)
    except Exception as e:
        print(f"Moderation API call failed with error: {e}")
        rollbar.report_message(f"Moderation API call failed with error: {e}", 'error')
        return None, None, None, None
    
    # Step 2: Check the Moderation Result
    if moderation_response["results"][0]["flagged"]:
        # Construct a similar response structure indicating content violation
        response = {
            "choices": [{
                "message": {
                    "content": "Content does not comply with OpenAI's usage policies"
                }
            }]
        }
        return response, None, form_prompt, None

    # Step 3: Proceed as Normal if Content is Not Flagged   
    # Count tokens in the form_prompt
    token_count = num_tokens_from_string(form_prompt)
    max_tokens = 3500 #original
    # max_tokens = 2400
    # max_tokens = 1000

    is_trimmed = False
    
    # Trim the form_prompt if the token count exceeds the model's maximum limit
    if token_count > max_tokens:
        form_prompt_chunks = []
        chunks = [sentence for sentence in sent_tokenize(form_prompt)]
        temp_prompt = ''
        
        # for sentence in chunks:
        #     if num_tokens_from_string(temp_prompt + sentence) < max_tokens:
        #         temp_prompt += sentence
        #     else:
        #         form_prompt_chunks.append(temp_prompt.strip())
        #         temp_prompt = sentence
        #         # Break the loop if the sentence still exceeds max_tokens after trimming
        #         if num_tokens_from_string(temp_prompt) > max_tokens:
        #             break
        
        # if temp_prompt != '':
        #     form_prompt_chunks.append(temp_prompt.strip())

        for sentence in chunks:
          # Check if adding the next sentence will exceed max_tokens
          if num_tokens_from_string(temp_prompt + sentence + global_prompt) <= max_tokens:
              temp_prompt += sentence
          else:
              form_prompt_chunks.append(temp_prompt.strip())
              temp_prompt = sentence
          
          # Handle the scenario where a single sentence exceeds max_tokens after including global_prompt
          while num_tokens_from_string(temp_prompt + global_prompt) > max_tokens:
              words = temp_prompt.split()
              partial_sentence = ''
              while words and num_tokens_from_string(partial_sentence + ' '.join(words[:1]) + global_prompt) <= max_tokens:
                  partial_sentence += words.pop(0) + ' '
              if not partial_sentence:
                  print(f"Unable to split sentence further: {temp_prompt}")
                  rollbar.report_message(f"Unable to split sentence further: {temp_prompt}", 'warning')
                  break
              form_prompt_chunks.append(partial_sentence.strip())
              temp_prompt = ' '.join(words)

        if temp_prompt:
          form_prompt_chunks.append(temp_prompt.strip())

        is_trimmed = True
        completed_messages = []
        openai_responses = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if form_prompt_chunks[0] == '':
          form_prompt_chunks.pop(0)
        for chunk in form_prompt_chunks:
            message = {"role": "user", "content": global_prompt + chunk}
            # Added try-except block for API call
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo", #changing this from 16K to 4K Model
                    messages=[message],
                    temperature=0.7,
                    max_tokens=1000,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=1
                )
            except Exception as e:
                print(f"API call failed with error: {e}")
                rollbar.report_message(f"API call failed with error: {e}", 'error')
                app.logger.error(f"API call failed with error: {e}")
                return None, None, None, None
                
            # Check if 'choices' and 'message' keys exist in the response
            if 'choices' in response and 'message' in response['choices'][0]:
                completed_messages.extend(response["choices"][0]['message']['content'].split('\n')[:-1])
            openai_responses.append(response)
            for key in total_usage:
                total_usage[key] += response["usage"][key]
                
        completed_messages.append(response["choices"][0]['message']['content'].split('\n')[-1])
        openai_response = openai_responses[-1].copy()
        openai_response["choices"] = [{"message": {"content": '\n'.join(completed_messages)}}]
        openai_response["usage"] = total_usage
        number_of_chunks = len(form_prompt_chunks)
        return openai_response, is_trimmed, form_prompt, number_of_chunks
    else:
        message = {"role": "user", "content": global_prompt + form_prompt}
        
        # Added try-except block for API call
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo", #changing this from 16K to 4K Model
                messages=[message],
                temperature=0.7,
                max_tokens=1000,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=1
            )
        except Exception as e:
            print(f"API call failed with error: {e}")
            rollbar.report_message(f"API call failed with error: {e}", 'error')
            app.logger.error(f"API call failed with error: {e}")
            return None, None, None, None
        
        number_of_chunks = 1
        return response, is_trimmed, form_prompt, number_of_chunks



# -------------------- Helper functions  --------------------

#function to clear the session
def clear_session():
  session.pop('content_written', None)
  session.pop('url', None)
  session.pop('text2summarize', None)
  session.pop('openAIsummary', None)
  session.pop('text2summarize_URL', None)
  session.pop('openAI_summary_URL', None) 
  session.pop('openAI_summary_URL_JSON', None)    
  session.pop('text2summarize_hash', None)
  session.pop('form_prompt', None)
  session.pop('global_prompt', None)
  session.pop('is_trimmed', None)
  session.pop('global_number_of_chunks', None)
  session.pop('openai_response', None)
  session.pop('openai_responses', None)
  session.pop('completed_messages', None)
  session.pop('total_usage', None)
  session.pop('form_prompt_chunks', None)
  session.pop('form_prompt_chunk', None)
  session.pop('title_prompt', None)