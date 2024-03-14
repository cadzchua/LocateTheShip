FROM python:3-alpine3.19
COPY requirements.txt .
RUN pip install -r requirement.txt
EXPOSE 6969
CMD python ./app.py