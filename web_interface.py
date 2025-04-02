#!/usr/bin/env python3
# web frontend for gallery display
# please install flask with the async option (pip install flask[async])
# please install quart (pip install quart)
# please install quart_flask_patch (pip install quart_flask_patch)
# and bootstrap-flask (pip install Bootstrap-Flask)
# V 1.0.0 14/3/25 NW Initial release
# V 1.0.1 15/3/25 NW Added |safe filter in modal Marco for description and details
# V 1.1.1 18/3/25 NW updated to load modal dialog on demand
# V 1.2.0 19/3/25 NW switched from flask to quart for async features, refactor as class
# V 2.0.0 28/3/25 NW New version with seperate caption display

import quart_flask_patch
import asyncio
from quart import Quart, render_template, make_response, current_app, websocket
from flask_bootstrap import Bootstrap5
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse, os
import logging
from signal import SIGTERM, SIGINT
from hypercorn.config import Config
from hypercorn.asyncio import serve

from async_art_gallery_web import monitor_and_display
from exif_data import ExifData

__version__ = '2.0.0'

logging.basicConfig(level=logging.INFO)

def parseargs():
    # Add command line argument parsing
    parser = argparse.ArgumentParser(description='Async Art gallery for Samsung Frame TV Version: {}'.format(__version__))
    parser.add_argument('ip', action="store", type=str, default=None, help='ip address of TV (default: %(default)s))')
    parser.add_argument('-p','--port', action="store", type=int, default=5000, help='port for web page interface (default: %(default)s))')
    parser.add_argument('-f','--folder', action="store", type=str, default="./images", help='folder to load images from (default: %(default)s))')
    parser.add_argument('-m','--matte', action="store", type=str, default="none", help='default matte to use (default: %(default)s))')
    parser.add_argument('-t','--token_file', action="store", type=str, default="token_file.txt", help='default token file to use (default: %(default)s))')
    parser.add_argument('-u','--update', action="store", type=float, default=0, help='slideshow update period (mins) 0=off (default: %(default)s))')
    parser.add_argument('-c','--check', action="store", type=int, default=600, help='how often to check for new art 0=run once (default: %(default)s))')
    parser.add_argument('-d','--display_for', action="store", type=int, default=120, help='how long to display manually selected art for (default: %(default)s))')
    parser.add_argument('-mo','--modal', default='', choices=['modal-sm', 'modal-lg', 'modal-xl', 'modal-fullscreen', 'modal-fullscreen-sm-down',
                                                              'modal-fullscreen-md-down', 'modal-fullscreen-lg-down', 'modal-fullscreen-xl-down', 'modal-fullscreen-xxl-down'],
                                         help='size of modal text box see https://www.w3schools.com/bootstrap5/bootstrap_modal.php for explanation (default: medium)')
    parser.add_argument('-th','--theme', default=None, choices=[None, 'cerulian', 'cosmo', 'cyborg', 'darkly', 'flatly', 'journal', 'litera', 'lumen', 'lux', 'materia', 'minty',
                                                                'morph', 'pulse', 'quartz', 'sandstone', 'simplex', 'sketchy', 'slate', 'solar', 'spacelab', 'suerhero',
                                                                'united', 'vapour', 'yeti', 'zephyr', 'dark'],
                                         help='theme to apply to display (default: %(default)s))')
    parser.add_argument('-ph','--photographer', action="store", type=str, default="Paul Thompsen", help='default photographer to use (default: %(default)s))')
    parser.add_argument('-sf','--serif_font', action='store_true', default=False, help='use Serif Font for caption display (default: %(default)s))')
    parser.add_argument('-s','--sync', action='store_false', default=True, help='automatically syncronize (needs Pil library) (default: %(default)s))')
    parser.add_argument('-K','--kiosk', action='store_true', default=False, help='Show in Kiosk mode (default: %(default)s))')
    parser.add_argument('-P','--production', action='store_true', default=False, help='Run in Production server mode (default: %(default)s))')
    parser.add_argument('-A','--art_mode', action='store_true', default=False, help='Ensure TV stays in art mode (except when off) (default: %(default)s))')
    parser.add_argument('-S','--sequential', action='store_true', default=False, help='sequential slide show (default: %(default)s))')
    parser.add_argument('-O','--on', action='store_true', default=False, help='exit if TV is off (default: %(default)s))')
    parser.add_argument('-F','--favourite', action='store_true', default=False, help='include favourites in rotation (default: %(default)s))')
    parser.add_argument('-X','--exif', action='store_false', default=True, help='Use Exif data (default: %(default)s))')
    parser.add_argument('-D','--debug', action='store_true', default=False, help='Debug mode (default: %(default)s))')
    return parser.parse_args()

