FROM tiangolo/uwsgi-nginx-flask:python3.8
  
COPY ./app /app

# instal  pip pakcages
RUN pip install -r /app/requirements.txt

# setup tesseract-ocr engine  https://github.com/tesseract-ocr/tesseract/wiki
RUN sudo apt install tesseract-ocr
RUN sudo apt install libtesseract-dev