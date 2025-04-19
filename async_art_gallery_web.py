#!/usr/bin/env python3
# fully async library to monitor a folder and upload/display on Frame TV using a web page for control
# do not run it directly, use web_interface.py instead

'''
This program will read the files in a designated folder (with allowed extensions) and upload them to your TV. It keeps track of which files correspond to what
content_id on your TV by saving the data in a file called uploaded_files.json. it also keeps track of when the selected artwork was last changed.

It monitors the folder for changes every check seconds (5 by default), new files are uploaded to the TV, removed files are deleted from the TV, and if a file
is changed, the old content is removed from the TV and the new content uploaded to the TV. Content is only changed if the TV is in art mode.

if check is set to 0 seconds, the program will run once and exit. You can then run it periodically (say with a cron job).

if there is more than one file in the folder, the current artword displayed is changed every update minutes (0) by default (which means do not select any artwork),
otherwise the single file in the folder is selected to be displayed. this also only happens when the TV is in art mode.

PIL is required for the initial syncronization, the first time the program is run.

If the on (-O) option is selected, the program wil exit if the TV is not on (TV or art mode).
If the sequential (-S) option is selected, then the slideshow is sequential, not random (random is the default)
The default checking period is 60 seconds or the update period whichever is less.

It is a library used by the web_interface.py program
'''

import logging
import json
import asyncio
import time

from tv_interface import TVInterface

logging.basicConfig(level=logging.INFO)
             
