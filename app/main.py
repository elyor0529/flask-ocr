import os
from urllib.parse import urlparse
import uuid
import time
from PIL import Image
from flask import Flask, request, jsonify, send_file
from pytesseract import image_to_string, pytesseract 
from azure.storage.blob import BlobClient

app = Flask(__name__, static_folder="static")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

TES_LANG = os.getenv('TES_LAN', default="eng")
AZURE_STOR_CONN = os.getenv('AZURE_STOR_CONN', default="AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;DefaultEndpointsProtocol=http;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;")

if os.name == 'nt':
    pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
else:
    pytesseract.tesseract_cmd = r'/usr/bin/tesseract'


def file_is_allowed(filename):
    allowed_extensions = {'png', 'jpg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
 
@app.route('/')
def home_page():
    return 'Images OCR tool!'


@app.route('/upload', methods=['POST'])
def upload_file():

    if 'files[]' not in request.form:
        resp = jsonify({'message': 'No file part in the request'})
        resp.status_code = 400
        return resp
     
    files = request.form.getlist('files[]') 
    try:
        start_time= time.time()

        for file in files:

            if file == '':
                raise Exception({'message': 'No file selected'}) 

            file_path = urlparse(file)
            file_name = os.path.basename(file_path.path)
            if not file_is_allowed(file_name):
                raise Exception({'message': 'Allowed file types are png,jpg'})
          
            file_prefix = str(uuid.uuid4())
            saved_path = os.path.join(app.static_folder, "tmp", file_prefix+"_" + file_name)
            
            download_blob = BlobClient.from_connection_string(conn_str=AZURE_STOR_CONN, container_name="images", blob_name=file)
            with open(saved_path, "wb") as file_blob:
                blob_data = download_blob.download_blob()
                blob_data.readinto(file_blob)

            result_prefix=os.path.splitext(file_name)[0]
            result_path = os.path.join(app.static_folder, "logs", file_prefix+"_"+result_prefix+ ".log")
            with open(result_path, 'wb') as result_blob:
                img = Image.open(saved_path)
                content = image_to_string(img, lang=TES_LANG)
                result_blob.write(str.encode(content)) 

            upload_blob = BlobClient.from_connection_string(conn_str=AZURE_STOR_CONN, container_name="images", blob_name=result_prefix+ ".log")
            with open(result_path, "rb") as upload_data:
                upload_blob.upload_blob(upload_data)

        end_time=time.time()
        duration_time = end_time - start_time
        resp = jsonify({'message':"done! ({0} sec)".format(duration_time)})
        resp.status_code = 200
        return resp
    except Exception as e:
        resp = jsonify({'message': str(e)})
        resp.status_code = 400
        return resp


if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=80)
