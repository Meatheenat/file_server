import os
import time
import shutil
import re
import platform
import subprocess
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash

app = Flask(__name__)
# คีย์ลับสำหรับสร้าง Session ของระบบแจ้งเตือน (Flash)
app.secret_key = "super_secret_key_for_unlimited_file_server"

# กำหนดและสร้างโฟลเดอร์สำหรับเก็บไฟล์
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ปลดล็อกขนาดไฟล์ให้สามารถอัปโหลดได้ไม่จำกัด
app.config['MAX_CONTENT_LENGTH'] = None 

def sanitize_filename(filename):
    """ทำความสะอาดชื่อไฟล์ รองรับภาษาไทยและลบอักขระพิเศษที่เป็นอันตราย"""
    cleaned = re.sub(r'[\/\\:\*\?"<>\|]', '', filename).strip()
    if not cleaned or cleaned.startswith('.'):
        cleaned = "uploaded_file_" + cleaned
    return cleaned

def get_unique_filename(filename):
    """จัดการไฟล์ชื่อซ้ำ โดยการเติม _1, _2 ต่อท้าย"""
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename
    while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)):
        unique_filename = f"{base}_{counter}{ext}"
        counter += 1
    return unique_filename

def format_file_size(size_in_bytes):
    """แปลงขนาดไฟล์จากหน่วย Bytes เป็นหน่วยที่มนุษย์อ่านง่าย (KB, MB, GB)"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} TB"

def get_disk_status():
    """คำนวณและคืนค่าพื้นที่ว่างของฮาร์ดดิสก์เซิร์ฟเวอร์"""
    total, used, free = shutil.disk_usage(UPLOAD_FOLDER)
    return {
        'total': format_file_size(total),
        'used': format_file_size(used),
        'free': format_file_size(free),
        'percent_used': round((used / total) * 100, 1)
    }

@app.route('/')
def index():
    """หน้าหลักของเว็บไซต์ โหลดรายการไฟล์และจัดเรียงตามที่ผู้ใช้เลือก"""
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
            
    # ระบบจัดเรียงไฟล์
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
    else: # newest (ค่าเริ่มต้น)
        files_info.sort(key=lambda x: x['raw_time'], reverse=True)

    disk_info = get_disk_status()
    return render_template('index.html', files=files_info, disk=disk_info, current_sort=sort_by)

@app.route('/upload', methods=['POST'])
def upload_file():
    """จัดการการอัปโหลดไฟล์ เขียนไฟล์ลงดิสก์แบบสตรีมมิ่งเพื่อประหยัด RAM"""
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('ไม่ได้เลือกไฟล์ หรือไม่พบไฟล์', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    filename = get_unique_filename(sanitize_filename(file.filename))
    dest_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        # อ่านและเขียนไฟล์ทีละ 64KB ช่วยให้เครื่องไม่ค้างเมื่ออัปโหลดไฟล์ขนาด GB
        with open(dest_path, 'wb') as f:
            chunk_size = 4096 * 16  
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
    """ส่งไฟล์ให้ผู้ใช้ดาวน์โหลดลงเครื่อง"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/view/<path:filename>')
def view_file(filename):
    """ส่งไฟล์ให้เบราว์เซอร์เปิดดู (ถ้าเบราว์เซอร์รองรับ เช่น รูปภาพ, วิดีโอ, PDF)"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/run_on_server/<path:filename>', methods=['POST'])
def run_on_server(filename):
    """สั่งให้คอมพิวเตอร์เครื่องหลัก (เซิร์ฟเวอร์) เปิดไฟล์นั้นขึ้นมา"""
    secure_name = os.path.basename(filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
    
    if os.path.exists(file_path):
        try:
            # เลือกคำสั่งเปิดไฟล์ตามระบบปฏิบัติการของเซิร์ฟเวอร์
            if platform.system() == 'Windows':
                os.startfile(file_path)
            elif platform.system() == 'Darwin': # macOS
                subprocess.call(('open', file_path))
            else: # Linux
                subprocess.call(('xdg-open', file_path))
                
            flash(f'กำลังสั่งเปิดไฟล์ "{secure_name}" บนหน้าจอเซิร์ฟเวอร์', 'success')
        except Exception as e:
            flash(f'ไม่สามารถเปิดไฟล์ได้: {str(e)}', 'error')
    else:
        flash('ไม่พบไฟล์', 'error')
        
    return redirect(url_for('index'))

@app.route('/delete/<path:filename>', methods=['POST'])
def delete_file(filename):
    """ลบไฟล์ออกจากเซิร์ฟเวอร์"""
    try:
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
    # รันเซิร์ฟเวอร์บนทุก IP Address ในเครือข่าย พอร์ต 5000
    app.run(host='0.0.0.0', port=5000, debug=True)