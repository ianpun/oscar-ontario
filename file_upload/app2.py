from flask import Flask, request, redirect, url_for, render_template
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# Define the external folder to save uploaded files
EXTERNAL_UPLOAD_FOLDER = '/Users/drmrspiggy/Documents/OSCARdatabridge/OSCAR_document_import'
app.config['UPLOAD_FOLDER'] = EXTERNAL_UPLOAD_FOLDER

# Allow only jpg files
ALLOWED_EXTENSIONS = {'jpg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        # If the user does not select a file, the browser submits an empty file without a filename
        if file.filename == '':
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return redirect(url_for('upload_file', filename=filename))
    return render_template('index.html')

if __name__ == '__main__':
    if not os.path.exists(EXTERNAL_UPLOAD_FOLDER):
        os.makedirs(EXTERNAL_UPLOAD_FOLDER)
    app.run(host='0.0.0.0', port=5001, debug=True)