class WebServer(monitor_and_display):
    
    macro = {'modal': 'render_modal', 'caption': 'render_caption'}
    
    def __init__(self, ip,
                       folder,
                       period=5,
                       update_time=1440,
                       display_for=120,
                       include_fav=False,
                       sync=True,
                       matte='none',
                       sequential=False,
                       on=False,
                       token_file=None,
                       art_mode = False,
                       port=5000,
                       modal_size = '',
                       photographer = None,
                       theme = None,
                       serif_font = False,
                       exif = True,
                       kiosk=False):
        super().__init__(   ip,
                            folder,
                            period          = period,
                            update_time     = update_time,
                            display_for     = display_for,
                            include_fav     = include_fav,
                            sync            = sync,
                            matte           = matte,
                            sequential      = sequential,
                            on              = on,
                            token_file      = token_file,
                            art_mode        = art_mode)
        self.log = logging.getLogger('Main.'+__class__.__name__)
        self.debug = self.log.getEffectiveLevel() <= logging.DEBUG
        self.host = '0.0.0.0'   #allow connection from any computer
        self.port = port
        self.modal_size = modal_size
        self.photographer = photographer
        self.theme = theme
        self.serif_font = serif_font
        self.kiosk = kiosk
        self.connected = set()
        self.exit = False
        self.text = {}
        self.screens = []
        self.add_signals()
        self.exif = ExifData(folder if exif else None, ip)
        self.app = Quart(__name__, static_folder=folder)
        self.bootstrap = Bootstrap5(self.app)
        if self.theme != 'dark':    #dark is not an actual theme, but a manual setting
            self.app.config['BOOTSTRAP_BOOTSWATCH_THEME'] = self.theme
        self.app.add_url_rule('/','show_thumbnails', self.show_thumbnails)
        self.app.add_url_rule('/caption','show_caption', self.show_caption)
        self.app.add_websocket('/ws', 'ws', self.ws)
        
    async def initialize_screens(self):
        '''
        initiialize caption and display screens if present
        '''
        self.screens = await self.get_connected_screens_status()
        if len(self.screens) >= 1:
            self.log.info('Starting Caption Screen')
            asyncio.create_task(self.start_browser_with_delay(app='http://localhost:5000/caption', pos='0,0', kiosk=True))  #caption display
        if len(self.screens) >= 2:
            self.log.info('Starting Display Screen')
            asyncio.create_task(self.start_browser_with_delay(app='http://localhost:5000/', pos='1420,0'))                  #buttons display
        
    async def serve_forever(self, production=False):
        '''
        start everything up in either development or production environment
        '''
        asyncio.create_task(self.shutdown_trigger())
        await self.initialize_screens()
        if production:
            self.log.info('PRODUCTION Mode')
            config = Config()
            config.bind = '{}:{}'.format(self.host, self.port)
            config.loglevel = 'DEBUG' if self.debug else 'INFO'
            asyncio.create_task(self.start_monitoring())
            await serve(self.app, config, shutdown_trigger=self.shutdown_trigger)
        else:
            self.log.info('DEVELOPMENT Mode')
            await asyncio.gather(self.run(), self.start_monitoring(), return_exceptions=True)
    
    async def run(self):
        '''
        run web server as task
        '''
        self.log.info('Serving files from: {}'.format(self.app.static_folder))
        await self.app.run_task(host=self.host, port=self.port, debug=self.debug,  shutdown_trigger=self.shutdown_trigger)
        
    def close(self):
        '''
        exit server
        '''
        self.log.info('SIGINT/SIGTERM received, exiting')
        self.exit=True
        super().close()
        
    def add_signals(self):
        '''
        setup signals to exit program
        '''
        try:    #might not work on windows
            asyncio.get_running_loop().add_signal_handler(SIGINT, self.close)
            asyncio.get_running_loop().add_signal_handler(SIGTERM, self.close)
        except Exception:
            self.log.warning('signal error')
            
    async def shutdown_trigger(self):
        '''
        just loop until self.exit is set
        This should trigger the server shutdown
        '''
        while not self.exit:
            await asyncio.sleep(1)
        self.log.info('shutdown initiated')

    async def get_template_attribute(self, template, attibute):
        '''
        kludge to replicate get_template_attribute, as async function
        '''
        return getattr(await current_app.jinja_env.get_template(template)._get_default_module_async(), attibute)
        
    async def sending(self):
        '''
        websocket send - update web page with displayed filename on TV
        '''
        self.log.info('websocket sending started')
        await self.broadcast_tv_filename()  
        self.log.warning('websocket sending ended')

    async def receiving(self):
        '''
        websocket receive requests from web page
        '''
        self.log.info('websocket receiving started')
        while not self.exit:
            data = await websocket.receive_json()
            await self.ws_process(data)      
        self.log.warning('websocket receiving ended')
        
    async def broadcast_tv_filename(self):
        '''
        broadcast filename changes to all websockets connected
        '''
        data={'type':'update'}
        filename = self.filename_changed()           #filename generator
        while not self.exit:
            #stream filename changes on TV to web page
            data['name'] = await anext(filename)        #blocks until next filename is available
            for screen in self.screens:
                await self.caption_screen_control(data['name']!='off', screen=screen.split(' ')[0])
            for websoc in self.connected:
                self.log.info('WS({}): will be skipping: {}'.format(websoc.id, websoc.skip))
                if data['name'] in websoc.skip:         #skip if image was previously requested, as modal is already displayed
                    self.log.info('WS({}): Not sending {} as image was previously selected'.format(websoc.id, data['name']))
                    websoc.skip.discard(data['name'])
                    continue
                await self.ws_send(data, websoc)
        
    async def ws_process(self, data):
        '''
        process and respond to websocket data
        '''
        websoc = self.get_ws()
        self.log.info('WS({}): received from ws: {}'.format(websoc.id, data))
        #Python 3.10 onwards only!
        match data['type']:
            case 'modal':
                #send modal window html rendered from jinga template
                send_data = await self.get_window_data(data['name'], type='modal')
                await self.ws_send(send_data)
            
            case 'caption':
                #send caption window html rendered from jinga template
                send_data = await self.get_window_data(data['name'], type='caption')
                await self.ws_send(send_data)
                
            case'display':
                #display file on TV
                self.log.info('show image: {}'.format(data['name']))
                websoc.skip.add(data['name'])
                await self.set_image_from_filename(data['name'])
                
            case 'refresh':
                #refresh current displayed file - called on websocket first connect
                name = await self.get_current_filename(True)
                self.log.info('got current image as: {}'.format(name))
                await self.ws_send({'type':'update',
                                    'name': name})

            case _:
                self.log.info('No match for data type: {]'.format(data['type']))
                
    async def get_window_data(self, name, type='modal'):
        text = self.get_text(name, type=type)
        send_data = {'type':type, 'name': 'none'}
        if text:
            window = await self.get_template_attribute('macros.html', self.macro[type])
            send_data['data'] = await window(text, self.modal_size)
            send_data['name'] = name
        return send_data
        
    async def ws_send(self, data, websoc=None):
        '''
        send json to websocket
        '''
        ws = websoc or self.get_ws()
        if not self.debug:
            self.log.info('WS({}): sending: type: {}, name: {}'.format(ws.id, data.get('type'), data.get('name', data)))
        self.log.debug('WS({}): sending: {}'.format(ws.id, data))
        await ws.send_json(data)
            
    def get_ws(self):
        '''
        get current websocket object
        '''
        return websocket._get_current_object()

    async def ws(self):
        '''
        start websocket
        '''
        try:
            websoc = self.get_ws()
            self.connected.add(websoc)
            websoc.skip = set()
            websoc.id = len(self.connected)
            self.log.info('{} websocket connected'.format(len(self.connected)))
            await self.ws_process({'type': 'refresh'})  #send 'refresh' to update display on first connection
            producer = asyncio.create_task(self.sending())
            consumer = asyncio.create_task(self.receiving())
            await asyncio.gather(producer, consumer)
        except asyncio.exceptions.CancelledError:
            self.log.info('WS({}): websocket cancelled'.format(websoc.id))
        except Exception as e:
            self.log.exception(e)
        finally:
            self.log.info('WS({}): cancelling websocket tasks'.format(websoc.id))
            try:
                consumer.cancel()
                producer.cancel()
            except Exception:
                pass
            self.connected.discard(websoc)
        self.log.warning('WS({}): websocket closed'.format(websoc.id))
        
    async def show_caption(self):
        '''
        show caption screen
        '''
        self.log.info('loading caption page')
        return await render_template('caption.html', serif_font=self.serif_font, theme=self.theme)

    async def show_thumbnails(self):
        '''
        construct thumbnail page from files in static folder
        '''
        self.log.info('loading thumnail page')
        image_names = self.get_folder_files()
        self.exif.get_files(image_names)
        self.log.info('displaying Buttons for: {}'.format(image_names))
        return await render_template('home.html', names=image_names, kiosk=str(self.kiosk).lower())
        
    async def get_connected_screens_status(self, screen=None):
        '''
        detect attached screens if screen is None, or
        return True if defined screen is on
        uses wlr-randr
        alternative:
        kmsprint:
        Connector 0 (33) HDMI-A-1 (disconnected)
          Encoder 0 (32) TMDS
        Connector 1 (42) HDMI-A-2 (disconnected)
          Encoder 1 (41) TMDS
          
        or
        
        Connector 0 (33) HDMI-A-1 (connected)
          Encoder 0 (32) TMDS
            Crtc 2 (92) 320x1480@59.32 48.000 320/100/10/90/- 1480/60/10/6/- 59 (59.32) P|U|D
              Plane 2 (81) fb-id: 679 (crtcs: 2) 0,0 320x1480 -> 0,0 320x1480 (XR24 AR24 AB24 XB24 RG16 BG16 AR15 XR15 RG24 BG24 YU16 YV16 YU24 YV24 YU12 YV12 NV12 NV21 NV16 NV61 P030 XR30 AR30 AB30 XB30 RGB8 BGR8 XR12 AR12 XB12 AB12 BX12 BA12 RX12 RA12)
                FB 679 320x1480 XR24
        Connector 1 (42) HDMI-A-2 (disconnected)
          Encoder 1 (41) TMDS
        '''
        screens = []
        is_on = False
        proc = await asyncio.create_subprocess_exec('wlr-randr', stdout=asyncio.subprocess.PIPE)
        # Read output and process line by line
        data = await proc.stdout.read()
        lines = data.decode().split('\n') if data else []
        for i, line in enumerate(lines):
            if screen:
                if screen in line:  #Find HDMI-A-1 "HOT WaveShsare 0x00000001 (HDMI-A-1)"
                    is_on = 'yes' in lines[min(len(lines)-1, i+1)] #check if Enabled: yes 
                    break
            else:
                if 'HDMI-A' in line:
                   screens.append(line)
                   self.log.info('found attached screen: {}'.format(line))
        await proc.wait()
        return is_on if screen else screens
        
    async def caption_screen_control(self, on=True, screen='HDMI-A-1'):
        '''
        Turn caption screen on or off using:
        wlr-randr --output HDMI-A-1 --off or --on
        check to see if screen is on first if turning on as screen flickers sending --on again, if already on.
        '''
        if any([s for s in self.screens if screen in s]):   #if our screen is one of the detected screens
            is_on = await self.get_connected_screens_status(screen) if on else False
            if (on and not is_on) or not on:
                proc = await asyncio.create_subprocess_exec('wlr-randr', '--output', screen, '--on' if on else '--off')
                # Wait for the subprocess exit.
                await proc.wait()
        
    async def start_browser_with_delay(self, app, pos, kiosk, delay=1):
        '''
        start browser on display after delay - call as task
        '''
        await asyncio.sleep(delay)
        await self.start_browser_on_display(app, pos, kiosk)
        
    async def start_browser_on_display(self, app='http://localhost:5000/caption', pos='0,0', kiosk=True):
        '''
        display web page (app) on screen in possition given by pos (x, y) - seconds screen would start at 1420, so 1420,0
        derfaults are for the caption display, second display would be app='http://localhost:5000', pos='1420,0'
        Will not return until browser exits
        '''
        proc = await asyncio.create_subprocess_exec('chromium-browser',
                                                    '--kiosk' if kiosk else '',
                                                    '--noerrdialogs',
                                                    '--disable-infobars',
                                                    '--app={}'.format(app),
                                                    '--start-fullscreen',
                                                    '--window-position={}'.format(pos),
                                                    '--user-data-dir={}'.format(TemporaryDirectory().name),
                                                    '--enable-features=OverlayScrollbar',
                                                    stderr=asyncio.subprocess.DEVNULL)
        # Wait for the subprocess exit.
        await proc.wait()
        
    def get_text(self, file, type='modal'):
        '''
        takes a image file name, changes the extension to TXT (also tries txt).
        if data does not already exist in self.txt and file has not been updated, reads the file from the static folder
        and returns a dictionary of the json.
        returns None if file not found, or json is invalid and data not in the image exif data
        returns caption data or modal data built from the text or exif data
        '''
        #default info
        data = {"id": Path(file).with_suffix(""), "name": file}
        text = {}
        text_file = Path(self.app.static_folder, Path(file).with_suffix(".TXT"))
        if not text_file.is_file():
            text_file = Path(text_file).with_suffix(".txt")
        try:
            ts = self.get_last_updated(text_file)
            if self.text.get(file,{}).get('timestamp') != ts:
                with open(text_file, 'r') as f:
                    text = self.app.json.load(f)
                    text['timestamp'] = ts
                    self.text[file] = text
            else:
                text = self.text.get(file,{})
            self.log.debug('got text for image: {}: {}'.format(file, text))
        except FileNotFoundError:
            pass
        except Exception as e:
            self.log.warning('error: {}: {}'.format(e, text_file))
        #Python 3.10 onwards only!
        match type:
            case 'modal':
                text = self.get_modal_from_exif(file, text)
            case 'caption':
                text = self.get_caption_from_exif(file, text)
        if not text:
            return None
        data.update(text)
        return data
            
    def get_modal_from_exif(self, file, text):
        '''
        fill in modal data from exif data if it exists or default from text file
        modal uses:
        header
        description
        details
        time
        location
        credit
        '''
        modal = {}
        modal['header'] = self.exif.get_title(file, text.get('header') or text.get('description'))
        modal['description'] = self.exif.get_description(file, text.get('description'))
        if modal['header'] and modal['description'] and modal['header'] == modal['description']:
            modal['description'] = None
        if modal['header']:
            modal['details'] = self.html_markup(self.exif.get_user_comment(file, text.get('details')))
            modal['time'] = self.exif.get_date_original(file, text.get('time'))
            modal['location'] = self.exif.get_location(file, text.get('location'))
            modal['credit'] = self.exif.get_credit(file, text.get('credit'))
            return modal
        return None
            
    def get_caption_from_exif(self, file, text):
        '''
        fill in caption data from exif data if it exists or default from text file
        uses exif fields:
        ImageTitle, ImageDescription for caption, if not present, uses 'caption' in text file, or if not present 'header' or 'description' in text file
        GPS address for location, or 'location' in text file if not present
        Photographer or Artist, or 'photographer' in text file, plus month and year from DateTimeOriginal for byline
        Model and FocalLength for camera
        ExposureTime, FNumber (or ApertureValue) and ISOSpeedRatings for settings
        
        caption values are:
        title: 'caption' in text file
        location
        byline
        camera
        settings
        '''
        try:
            caption = {}
            #get values from exif or defaults from text file
            caption['title'] = self.exif.get_title(file, text.get('header') or text.get('description'))
            if caption['title']:
                caption['location'] =  self.exif.get_caption_location(file, text.get('location'))
                caption['byline'] = self.exif.get_byline(file, text.get('photographer', self.photographer))
                caption['camera'] = self.exif.get_camera(file)
                caption['settings'] = self.exif.get_settings(file)
                return caption
        except Exception as e:
            self.log.exception(e)
        return None
        
    def html_markup(self, text):
        if text:
            return text.replace('\n', '<br>')
        