class monitor_and_display(TVInterface):
        
    def __init__(self, ip, folder, period=5, update_time=1440, display_for=120, include_fav=False, sync=True, matte='none', sequential=False, on=False, token_file=None, art_mode=False):
        self.log = logging.getLogger('Main.'+__class__.__name__)
        self.debug = self.log.getEffectiveLevel() <= logging.DEBUG
        super().__init__(ip, token_file, folder, art_mode)
        self.folder = folder
        self.update_time = int(max(0, update_time*60))   #convert minutes to seconds
        self.period = min(max(5, period), self.update_time, display_for) if self.update_time > 0 else period
        self.display_for = display_for
        self.include_fav = include_fav
        self.sync = sync
        self.matte = matte
        self.sequential = sequential
        self.on = on
        self.program_data_path = self.get_Path('./uploaded_files.json')
        self.uploaded_files = {}
        self.fav = set()
        self.timing = {}
        self.current_content_id = None
        self.prev_filename = None
        self.updated = True
        self.exit = False
        self.modified_files = set()
        
    async def start_monitoring(self):
        '''
        program entry point
        '''
        if self.on and not await self.tv_on():
            self.log.info('TV is off, exiting')
        else:
            self.log.info('Start Monitoring')
            try:
                await self.connect()
            except Exception as e:
                self.log.error('failed to connect with TV: {}'.format(e))
            if self.tv_is_alive():
                self.matte = await self.check_matte(self.matte)
                await self.select_artwork()
        await self.close_tv_connection()
        self.exit = True
        self.log.info('exited')
            
    async def initialize(self):
        '''
        initializes program
        gets API version, and current displayed art content_id
        uses PIL to try to match files in folder with content_id on tv.
        this matching is not really needed if uploaded_files (loaded from file) is accurate,
        and can be skipped by setting sync (-s) to False
        '''
        await self.get_api_version()
        self.current_content_id = await self.get_current_artwork()
        self.log.info('Current artwork is: {}'.format(self.current_content_id))
        self.load_program_data()
        self.log.info('files in directory: {}: {}'.format(self.folder, self.get_folder_files()))
        if self.sync:
            await self.initialize_pil()
        else:
            self.log.warning('syncing disabled, not updating uploaded files list')
            
    def check_time(self, start, duration=None, initial_value=None):
        '''
        return remaining time before timer expires if greater than 0, check with duration == None
        or reset timer if duration has value, optionally set initial start value
        '''
        if not self.timing.get(start):
           self.timing[start] = {'start': time.time(), 'duration': 0} 
        if duration is not None:    #restart timer for duration
            self.timing[start]['start'] = time.time()
            self.timing[start]['duration'] = duration
        if initial_value is not None:
           self.timing[start]['start'] = initial_value
        remaining = self.timing[start]['duration'] - (time.time() - self.timing[start]['start'])
        self.log.debug('{}: next update in: {}'.format(start, round(remaining, 2)))
        return remaining if remaining > 0 else 0
        
    async def sync_file_list(self):
        '''
        if art has been deleted on tv, resyncronises uploaded_files with tv
        '''
        my_photos = await self.get_tv_content('MY-C0002')
        if my_photos is not None:
            self.log.info('Syncing uploaded_files with TV')
            self.uploaded_files = {k:v for k,v in self.uploaded_files.items() if v['content_id'] in my_photos}
            self.write_program_data()
   
    def load_program_data(self):
        '''
        load previous settings on program start update
        '''
        if self.program_data_path.is_file():
            program_data = json.loads(self.program_data_path.read_text())
            self.uploaded_files = program_data.get('uploaded_files', program_data)
            self.check_time('start', self.update_time, program_data.get('last_update', time.time()))
        else:
            self.log.warning('no uploaded files list found')
            self.uploaded_files = {}
            self.check_time('start', self.update_time)
        
    def write_program_data(self):
        '''
        save current settings, including file list with content_id on tv and last updated time
        also save the last time that art was updated, for timing slideshows
        '''
        
        program_data = {'last_update': self.timing.get('start', {}).get('start'), 'uploaded_files': self.uploaded_files}
        self.program_data_path.write_text(json.dumps(program_data, indent=2))
        
    async def upload_files(self, filenames):
        '''
        upload files in list to tv
        '''
        uploaded_files, missing_files = await self.upload_files_to_tv(filenames, self.matte)
        [self.uploaded_files.pop(filename) for filename in missing_files]
        self.uploaded_files.update(uploaded_files)
        self.write_program_data()
        
    async def remove_files(self, files):
        '''
        if files deleted, remove them from tv
        '''
        content_ids_removed = [v['content_id'] for k, v in self.uploaded_files.items() if k not in [f.name for f in files]]
        #delete images from tv
        if content_ids_removed:
            if await self.delete_files_from_tv(content_ids_removed):
                await self.sync_file_list()
            return True
        return False
            
    async def add_files(self, files):
        '''
        if new files found, upload to tv
        '''
        new_files = [f for f in files if f.name not in self.uploaded_files.keys()]
        self.modified_files.update(new_files)
        #upload new files
        if new_files:
            self.log.info('adding files to tv : {}'.format(self.format_files(new_files)))
            await self.wait_for_files(new_files)
            await self.upload_files(new_files)
            return True
        return False
            
    async def update_files(self, files):
        '''
        check if files were modified
        if so, delete old content on tv and upload new
        '''
        modified_files = [f for f in files if f.name in self.uploaded_files.keys() and self.uploaded_files[f.name].get('modified') != self.get_last_updated(f)]
        self.modified_files.update(modified_files)
        #delete old file and upload new:
        if modified_files:
            self.log.info('updating files on tv : {}'.format(self.format_files(modified_files)))
            await self.wait_for_files(modified_files)
            files_to_delete = [v['content_id'] for k, v in self.uploaded_files.items() if k in [f.name for f in modified_files]]
            if files_to_delete and await self.delete_files_from_tv(files_to_delete):
                await self.sync_file_list()
            await self.upload_files(modified_files)
            return True
        return False
        
    def get_modified_files(self):
        '''
        return copy of modified files and delete orgiginal
        '''
        modified_files = self.modified_files.copy()
        self.modified_files = set()
        self.log.debug('returning modified files: {}'.format(modified_files))
        return modified_files
            
    async def update_art_timer(self):
        '''
        changes art on tv as part of slideshow if enabled
        updates favourites list if favourites are included in slideshow
        '''
        if self.update_time > 0 and (len(self.uploaded_files.keys()) > 1 or self.include_fav):
            if not self.check_time('start'):                       #if timer expired
                self.log.info('doing slideshow update, after {}'.format(self.get_time(self.update_time)))
                self.check_time('start', self.update_time)         #reset timer
                self.write_program_data()
                if self.include_fav:
                    self.log.info('updating favourites')
                    fav = await self.get_tv_content('MY-C0004')
                    self.fav = set(fav) if fav is not None else self.fav
                await self.change_art()
            else:
                self.log.info('next {} update in {}'.format('sequential' if self.sequential else 'random', self.get_time(self.check_time('start'))))
                
    def get_content_ids(self):
        '''
        return list of all content ids available for selecting to display NOTE sets() are not ordered
        if not including favourites, order list by filename in self.uploaded_files
        '''
        if self.fav:
            return list({v['content_id'] for v in self.uploaded_files.values()}.union(self.fav))
        return [v['content_id'] for k, v in sorted(self.uploaded_files.items())]
        
    def get_next_art(self):
        '''
        get next content_id from list (excluding current content id), set current_content_id or return None if no list
        '''
        content_ids = [id for id in self.get_content_ids() if id != self.current_content_id]
        if content_ids:
            content_id = self.next_value(self.current_content_id, self.get_content_ids()) if self.sequential else self.random_choice(content_ids)
            return content_id
        return None
        
    async def change_art(self, new_content_id=None):
        '''
        update displayed art on tv, if next_art is a different content_id to current
        '''
        content_id = new_content_id or self.get_next_art()
        if content_id and content_id != self.current_content_id:
            await self.select_image(content_id)
            self.current_content_id = content_id
        else:
            self.log.info('skipping art update, as new content_id: {} is the same as currently shown'.format(content_id))
            
    async def set_image_from_filename(self, filename):
        '''
        set image on TV from filename, and pause auto rotation
        '''
        try:
            content_id = self.uploaded_files[filename]['content_id']
            self.check_time('skip', self.display_for)   #reset timer
            self.check_time('start', initial_value=0)   #disable timer
            await self.change_art(content_id)
        except Exception as e:
            self.log.warning('error: {}, file: {}'.format(e, filename))
        
    async def filename_changed(self):
        '''
        async generator that yields changed filename or 'off' if tv is not in art mode
        self.updated is intiially True
        '''
        while not self.exit:
            self.log.debug('checking art mode')
            art_mode = await self.tv_in_artmode()
            if self.updated:
                self.updated = False
                self.prev_filename = None
                yield 'refresh'
            for filename, value in self.uploaded_files.items():
                if value['content_id'] == self.current_content_id:
                    filename = filename if art_mode else 'off'
                    if filename != self.prev_filename:
                        self.prev_filename = filename
                        self.log.info('returning: {}'.format(filename))
                        yield filename
                        break
            await self.wait_seconds(1)
        yield 'off'
    
    async def check_dir(self):
        '''
        scan folder for new, deleted or updated files, but only when tv is in art mode
        '''
        try:
            if await self.tv_in_artmode():
                self.log.info('checking directory: {}{}'.format(self.folder, ' every {}'.format(self.get_time(self.period)) if self.period else ''))
                files = self.get_folder_files(True)
                await self.sync_file_list()
                self.updated = any([
                    await self.remove_files(files),
                    await self.add_files(files),
                    await self.update_files(files),
                ])
                # if art manually selected timer expired, auto update, else skip
                if not self.check_time('skip'):
                    await self.update_art_timer()
                    if len(self.get_content_ids()) == 1:
                        await self.change_art()
            else:
                self.log.info('artmode or tv is off')
        except Exception as e:
            self.log.warning("error in check_dir: {}".format(e))

    async def select_artwork(self):
        '''
        main loop
        initialize, check directory for changed files and update
        '''
        await self.initialize()
        while not self.exit:
            await self.check_dir()
            if self.period == 0:
                break
            await self.wait_seconds(min(self.period, *[self.check_time(t) for t in self.timing.keys() if self.check_time(t) > 0] or [self.period]))
        
    async def initialize_pil(self):
        '''
        initialize uploaded_files.json using PIL
        compares the file data with thumbnails to find the content_id and write to uploaded_files.json
        if it doesn't already exist
        '''
        uploaded_files = await self.compare_thumbnails_with_files()
        if uploaded_files:
            self.uploaded_files.update(uploaded_files)
            self.write_program_data()
        else:
            self.log.info('no files, using origional uploaded files list')

            
async def main():
    global log
    log = logging.getLogger('Main')
    log.info('This is a library for the web_interface, please run that instead')

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass