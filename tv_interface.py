#!/usr/bin/env python3
# abstract frame TV interface

import logging
from pathlib import Path
import sys
import io
import random, string
import asyncio
import time
import datetime
from PIL import Image, ImageFilter, ImageChops

from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws.async_remote import SamsungTVWSAsyncRemote
from samsungtvws.remote import SendRemoteKey
from samsungtvws import __version__

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
        
    def get_suffix(self, filename):
        '''
        get suffix without '.' or ''
        '''
        return filename.suffix[1:].lower()
        
    def get_last_updated(self, filename):
        '''
        get last updated timestamp for file
        '''
        #return Path(self.folder, filename).stat().st_mtime
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
        if text:
            return text.replace('\n', '<br>')
            
    def get_mime_type(self, filename):
        '''
        return mime type
        '''
        match filename.suffix:
            case '.jpg':
                mime_type='image/jpeg'
            case '.jpeg':
                mime_type='image/jpeg'
            case '.png':
                mime_type='image/png'
            case '.bmp':
                mime_type='image/bmp'
            case '.tif':
                mime_type='image/tiff'
            case _:
                mime_type='image/jpeg'
        return mime_type
                
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
        img1 = Image.open(io.BytesIO(my_data))
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
        use PIL if available to check
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
        check file type if we have PIL
        '''
        if file_type:
            org = file_type
            file_type = Image.open(filename).format.lower() if not image_data else image_data.format.lower()
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
        only used if PIL is installed
        '''
        files = self.get_folder_files(True)
        self.log.info('loading files: {}'.format(self.format_files(files)))
        files_images = self.get_files_dict(files)
        self.log.info('loaded: {}'.format(self.format_files(files_images.keys())))
        return files_images
        
    def get_files_dict(self, files):
        '''
        makes a dictionary of filename and file binary data
        warns if file type given by extension is wrong
        only used if PIL is installed
        '''
        files_images = {}
        for file in files:
            try:
                data = Image.open(file)
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
             
