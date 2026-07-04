import os
import time
import shutil
import re
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash

app = Flask(__name__)
app.secret_key = "super_secret_key_for_unlimited_file_server"

# กำหนดโฟลเดอร์สำหรับเก็บไฟล์
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ตั้งค่าให้ Flask อนุญาตสตรีมไฟล์ขนาดใหญ่ได้
app.config['MAX_CONTENT_LENGTH'] = None 

def sanitize_filename(filename):
    """
    ฟังก์ชันทำความสะอาดชื่อไฟล์เพื่อความปลอดภัย 
    รองรับภาษาไทย และป้องกันอักขระอันตรายที่เป็นอันตรายต่อระบบไฟล์
    """
    # ลบอักขระที่ระบบปฏิบัติการไม่รองรับในชื่อไฟล์ เช่น / \ : * ? " < > |
    cleaned = re.sub(r'[\/\\:\*\?"<>\|]', '', filename)
    # ตัดช่องว่างหัวท้าย
    cleaned = cleaned.strip()
    # ถ้าหากชื่อไฟล์ว่างเปล่า ให้ใส่ชื่อเริ่มต้นเป็น file_ เพื่อป้องกันข้อผิดพลาด
    if not cleaned or cleaned.startswith('.'):
        cleaned = "uploaded_file" + cleaned
    return cleaned

def get_unique_filename(filename):
    """ฟังก์ชันจัดการไฟล์ชื่อซ้ำ โดยการเติม _1, _2 ต่อท้ายชื่อไฟล์"""
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename
    while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)):
        unique_filename = f"{base}_{counter}{ext}"
        counter += 1
    return unique_filename

def format_file_size(size_in_bytes):
    """ฟังก์ชันแปลงขนาดจาก Bytes เป็นหน่วยที่อ่านง่าย"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} TB"

def get_disk_status():
    """ฟังก์ชันคำนวณพื้นที่ว่างในฮาร์ดดิสก์ที่รันเซิร์ฟเวอร์"""
    total, used, free = shutil.disk_usage(UPLOAD_FOLDER)
    return {
        'total': format_file_size(total),
        'used': format_file_size(used),
        'free': format_file_size(free),
        'percent_used': round((used / total) * 100, 1)
    }

# สร้างโฟลเดอร์เก็บไฟล์หากยังไม่มี
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    raw_files = os.listdir(app.config['UPLOAD_FOLDER'])
    files_info = []
    sort_by = request.args.get('sort', 'newest')
    
    for file in raw_files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file)
        if os.path.isfile(file_path):
            file_stat = os.stat(file_path)
            files_info.append({
                'name': file,
                'raw_size': file_stat.st_size,
                'size': format_file_size(file_stat.st_size),
                'raw_time': file_stat.st_mtime,
                'time': time.strftime('%d/%m/%Y %H:%M', time.localtime(file_stat.st_mtime))
            })
            
    # จัดเรียงไฟล์ตามเงื่อนไข
    if sort_by == 'name_asc':
        files_info.sort(key=lambda x: x['name'].lower())
    elif sort_by == 'name_desc':
        files_info.sort(key=lambda x: x['name'].lower(), reverse=True)
    elif sort_by == 'size_asc':
        files_info.sort(key=lambda x: x['raw_size'])
    elif sort_by == 'size_desc':
        files_info.sort(key=lambda x: x['raw_size'], reverse=True)
    elif sort_by == 'oldest':
        files_info.sort(key=lambda x: x['raw_time'])
    else: # newest
        files_info.sort(key=lambda x: x['raw_time'], reverse=True)

    disk_info = get_disk_status()
    return render_template('index.html', files=files_info, disk=disk_info, current_sort=sort_by)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('ไม่พบไฟล์ในคำขอ', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('ไม่ได้เลือกไฟล์', 'error')
        return redirect(url_for('index'))
    
    if file:
        # ใช้ฟังก์ชันทำความสะอาดชื่อไฟล์ที่รองรับภาษาไทยแทน secure_filename
        filename = sanitize_filename(file.filename)
        filename = get_unique_filename(filename)
        dest_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            # ปรับปรุง: เขียนไฟล์แบบ Stream Chunk เพื่อประหยัด RAM สำหรับไฟล์ขนาดใหญ่มากๆ (เช่น หนัง, Backup)
            with open(dest_path, 'wb') as f:
                chunk_size = 4096 * 16  # 64 KB ต่อรอบ
                while True:
                    chunk = file.stream.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    
            flash(f'อัปโหลดไฟล์ "{filename}" สำเร็จแล้ว!', 'success')
        except Exception as e:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            flash(f'เกิดข้อผิดพลาดระหว่างอัปโหลด: {str(e)}', 'error')
            
    return redirect(url_for('index'))

@app.route('/download/<path:filename>')
def download_file(filename):
    # ปรับเป็น <path:filename> ป้องกันการป้อนชื่อย้อนโฟลเดอร์ และรองรับโครงสร้างชื่อพิเศษ
    # send_from_directory ปลอดภัยต่อ Path Traversal อยู่แล้วหากใช้ร่วมกับชื่อเดี่ยวๆ
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/delete/<path:filename>', methods=['POST'])
def delete_file(filename):
    try:
        # ป้องกันไม่ให้ใส่ตัวอักษรย้อนระบบไฟล์ (เช่น ../../../etc/passwd)
        secure_name = os.path.basename(filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            flash(f'ลบไฟล์ "{secure_name}" เรียบร้อยแล้ว', 'success')
        else:
            flash('ไม่พบไฟล์ที่ต้องการลบ', 'error')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการลบไฟล์: {str(e)}', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # รันเซิร์ฟเวอร์
    app.run(host='0.0.0.0', port=5000, debug=True)