FROM python:3.9-slim
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    librdkafka-dev
WORKDIR /app
COPY aisstream.py producer.py subscription.json requirements.txt /app/
RUN pip install -r requirements.txt 
EXPOSE 5000
CMD ["python", "aisstream.py"]
