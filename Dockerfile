# Use an official Python base image
FROM python:3.10-slim

# Set a working directory inside the container
WORKDIR /app

# Copy only the requirements file first (for better caching)
COPY requirements.txt /app/requirements.txt
# If you use Pipfile/Pipfile.lock or pyproject.toml instead, copy those.

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of your code
COPY . /app

# Expose the port on which Flask will run (5000 by default)
EXPOSE 5000

# We assume .env is copied over, 
# but be mindful if your .env contains secrets you do NOT want in the image.
# If it does contain sensitive data, you might prefer to pass them via environment
# variables at runtime (docker run --env-file=...).

# Run gunicorn (or you can just do flask run if you prefer)
# Using gunicorn is more production-friendly.
# "wsgi:app" means gunicorn will import `app` from wsgi.py
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wsgi:app"]