async def main():
    args = parseargs()
    logging.basicConfig(format='%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s',
                        force=True,
                        level=logging.DEBUG if args.debug else logging.INFO)
    log = logging.getLogger('Main')
    log.info('Program Started, version: {}'.format(__version__))
    log.debug('Debug mode')
    
    args.folder = Path(args.folder)
    
    if not os.path.exists(args.folder):
        log.warning('folder {} does not exist, exiting'.format(args.folder))
        os._exit(1)
        
    if args.kiosk:
        log.info("Running in Kiosk mode")
        
    if args.theme:
        log.info('using theme: {}'.format(args.theme))
        
    log.info('using serif font for caption: {}'.format(args.serif_font))
        
    web = WebServer( args.ip,
                     args.folder,
                     period          = args.check,
                     update_time     = args.update,
                     display_for     = args.display_for,
                     include_fav     = args.favourite,
                     sync            = args.sync,
                     matte           = args.matte,
                     sequential      = args.sequential,
                     on              = args.on,
                     token_file      = args.token_file,
                     art_mode        = args.art_mode,
                     port            = args.port,
                     modal_size      = args.modal,
                     photographer    = args.photographer,
                     theme           = args.theme,
                     serif_font      = args.serif_font,
                     exif            = args.exif,
                     kiosk           = args.kiosk)
    
    await web.serve_forever(args.production)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        os._exit(1)    

