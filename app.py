import os
import time
from PIL import Image
from flask import Flask, request, jsonify, send_file
from pytesseract import image_to_string, pytesseract

app = Flask(__name__, static_folder="static")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

pytesseract.tesseract_cmd = os.path.join(app.static_folder, "teseract", "tesseract.exe")


def file_is_allowed(filename):
    allowed_extensions = {'png', 'jpg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


@app.route('/')
def home_page():
    return 'Images OCR tool!'


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'files[]' not in request.files:
        resp = jsonify({'message': 'No file part in the request'})
        resp.status_code = 400
        return resp
    files = request.files.getlist('files[]')
    for file in files:
        if file.filename == '':
            resp = jsonify({'message': 'No file selected for uploading'})
            resp.status_code = 400
            return resp

        if not file_is_allowed(file.filename):
            resp = jsonify({'message': 'Allowed file types are png,jpg'})
            resp.status_code = 400
            return resp
    return return_ocr_file(files)


def return_ocr_file(files):
    try:
        timestamp = time.strftime("%Y%m%d%H%M%S")
        result = os.path.join(app.static_folder, "logs", timestamp + ".log")
        output = open(result, 'w+')
        for file in files:
            img = Image.open(file.stream)
            content = image_to_string(img, lang='eng')
            output.write(content + '\r\n')
        output.close()
        return send_file(filename_or_fp=result, attachment_filename="result-" + timestamp + ".txt", as_attachment=True)
    except Exception as e:
        resp = jsonify({'message': str(e)})
        resp.status_code = 400
        return resp


if __name__ == '__main__':
    app.run()
