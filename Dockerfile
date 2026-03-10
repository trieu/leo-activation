# Use official lightweight Python image
FROM python:3.11-slim

# Keep Python from generating .pyc files and force logs to show immediately
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the folder inside the container
WORKDIR /app

# Copy requirements and install them securely
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your actual Python code
COPY . .

# Expose the port Uvicorn uses
EXPOSE 8000

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]