#!/usr/bin/env python3
# abstract frame TV interface

import logging
from pathlib import Path
from io import BytesIO
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
        self.timers = set()
        asyncio.create_task(self.cancel_timers())
 
    async def wait_seconds(self, duration=1):
        '''
        pause for specific duration (seconds) while allowing cancelling
        '''
        task = asyncio.create_task(asyncio.sleep(duration))
        self.timers.add(task)
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self.timers.remove(task)
            
    async def cancel_timers(self):
        while not self.exit:
            await asyncio.sleep(2)
        try:
            self.log.info('cancelling sleep tasks')
            [t.cancel() for t in self.timers if not t.done()]
        except Exception as e:
            self.log.info(e)
        
    def format_files(self, files):
        '''
        format list for logging if Path or string:
        '''
        return [file.name if isinstance(file, Path) else file for file in files]
        
    def get_folder_files(self, path=False):
        '''
        returns list of files names (str) or Path (if path is True) in folder if extension matches allowed image types
        '''
        return [f if path else f.name for f in self.folder.iterdir() if f.is_file() and self.get_suffix(f) in self.allowed_ext]
        
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
        
    def get_PIL_image(self, file, raw=False, unchanged=False):
        '''
        loads and returns PIL image as JPEG format or raw jpg binary data if raw
        if unchanged, do not convert image to JPEG (used for exif data extraction)
        '''
        try:
            file = file if isinstance(file, (str, Path)) else BytesIO(file)
            img = Image.open(file)
            if img.format != 'JPEG' and not unchanged:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                membuf = BytesIO()
                img.save(membuf, format="JPEG", quality="maximum")
                return membuf if raw else Image.open(membuf)
            return file.read_bytes() if raw else img
        except Exception as e:
            self.log.warning('failed to load PIL image: {}'.format(e))
        return None
        
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
                
    def are_images_equal(self, my_data, img2):
        '''
        rough check if images are similar using PIL (avoid numpy which is faster)
        my_data is binary, so convert to PIL format first
        '''
        img1 = self.get_PIL_image(my_data)
        img1 = img1.convert('L').resize((384, 216)).filter(ImageFilter.GaussianBlur(radius=4))
        img2 = img2.convert('L').resize((384, 216)).filter(ImageFilter.GaussianBlur(radius=4))
        img3 = ImageChops.difference(img1, img2)    #updated 11/3/25 per suggestion in issue #11
        diff = sum(list(img3.getdata()))/(384*216)  #normalize
        equal_content = diff <= 5.0                 #pick a threshhold
        self.log.debug('equal_content: {}, diff: {}'.format(equal_content, round(diff, 2)))
        return equal_content, diff
        
    def are_images_equal_experiment(self, my_data, img2):
        '''
        rough check if images are similar using PIL (avoid numpy which is faster)
        my_data is binary, so convert to PIL format first
        '''
        img1 = self.get_PIL_image(my_data)
        img1 = img1.convert('RGB').resize((384, 216))
        img2 = img2.convert('RGB').resize((384, 216))
        img3 = ImageChops.difference(img1, img2).convert('L')    #updated 11/3/25 per suggestion in issue #11
        hist = img3.histogram()
        diff = sum(value * i for i, value in enumerate(hist))/(384*216)
        equal_content = diff <= 5.0                 #pick a threshhold
        self.log.debug('equal_content: {}, diff: {}'.format(equal_content, round(diff, 2)))
        return equal_content, diff
        
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
        '''
        try:
            return {file: self.get_PIL_image(file) for file in files}
        except Exception as e:
            self.log.warning('Error loading: {}, {}'.format(files, e))
        return {}
        
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