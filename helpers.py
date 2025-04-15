#!/usr/bin/env python3
# abstract frame TV interface

import logging
from pathlib import Path
import io
import random, string
import asyncio
import time
import datetime
from pprint import pformat
from PIL import Image, ImageFilter, ImageChops
from PIL.ExifTags import TAGS, GPSTAGS

logging.basicConfig(level=logging.INFO)

class helpers:
    
    allowed_ext = ['jpg', 'jpeg', 'png', 'bmp', 'tif']
    
    def __init__(self, folder=None):
        self.log = logging.getLogger('Main.'+__class__.__name__)
        self.debug = self.log.getEffectiveLevel() <= logging.DEBUG
        self.folder = folder
        self.exit = False
        self.timers = {}
        
    async def wait_seconds(self, duration=1):
        '''
        pause for specific duration (seconds) while allowing exit
        '''
        name = ''.join(random.choice(string.ascii_letters) for x in range(12))
        self.timers[name] = time.time()
        while time.time() - self.timers[name] < duration and not self.exit:
            await asyncio.sleep(1)
        self.timers.pop(name)
        
    def format_files(self, files):
        '''
        format list for logging if Path or string:
        '''
        return [file.name if isinstance(file, Path) else file for file in files]
        
    def get_folder_files(self, path=False):
        '''
        returns list of files names (str) or Path (if path is True) in folder if extension matches allowed image types
        '''
        return [f if path else f.name for f in self.folder.iterdir() if f.is_file() and self.get_file_type(f) in self.allowed_ext]
        
    def get_time(self, sec):
        '''
        returns seconds as timedelta for display as h:m:s
        '''
        return datetime.timedelta(seconds = sec)
        
    def get_exif_datetime(self, date):
        '''
        gets datetime object from exif format
        '''
        return datetime.datetime.fromisoformat(date.replace(':', '-', 2))
        
    def get_suffix(self, filename):
        '''
        get suffix without '.' or ''
        '''
        return filename.suffix[1:].lower()
        
    def get_Path(self, file):
        '''
        returns file as a Path object
        '''
        return Path(file)
        
    def get_PIL_image(self, file):
        '''
        loads and returns PIL image
        '''
        return Image.open(file)
        
    def update_tags(self, tags_dict={}):
        '''
        update Exif TAGS with additional tags
        '''
        TAGS.update(tags_dict)
        return TAGS
        
    def gps_exif_log(self, file, gpsinfo={}):
        '''
        pretty exif GPS logging
        '''
        self.log.debug('{}: GPS info:\r\n{}'.format(file, pformat({'{}({})'.format(GPSTAGS[k], k):v for k, v in gpsinfo.items()})))
        
    def exif_log(self, file, exif):
        '''
        pretty exif log
        '''
        self.log.debug('{}: exif tags:\r\n{}'.format(file, pformat(exif)))
        
    def random_choice(self, choices=[]):
        '''
        return random choice from list
        '''
        return random.choice(choices)
        
    def get_last_updated(self, filename):
        '''
        get last updated timestamp for file
        '''
        try:
            return filename.stat().st_mtime
        except Exception as e:
            self.log.exception(e)
            
    async def wait_for_files(self, files):
        #wait for files to arrive
        await self.wait_seconds(min(10, 5 * len(files)))
        
    def log_progress(self, total, count):
        '''
        log % progress every 10% if this will take a while
        '''
        if total >= 1000:
            percent = min(100,(count*100)//total)
            if count % (total//10) == 0:
                self.log.info('{}% complete'.format(percent))
                
    def html_markup(self, text):
        '''
        replace newlines with html <br>
        '''
        if text:
            return text.replace('\n', '<br>')
                
    def read_file(self, filename):
        '''
        read image file, return file binary data and file type
        '''
        try:
            file_data = Path(filename).read_bytes()
            file_type = self.get_file_type(filename)
            return file_data, file_type
        except Exception as e:
            self.log.error('Error reading file: {}, {}'.format(filename, e))
        return None, None
                
    def are_images_equal(self, my_data, img2):
        '''
        rough check if images are similar using PIL (avoid numpy which is faster)
        '''
        img1 = self.get_PIL_image(io.BytesIO(my_data))
        img1 = img1.convert('L').resize((384, 216)).filter(ImageFilter.GaussianBlur(radius=4))
        img2 = img2.convert('L').resize((384, 216)).filter(ImageFilter.GaussianBlur(radius=4))
        img3 = ImageChops.difference(img1, img2)    #updated 11/3/25 per suggestion in issue #11
        diff = sum(list(img3.getdata()))/(384*216)  #normalize
        equal_content = diff <= 5.0                 #pick a threshhold
        self.log.debug('equal_content: {}, diff: {}'.format(equal_content, round(diff, 2)))
        return equal_content, diff
        
    def get_file_type(self, filename, image_data=None):
        '''
        try to figure out what kind of image file is, starting with the extension
        fix the file type if it's wrong
        '''
        try:
            file_type = self.get_suffix(filename)
            if file_type in self.allowed_ext:
                file_type = self.fix_file_type(filename, file_type, image_data)
                return file_type
        except Exception as e:
            self.log.error('Error reading file: {}, {}'.format(filename, e))
        return None
        
    def fix_file_type(self, filename, file_type, image_data=None):
        '''
        check file type
        '''
        if file_type:
            org = file_type
            file_type = self.get_PIL_image(filename).format.lower() if not image_data else image_data.format.lower()
            if file_type in['jpg', 'jpeg', 'mpo']:
                file_type = 'jpeg'
            if not (org == file_type or (org == 'jpg' and file_type == 'jpeg')):
                self.log.warning('file {} type changed from {} to {}'.format(filename, org, file_type))
        return file_type
        
    def next_value(self, value, lst):
        '''
        get next value from list, or return first element
        return None if list is empty
        '''
        return lst[(lst.index(value)+1) % len(lst)] if value in lst else lst[0] if lst else None
        
    def load_files(self):
        '''
        reads folder files, and returns dictionary of filenames and binary data
        '''
        files = self.get_folder_files(True)
        self.log.info('loading files: {}'.format(self.format_files(files)))
        files_images = self.get_files_dict(files)
        self.log.info('loaded: {}'.format(self.format_files(files_images.keys())))
        return files_images
        
    def get_files_dict(self, files):
        '''
        makes a dictionary of filename and file binary data in PIL format
        warns if file type given by extension is wrong
        '''
        files_images = {}
        for file in files:
            try:
                data = self.get_PIL_image(file)
                format = self.get_file_type(file, data)
                if not (self.get_suffix(file) == format or (format=='jpeg' and self.get_suffix(file) == 'jpg')):
                    self.log.warning('file: {} is of type {}, the extension is wrong! please fix this'.format(file.name, format))
                files_images[file] = data
            except Exception as e:
                self.log.warning('Error loading: {}, {}'.format(file, e))
        return files_images
        
    def update_uploaded_files(self, filename, content_id, uploaded_files={}):
        '''
        update dictionary with filename
        '''
        uploaded_files.pop(filename.name, None)
        if content_id:
            uploaded_files[filename.name] = {'content_id': content_id, 'modified':self.get_last_updated(filename)}
        return uploaded_files
        
    def get_image_for_ai(self, image_file, client):
        '''
        load image for AI use
        check size and return PIL image or file ref after uploading or None if file too big
        '''
        image_size = image_file.stat().st_size
        if image_size >= 2*1024*1024*1024:      #2Gb file size limit
            self.log.warning('{}: file is over 2GB - so too large to upload'.format(image_file.name))
            return None
        if image_size > 19*1024*1024:           #20MB inline upload limit, so upload seperately
            return client.files.upload(file=image_file)
        return self.get_PIL_image(image_file)
        
    def update_text(self, info, text, new_info):
        '''
        update text and info with AI information
        '''
        updated = False
        for k, v in new_info.items():
            if not text.get(k) and not info.get(k):
                text[k] = self.html_markup(new_info[k])
                info[k] = self.html_markup(new_info[k])
                updated = True
        return updated
    
async def main():
    global log
    log = logging.getLogger('Main')
    log.info('This is a library for the web_interface, please run that instead')

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass