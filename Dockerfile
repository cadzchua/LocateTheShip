FROM python:3.9-slim
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    librdkafka-dev
WORKDIR /app
COPY producer.py requirements.txt /app/
RUN pip install -r requirements.txt 
CMD ["python", "producer.py"]