class TVInterface(helpers):
    
    def __init__(self, ip, token_file='./token_file.txt', folder='./images', art_mode=False):
        self.log = logging.getLogger('Main.'+__class__.__name__)
        self.debug = self.log.getEffectiveLevel() <= logging.DEBUG
        super().__init__(Path(folder))
        self.ip = ip
        # Autosave token to file
        self.token_file = Path(token_file) if token_file else token_file
        self.art_mode = art_mode
        self.folder = Path(folder)
        self.art_task = None
        self.api_version = 0
        self.exit = False
        self.lock = asyncio.Lock()
        self.tv = SamsungTVAsyncArt(host=self.ip, port=8002, token_file=self.token_file)
            
    async def connect(self):
        await self.tv.start_listening()
        self.log.info('Started')
        if self.art_mode:
            self.art_task = asyncio.create_task(self.ensure_artmode())
        
    async def close(self):
        '''
        exit any running programs or tasks
        '''
        self.log.info('EXIT received, exiting, please wait for tasks to complete...')
        helpers.exit = True
        self.exit = True
        if self.art_task:
            self.art_task.cancel()
        await self.tv.close()
        #raise SystemExit('cancelled')
            
    def tv_is_alive(self):
        return self.tv.is_alive()
            
    async def tv_on(self):
        return await self.tv.on()
        
    async def get_api_version(self):
        '''
        checks api version to see if it's old (<2021) or new type
        sets api_version to 0 for old, and 1 for new
        '''
        api_version = await self.tv.get_api_version()
        self.log.info('API version: {}'.format(api_version))
        self.api_version = 0 if int(api_version.replace('.','')) < 4000 else 1
        
    async def check_matte(self, matte):
        '''
        checks if the matte passed for uploads to use is valid type and color
        '''
        if matte != 'none':
            org_matte = matte
            matte = matte.split('_')
            try:
                mattes = await self.tv.get_matte_list(True)
                matte_types, matte_colors = ([m['matte_type'] for m in mattes[0]], [m['color'] for m in mattes[1]])
                if matte[0] in matte_types and matte[1] in matte_colors:
                    self.log.info('using matte: {}'.format(org_matte))
                    return org_matte
                else:
                    self.log.info('Valid mattes types: {} and colors: {}'.format(matte_types, matte_colors))
                self.log.warning('Invalid matte selected: {}. A valid matte would be shadowbox_polar for eample, using none'.format(org_matte))
            except AssertionError:
                self.log.warning('Error getting mattes list, setting to none'.format(e))
            return 'none'
        
    async def get_tv_content(self, category='MY-C0002'):
        '''
        gets content_id list of category - either My Photos (MY-C0002) or Favourites (MY-C0004) from tv
        '''
        try:
            async with self.lock:
                result = [v['content_id'] for v in await self.tv.available(category, timeout=10)]
        except AssertionError:
            self.log.warning('failed to get contents from TV')
            result = None
        return result
        
    async def get_thumbnails(self, content_ids):
        '''
        gets thumbnails from tv in list of content_ids
        returns dictionary of content_ids and binary data
        only used if PIL is installed
        '''
        thumbnails = {}
        if content_ids:
            async with self.lock:
                if self.api_version == 0:
                    thumbnails = {content_id:await self.tv.get_thumbnail(content_id) for content_id in content_ids}
                elif self.api_version == 1:
                    thumbnails = {k.split('.')[0]:v for k,v in (await self.tv.get_thumbnail_list(content_ids)).items()}
        self.log.info('got {} thumbnails'.format(len(thumbnails)))
        return thumbnails
        
    async def get_current_artwork(self):
        '''
        reads currently displayed art content_id from tv
        '''
        try:
            content_id = (await self.tv.get_current()).get('content_id')
        except Exception:
            content_id = None
        return content_id
            
    async def delete_files_from_tv(self, content_ids):
        '''
        remove files from tv if tv is in art mode
        '''
        try:
            if self.tv.art_mode:
                async with self.lock:
                    self.log.info('removing files from tv : {}'.format(content_ids))
                    await self.tv.delete_list(content_ids)
                return True
        except Exception as e:
            self.log.error(e)
        return False
        
    async def upload_files_to_tv(self, filenames, matte='none'):
        '''
        upload files in list to tv with selected matte
        return dictionary of uploaded files, and list of files that failed to upload
        '''
        uploaded_files = {}
        missing_files = []
        for filename in filenames:
            file_data, file_type = self.read_file(filename)
            if file_data and self.tv.art_mode:
                self.log.info('uploading : {} to tv'.format(filename.name))
                async with self.lock:
                    content_id = await self.tv.upload(file_data, file_type=file_type, matte=matte, portrait_matte=matte, timeout=30)
                    if content_id:
                        uploaded_files = self.update_uploaded_files(filename, content_id, uploaded_files)
                        self.log.info('uploaded : {} to tv as {}'.format(filename.name, content_id))
                    else:
                        missing_files.append(filename.name)
                        self.log.warning('file: {} failed to upload'.format(filename.name))
        return uploaded_files, missing_files
            
    async def select_image(self, content_id):
        '''
        select image to display on TV from content_id
        '''
        try:
            async with self.lock:
                self.log.info('selecting tv art: content_id: {}'.format(content_id))
                await self.tv.select_image(content_id)
            return content_id
        except Exception as e:
            self.log.error(e)
        return None
        
    async def tv_in_artmode(self):
        '''
        is TV on, and in art mode
        '''
        try:
            async with self.lock:
                if not self.exit:
                    return await self.tv.in_artmode()
        except AssertionError as e:
            self.log.warning('AssertionError error: {} returning: {}'.format(e, self.tv.art_mode))
        return self.tv.art_mode
        
    async def compare_thumbnails_with_files(self):
        '''
        initialize uploaded_files using PIL
        compares the file data with thumbnails to find the content_id and write to uploaded_files
        if it doesn't already exist
        '''
        self.log.info('Checking uploaded files list using PIL')
        files_images = self.load_files()
        if files_images:
            self.log.info('getting My Photos list')
            my_photos = await self.get_tv_content('MY-C0002')
            if my_photos is not None and len(my_photos) > 0:
                return await self.check_thumbnails(files_images, my_photos)
            else:
                self.log.info('no photos found on tv')
        return None
        
    async def check_thumbnails(self, files_images, my_photos):
        '''
        download thumbnails from my_photos to compare with file data
        save any updates
        '''
        self.log.info('downloading My Photos thumbnails, please wait...')
        my_photos_thumbnails = await self.get_thumbnails(my_photos)
        if my_photos_thumbnails:
            self.log.info('checking thumbnails against {} files, please wait...'.format(len(files_images)))
            return self.compare_thumbnails(files_images, my_photos_thumbnails)
        else:
            self.log.info('failed to get thumbnails')
        return None
            
    def compare_thumbnails(self, files_images, my_photos_thumbnails):
        '''
        compare file data with thumbnails to find a match, and update update_uploaded_files
        '''
        uploaded_files = {}
        for k, (filename, file_data) in enumerate(files_images.items()):
            for i, (my_content_id, my_data) in enumerate(my_photos_thumbnails.items()):
                self.log_progress(len(files_images)*len(my_photos_thumbnails), k*len(files_images)+i)
                self.log.debug('checking: {} against {}, thumbnail: {} bytes'.format(filename.name, my_content_id, len(my_data)))
                equal, diff =  self.are_images_equal(my_data, file_data)
                if equal:
                    self.log.info('found uploaded file: {} as {} diff: {}'.format(filename.name, my_content_id, round(diff, 2)))
                    uploaded_files = self.update_uploaded_files(filename, my_content_id, uploaded_files)
                    break
            if self.exit:
                break
        return uploaded_files
        
    async def ensure_artmode(self):
        '''
        Keep TV in art_mode, (ie not playing) unless TV is off
        '''
        self.log.info('ensure art_mode enabled')
        self.tv_remote = SamsungTVWSAsyncRemote(host=self.ip, port=8002, token_file=self.token_file)
        while not self.exit:
            try:
                async with self.lock:
                    if await self.tv.on():
                        if await self.tv.get_artmode() != 'on':
                            #send KEY_POWER
                            self.log.warning('TV is playing, sending KEY_POWER')
                            await self.tv_remote.send_command(SendRemoteKey.click("KEY_POWER"))
            except AssertionError as e:
                self.log.warning('AssertionError')
            await self.wait_seconds(15)
        await self.tv_remote.close()

            
async def main():
    global log
    log = logging.getLogger('Main')
    log.info('This is a library for the web_interface, please run that instead')

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit()