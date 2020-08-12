import os
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
import io
from zipfile import ZipFile
import time
from PIL import Image
from flask import Flask, request, jsonify, send_file
from pytesseract import image_to_data,image_to_string,image_to_osd, pytesseract 
from azure.storage.blob import BlobClient
from azure.servicebus import ServiceBusClient,Message
import logging
from multiprocessing import Process
import json

# flask
app = Flask(__name__, static_folder="static")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# azure
AZURE_BLOB_STOR_CONN = os.getenv('AZURE_BLOB_STOR_CONN', default="DefaultEndpointsProtocol=https;AccountName=ssmtest2;AccountKey=F6wNhZnDUHh7vEw6bxeQb2yrz1Iqw1GPh9uLqwPwxjBUCNjYro3TGUum/kFnr25tG/fWzrqpauVhPnKUEPZAwA==;EndpointSuffix=core.windows.net")
AZURE_BLOB_CONT_NAME = os.getenv('AZURE_BLOB_CONT_NAME', default="images")
AZURE_SERV_BUS_CONN = os.getenv('AZURE_SERV_BUS_CONN', default="Endpoint=sb://ssm-test.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=4866x+b6U/qzuzNUK6upkZ0McMVEliCP8Skg2du7DM0=")
AZURE_SERV_QUE_NAME = os.getenv('AZURE_SERV_QUE_NAME', default="queue1")
AZURE_SERV_TOP_SEND = os.getenv('AZURE_SERV_TOP_SEND', default="topic1")

# log
logging.basicConfig(level=logging.NOTSET,format='[%(levelname)s] (%(threadName)-10s) %(message)s')

# tesseract
if os.name == 'nt':
    pytesseract.tesseract_cmd = os.getenv('TES_PATH', default=r"C:\Program Files\Tesseract-OCR\tesseract.exe") 
else:
    pytesseract.tesseract_cmd = os.getenv('TES_PATH', default=r"/usr/bin/tesseract")
   
def _file_is_allowed(file_name):
    allowed_extensions = {'png', 'jpg'}
    return '.' in file_name and file_name.rsplit('.', 1)[1].lower() in allowed_extensions

def _format_is_allowed(fmt):
    allowed_extensions = {'txt', 'tsv','osd'}
    return fmt in allowed_extensions

def _formats_is_allowed(fmts):
    allowed_extensions = {'txt', 'tsv','osd'}
    for fmt in fmts:
        return fmt in allowed_extensions
    return False
    
@app.route('/upload', methods=['POST'])
def upload_file():

    try:
        
        if 'file' not in request.files:
            raise Exception('No file part')
  
        file = request.files['file']
        file_name=file.filename
        if file_name == '':
            raise Exception('No file selected')

        if not _file_is_allowed(file_name):
            raise Exception('Allowed only png,jpg formats')
 
        if 'format' not in request.args:
            raise Exception('No format')

        result_format = request.args.get('format')
        result_formats=[]
        if ',' in result_format:
            result_formats=result_format.split(',')
            if not _formats_is_allowed(result_formats):
                raise Exception('Only txt,tsv,osd formats')
        else:
            if not _format_is_allowed(result_format):
                raise Exception('Only txt,tsv,osd formats')
 
        start_time = time.time()
        file_prefix = time.strftime("%Y%m%d%H%M%S")

        saved_path = os.path.join(app.static_folder, "files", file_prefix + "_" + secure_filename(file_name))
        file.save(saved_path)
        logging.info("{} uploaded!".format(saved_path))
        
        result_prefix = os.path.splitext(file_name)[0]
        result_path=None

        if len(result_formats)>0:

            result_path = os.path.join(app.static_folder, "files",file_prefix + "_" + result_prefix + ".zip")
            zip_entries=[]
            with ZipFile(result_path, 'w') as zipObj:
                for fmt in result_formats:
                    entry_path = os.path.join(app.static_folder, "files",file_prefix + "_" + result_prefix + "."+fmt)
                    img = Image.open(saved_path)
                    result_data=None
                    if(fmt=="tsv"):
                        result_data = image_to_data(img)
                    elif(fmt=="osd"):
                        result_data = image_to_osd(img)
                    else:
                        result_data = image_to_string(img)
                    with open(entry_path, 'wb') as result_file:
                        result_file.write(str.encode(result_data)) 
                    zipObj.write(entry_path,result_prefix + "."+fmt)
                    zip_entries.append(entry_path)
                    logging.info("{} recognized!".format(entry_path))
            for zip_entry in zip_entries:
                os.remove(zip_entry)
                logging.info("{} deleted!".format(zip_entry))
        else:
 
            result_path = os.path.join(app.static_folder, "files",file_prefix + "_" + result_prefix + "."+result_format)
            img = Image.open(saved_path)
            result_data=None
            if(result_format=="tsv"):
                result_data = image_to_data(img)
            elif(result_format=="osd"):
                result_data = image_to_osd(img)
            else:
                result_data = image_to_string(img)
            with open(result_path, 'wb') as result_file:
                result_file.write(str.encode(result_data)) 
            logging.info("{} recognized!".format(saved_path))

        end_time = time.time()
        duration_time = end_time - start_time

        msg = "finished! ({0} sec)".format(duration_time)
        logging.info(msg)

        if len(result_formats)>0:
            return send_file(filename_or_fp=result_path, attachment_filename=file_prefix + ".zip",as_attachment=True)
        else:
            return send_file(filename_or_fp=result_path, attachment_filename=file_prefix + "."+result_format,as_attachment=True)
    except Exception as e:
        logging.error(e)
        resp = jsonify({'message': str(e)})
        resp.status_code = 400
        return resp

def _download_blob(saved_path,file_name):
    download_blob = BlobClient.from_connection_string(conn_str=AZURE_BLOB_STOR_CONN, container_name=AZURE_BLOB_CONT_NAME, blob_name=file_name)
    with open(saved_path, "wb") as file_blob:
        blob_data = download_blob.download_blob()
        blob_data.readinto(file_blob)
    logging.info("{} downloaded!".format(saved_path))

def _upload_blob(result_path,file_name):
    upload_blob = BlobClient.from_connection_string(conn_str=AZURE_BLOB_STOR_CONN, container_name=AZURE_BLOB_CONT_NAME, blob_name=file_name)
    with open(result_path, "rb") as upload_data:
        upload_blob.upload_blob(upload_data)
    logging.info("{} uploaded!".format(result_path))

def _process_queue():
    sleep_time = 1

    try:
        client = ServiceBusClient.from_connection_string(AZURE_SERV_BUS_CONN)
        while True:
            with client.get_queue_receiver(AZURE_SERV_QUE_NAME) as receiver:
                for message in receiver:
                    logging.info("Receiving: {}".format(message))
                    _process_message(message)
            time.sleep(sleep_time)
    except Exception as e:
        logging.error(e)
    finally:
        time.sleep(sleep_time)
        _start_job()
  
def _process_message(msg):
     
    try:
        reqId = msg.user_properties[b"requestId"]
        logging.info("Request: {}".format(reqId))

        objReq = json.loads(str(msg))
        
        file_url = objReq["fileUrl"]
        logging.info("File: {}".format(file_url))

        result_format = objReq["format"]
        logging.info("Result format: {}".format(result_format))
        result_formats=[]
        if ',' in result_format:
            result_formats=result_format.split(',')
            if not _formats_is_allowed(result_formats):
                raise Exception('Only txt,tsv,osd formats')
        else:
            if not _format_is_allowed(result_format):
                raise Exception('Only txt,tsv,osd formats')
         
        file_path = urlparse(file_url)
        file_name = os.path.basename(file_path.path)
        
        if  _file_is_allowed(file_name):
            
            file_prefix = time.strftime("%Y%m%d%H%M%S")
            saved_path = os.path.join(app.static_folder, "jobs",file_prefix + "_" + AZURE_BLOB_CONT_NAME + "_" + file_name)
            _download_blob(saved_path,file_name)

            result_prefix = os.path.splitext(file_name)[0]
            if len(result_formats)>0:
                result_path = os.path.join(app.static_folder, "jobs",file_prefix + "_" + result_prefix + ".zip")
                zip_entries=[]
                with ZipFile(result_path, 'w') as zipObj:
                    for fmt in result_formats:
                        entry_path = os.path.join(app.static_folder, "jobs",file_prefix + "_" + result_prefix + "."+fmt)
                        img = Image.open(saved_path)
                        result_data=None
                        if(fmt=="tsv"):
                            result_data = image_to_data(img)
                        elif(fmt=="osd"):
                            result_data = image_to_osd(img)
                        else:
                            result_data = image_to_string(img)
                        with open(entry_path, 'wb') as result_file:
                            result_file.write(str.encode(result_data)) 
                        zipObj.write(entry_path,result_prefix + "."+fmt)
                        zip_entries.append(entry_path)
                        logging.info("{} recognized!".format(entry_path))
                for zip_entry in zip_entries:
                    os.remove(zip_entry)
                    logging.info("{} deleted!".format(zip_entry))
            else:
                result_path = os.path.join(app.static_folder, "jobs", file_prefix + "_" + AZURE_BLOB_CONT_NAME + "_" + result_prefix + "."+result_format)
                img = Image.open(saved_path)
                result_data=None
                if(result_format=="tsv"):
                    result_data = image_to_data(img)
                elif(result_format=="osd"):
                    result_data = image_to_osd(img)
                else:
                    result_data = image_to_string(img)
                with open(result_path, 'wb') as result_file:
                    result_file.write(str.encode(result_data)) 
                logging.info("{} recognized!".format(saved_path))
  
            result_url=None
            if len(result_formats)>0:
                result_url=str.replace(file_url,file_name,  result_prefix + ".zip") 
                _upload_blob(result_path,result_prefix + ".zip")
            else:
                result_url=str.replace(file_url,file_name,  result_prefix + "."+result_format)
                _upload_blob(result_path,result_prefix + "."+result_format)


            _send_topic(reqId,result_url)

        else:
             logging.error("Allowed only png,jpg formats: {}".format(file_name)) 
    except Exception as e:
        logging.error(str(e)) 
    finally:
        msg.complete() 

def _send_topic(req_id,file_url):
    logging.info("Sending to topic message: {}".format(file_url))

    start_time = time.time()
    with ServiceBusClient.from_connection_string(AZURE_SERV_BUS_CONN) as client:
        with client.get_topic_sender(AZURE_SERV_TOP_SEND) as sender:
            body_payload={
                'resultUrl':file_url
            }
            user_props = {
                'requestId': req_id
            }
            message = Message(json.dumps(body_payload))
            message.user_properties = user_props
            message.properties.content_type = 'application/json'
            sender.send_messages(message)
    end_time = time.time()
    duration_time = end_time - start_time
    logging.info("send! ({0} sec)".format(duration_time))

job_listener= None

def _start_job():

    try:
        global job_listener
    
        if job_listener==None:
           job_listener= Process(target=_process_queue)
        else:
            job_listener.terminate() 

        job_listener.start()

        logging.info("Job started")
    except Exception as e:
        logging.error(e)

_start_job()

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=80)
