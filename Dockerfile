FROM python:3.11

RUN mkdir /app
WORKDIR /app

RUN apt update && apt install -y gettext
# RUN apt install -y postgresql-client # uncomment when migrate to postgresql
RUN pip install uvicorn[standard] pip-tools
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .