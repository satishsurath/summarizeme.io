
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.widgets import TextArea
from wtforms.fields import URLField
from wtforms.validators import DataRequired, URL
from flask_wtf.file import FileField, FileRequired, FileAllowed

class SummarizeFromText(FlaskForm):
    summarize = StringField('Paste / type the text:', widget=TextArea(), validators=[DataRequired()])
    accept_terms = BooleanField('I accept the Terms of Use and Privacy Policy', validators=[DataRequired()])
    submit = SubmitField('Summarize')

class SummarizeFromURL(FlaskForm):
    summarize = URLField('Paste / type the URL of the webpage:', validators=[DataRequired(), URL(message='Please enter a valid URL.')])
    accept_terms = BooleanField('I accept the Terms of Use and Privacy Policy', validators=[DataRequired()])
    submit = SubmitField('Summarize')

class SummarizeFromYouTube(FlaskForm):
    youtube_url = URLField('Paste / type the URL of the webpage:', validators=[DataRequired(), URL(message='Please enter a valid YouTube URL.')])
    accept_terms = BooleanField('I accept the Terms of Use and Privacy Policy', validators=[DataRequired()])
    submit = SubmitField('Summarize')

class UploadPDFForm(FlaskForm):
    pdf = FileField('Upload PDF file:', validators=[FileRequired(), FileAllowed(['pdf'], 'PDF files only')])
    accept_terms = BooleanField('I accept the Terms of Use and Privacy Policy', validators=[DataRequired()])
    submit = SubmitField('Summarize')

class openAI_debug_form(FlaskForm):
    openAI_debug_form_key = StringField('Paste your OpenAI API Key (will not be saved)')
    openAI_debug_form_prompt = StringField('OpenAI Input:', widget=TextArea(), validators=[DataRequired()])
    submit = SubmitField('Submit')   



