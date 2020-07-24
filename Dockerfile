FROM tiangolo/uwsgi-nginx-flask:python3.8
  
COPY ./app /app

RUN pip install -r /app/requirements.txt

RUN sh -c 'apt-get -y update'
RUN sh -c 'apt-get -y install tesseract-ocr'
RUN sh -c 'apt-get -y install libtesseract-dev'