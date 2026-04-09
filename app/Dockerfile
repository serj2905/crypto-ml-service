FROM python:3.12-slim

WORKDIR /APP

COPY requirements.txt /APP/

RUN pip install -r requirements.txt

EXPOSE 8080

COPY . /app

CMD ["python", "main.py"]
