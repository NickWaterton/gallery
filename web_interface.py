#!/usr/bin/env python3
# web frontend for gallery display
# please run pip install -r requirements.txt to install the required libraries
# V 1.0.0 14/3/25 NW Initial release
# V 1.0.1 15/3/25 NW Added |safe filter in modal Macro for description and details
# V 1.1.1 18/3/25 NW updated to load modal dialog on demand
# V 1.2.0 19/3/25 NW switched from flask to quart for async features, refactor as class
# V 2.0.0 28/3/25 NW New version with seperate caption display
# V 2.0.1 3/4/25  NW Minor fixes
# V 2.0.2 4/4/25  NW Fix exif loading
# V 2.0.3 7/4/25  NW refactored async_art_gallery_web.py and fixed sequential
# V 2.0.4 12/4/25 NW fixed themes loading, and streamlined updates.
# V 2.0.5 13/4/25 NW major refactoring
# V 2.1.0 14/4/25 NW Added google AI to fill in image details if missing
# V 2.1.1 15/4/25 NW General tidy up
# V 2.2.2 16/4/25 NW Improved startup and shutdown
# V 2.2.3 17/4/25 NW General simplification
# V 2.2.4 18/4/25 NW More General simplification
# V 2.2.5 19/4/25 NW Fixd timing bug and redo websockets
# V 2.2.6 22/5/2025 NW modified uploaded_files.json to store data by ip address (so multiple copies of program can be run), added ability to set caption and display hdmi port
# V 2.2.7 28/5/2025 NW Multiple fixes for Wayland multiple displays, introduction of movemouse.py
# V 2.7.8 30/5/2025 NW Minor display fixes. Add rotation options

import quart_flask_patch
import asyncio
from quart import Quart, render_template, make_response, current_app, websocket
from flask_bootstrap import Bootstrap5
from tempfile import TemporaryDirectory
import argparse, sys
import logging
from signal import SIGTERM, SIGINT
from hypercorn.config import Config
from hypercorn.asyncio import serve

from async_art_gallery_web import monitor_and_display
from exif_data import ExifData
from movemouse import WaylandClient

__version__ = '2.1.8'

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
    parser.add_argument('-ca','--caption_hdmi', action="store", type=int, default=1, choices=[0,1,2], help='caption display HDMI (0=off, default: %(default)s))')
    parser.add_argument('-di','--display_hdmi', action="store", type=int, default=0, choices=[0,1,2], help='buttons display HDMI (0=off, default: %(default)s))')
    parser.add_argument('-car','--caption_rot', action="store", type=str, default='90', choices=['normal', 'flipped','90','180','270','flipped-90','flipped-180','flipped-270'], help='caption display rotation (default: %(default)s))')
    parser.add_argument('-dir','--display_rot', action="store", type=str, default='normal', choices=['normal', 'flipped','90','180','270','flipped-90','flipped-180','flipped-270'], help='buttons display rotation (default: %(default)s))')
    parser.add_argument('-g','--api_file', action="store", type=str, default="google_ai_api_key.txt", help='default google ai api key file to use, or google API_KEY (default: %(default)s))')
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
    
    def __init__(self,     ip,
                           folder,
                           period          = 5,
                           update_time     = 1440,
                           display_for     = 120,
                           include_fav     = False,
                           sync            = True,
                           matte           = 'none',
                           sequential      = False,
                           on              = False,
                           token_file      = None,
                           art_mode        = False,
                           port            = 5000,
                           modal_size      = '',
                           photographer    = None,
                           caption_hdmi    = 1,
                           display_hdmi    = 0,
                           caption_rot     = '90',
                           display_rot     = 'normal',
                           theme           = None,
                           serif_font      = False,
                           exif            = True,
                           kiosk           = False,
                           api_key         = None):
        super().__init__(  ip,
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
        self.caption_hdmi = caption_hdmi
        self.display_hdmi = display_hdmi
        self.caption_rot = caption_rot
        self.display_rot = display_rot
        self.width = self.height = 0    #screen settings
        self.theme = theme
        self.serif_font = serif_font
        self.kiosk = kiosk
        self.api_key = api_key
        self.connected = set()
        self.exit = False
        self.text = {}
        self.screens = {}
        self.browsers = []
        self.add_signals()
        self.text_lock = asyncio.Lock()
        self.ws_lock = asyncio.Lock()
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
        if self.caption_hdmi == 0 and self.display_hdmi == 0:
            self.log.info('No displays selected')
            return
        self.screens = await self.get_connected_screens_status()
        await self.set_screens(False)
        if self.caption_hdmi == self.display_hdmi and self.caption_hdmi != 0:
            self.log.warning('Button Display HDMI is the same as caption HDMI - disabling buttons display')
            self.display_hdmi = 0
    
        if self.caption_hdmi not in self.screens.keys():
            self.log.warning('no caption display {}'.format('' if self.caption_hdmi <=0 else 'on HDMI {}'.format(self.caption_hdmi)))
            
        if self.display_hdmi not in self.screens.keys():
            self.log.warning('no buttons display {}'.format('' if self.display_hdmi <=0 else 'on HDMI {}'.format(self.display_hdmi)))
            
        #configure and turn on screens
        for hdmi, val in self.screens.items():
            if self.caption_hdmi == hdmi:
                self.log.info('Configuring Caption Screen on {}'.format(val['name']))
                val['tra'] = self.caption_rot
                await self.screen_control(True, hdmi=hdmi, force=True)
            if self.display_hdmi == hdmi:
                self.log.info('Configuring Button Screen on {}'.format(val['name']))
                val['tra'] = self.display_rot
                await self.screen_control(True, hdmi=hdmi, force=True)
                
        #reload screen status
        self.screens = await self.get_connected_screens_status()
        self.get_screen_size()
        await self.restart_browsers()
                
    async def restart_browsers(self, delay=5):
        '''
        close and reopen browser windows
        '''
        if self.browsers:
            self.log.info('closing browsers')
            for br in self.browsers:
                if br.returncode == None:
                    br.terminate()
                while br.returncode == None:
                    await asyncio.sleep(1)
            self.browsers = []
            self.log.info('browsers closed.')
        self.log.info('starting browser windows')
        for hdmi, val in self.screens.items():
            if self.caption_hdmi == hdmi:
                self.log.info('Starting Caption Screen on {}'.format(val['name']))
                asyncio.create_task(self.start_browser_with_delay(app='http://localhost:{}/caption'.format(self.port), pos=val['pos'], kiosk=True, delay=delay))  #caption display
                await asyncio.sleep(2)
            if self.display_hdmi == hdmi:
                self.log.info('Starting Button Screen on {}'.format(val['name']))
                asyncio.create_task(self.start_browser_with_delay(app='http://localhost:{}/'.format(self.port), pos=val['pos'], kiosk=True, delay=delay))        #button display
                await asyncio.sleep(2)
                
    def get_screen_size(self):
        '''
        get width and height of screen(s)
        '''
        for val in self.screens.values():
            if val.get('res'):
                self.width += val['res'][0]
                self.height = max(val['res'][1], self.height)
        self.log.info('{} screens detected, width: {} height: {}'.format(len(self.screens), self.width, self.height))
        
    def multi_screen(self):
        '''
        do we have two screens connected
        '''
        return len(self.screens) > 1
        
    async def serve_forever(self, production=False):
        '''
        start everything up in either development or production environment
        '''
        await self.initialize_screens()
        if production:
            self.log.info('PRODUCTION Mode')
            config = Config()
            config.bind = '{}:{}'.format(self.host, self.port)
            config.loglevel = 'DEBUG' if self.debug else 'INFO'
            server = serve(self.app, config, shutdown_trigger=self.shutdown_trigger)
        else:
            self.log.info('DEVELOPMENT Mode')
            server = self.app.run_task(host=self.host, port=self.port, debug=self.debug,  shutdown_trigger=self.shutdown_trigger)
        self.log.info('Serving files from: {}'.format(self.app.static_folder))
        await asyncio.gather(server, self.start_monitoring(), return_exceptions=False)
        
    def close(self):
        '''
        exit server
        '''
        self.log.info('SIGINT/SIGTERM received, exiting')
        self.exit=True
        
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
        if not self.ws_lock.locked():           # only start one broadcast job
            self.log.info('websocket sending started')
            async with self.ws_lock:    
                await self.broadcast_tv_filename()
            self.log.warning('websocket sending ended')

    async def receiving(self):
        '''
        websocket receive requests from web page
        '''
        self.log.info('WS:{} websocket receiving started'.format(websocket.id))
        while not self.exit:
            data = await websocket.receive_json()
            await self.ws_process(data)      
        self.log.warning('WS:{} websocket receiving ended'.format(websocket.id))
        
    async def broadcast_tv_filename(self):
        '''
        broadcast filename changes to all websockets connected
        '''
        data={'type':'update'}
        filename = self.filename_changed()                  #filename generator
        try:
            while not self.exit:
                #stream filename changes on TV to web page
                data['name'] = await anext(filename)        #blocks until next filename is available
                #if we have multiple screens, turning them off and then on messes up the browser windows, so don't do it for a refresh
                await self.set_screens(data['name'] not in (['off'] if self.display_hdmi else ['off', 'refresh']))
                for websoc in self.connected:
                    if data['name'] in websoc.skip:         #skip if image was previously requested, as modal is already displayed
                        self.log.info('WS({}): Not sending {} as image was previously selected'.format(websoc.id, data['name']))
                        websoc.skip.discard(data['name'])
                    else:
                        await self.ws_send(data, websoc)
        finally:
            if self.exit:
                self.log.info('turning off all screens on EXIT')
                asyncio.create_task(self.set_screens(False))
        
    async def ws_process(self, data):
        '''
        process and respond to websocket data request
        '''
        self.log.info('WS({}): received from ws: {}'.format(websocket.id, data))
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
                
            case 'display':
                #display filename on TV via manual selection
                self.log.info('WS:{} show image: {}'.format(websocket.id, data['name']))
                websocket.skip.add(data['name'])
                await self.set_image_from_filename(data['name'])
                
            case 'reload':
                # reload buttons - called if files have been updated
                image_names = self.get_data()
                window = await self.get_template_attribute('macros.html', 'render_buttons')
                html = await window(image_names, str(self.kiosk).lower())
                await self.ws_send({'type':'update',
                                    'name': 'reload',
                                    'html': html})
                self.prev_filename = None   #trigger reload of filename
                
            case _:
                self.log.info('No match for data type: {}'.format(data['type']))
                
    async def get_window_data(self, name, type='modal'):
        '''
        get html to send to caption or modal windows using macro filled in from text data
        '''
        text = await self.get_text(name, type=type)
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
        ws = websoc or websocket
        if not self.debug:
            self.log.info('WS({}): sending: type: {}, name: {}'.format(ws.id, data.get('type'), data.get('name', data)))
        self.log.debug('WS({}): sending: {}'.format(ws.id, data))
        await ws.send_json(data)
        
    async def initialize_ws(self):
        '''
        send initialization info for web page on ws connection
        '''
        await self.ws_send({'type': 'theme', 'name': str(self.theme)})  #send 'theme' with name of theme to update display on first connection
        await self.ws_send({'type': 'kiosk', 'name': str(self.kiosk)})  #send 'kiosk' with name as kiosk mode
        self.prev_filename = None   #trigger reload of filename
        
    def get_ws_id(self):
        '''
        returns next sequential ws id as an integer, with id's being resued when disconnected
        just for logging id's
        '''
        used = [ws.id for ws in self.connected]
        return [x for x in range(1, len(used)+2) if x not in used][0]

    async def ws(self):
        '''
        start websocket
        NOTE: websocket is a context based global, so each websocket variable refers to it's own context (ie the websocket that created it)
        '''
        try:
            websocket.skip = set()
            websocket.id = self.get_ws_id()
            self.connected.add(websocket._get_current_object())
            self.log.info('WS:{}, (total:{}) websocket connected'.format(websocket.id, len(self.connected)))
            await self.initialize_ws()
            producer = asyncio.create_task(self.sending())
            consumer = asyncio.create_task(self.receiving())
            await asyncio.gather(producer, consumer)
        except asyncio.exceptions.CancelledError:
            self.log.info('WS({}): websocket cancelled'.format(websocket.id))
        except Exception as e:
            self.log.exception(e)
        finally:
            self.log.info('WS({}): cancelling websocket tasks'.format(websocket.id))
            try:
                consumer.cancel()
                producer.cancel()
            except Exception:
                pass
            self.connected.discard(websocket)
        self.log.warning('WS({}): websocket closed'.format(websocket.id))
        
    def get_data(self):
        '''
        get filenames from files in static folder and update exif if changed
        '''
        self.log.info('reloading thumnails')
        image_names = self.get_folder_files()
        self.exif.get_files(self.get_modified_files())
        self.log.info('displaying Buttons for: {}'.format(image_names))
        return image_names
        
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
        self.log.info('loading thumbnail page')
        image_names = self.get_data()
        return await render_template('home.html', names=image_names, kiosk=str(self.kiosk).lower(), theme=self.theme)
        
    async def move_mouse(self, x, y):
        '''
        with Wayland, have to move the mouse to the screen we want the windown to appear on
        so, have to do this nasty thing
        '''
        client = WaylandClient(self.width, self.height)
        client.move_mouse(x, y)
        await asyncio.sleep(0.1)
        
    async def set_screens(self, on):
        '''
        Turn all attached screens on or off
        '''
        self.log.debug('turning all screens {}'.format('ON' if on else 'OFF'))
        result = []
        for hdmi in self.screens.keys():
            if hdmi in [self.caption_hdmi, self.display_hdmi]:
                result.append(await self.screen_control(on, hdmi=hdmi))    #turn screen on or off
                
        if self.multi_screen() and any(result):
            if on:
                asyncio.create_task(self.restart_browsers(1))
        
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
        screens = {}
        sc = None
        is_on = False
        found = False
        proc = await asyncio.create_subprocess_exec('/usr/bin/wlr-randr', stdout=asyncio.subprocess.PIPE)
        # Read output and process line by line
        data = await proc.stdout.read()
        lines = data.decode().split('\n') if data else []
        for i, line in enumerate(lines):
            if screen:
                if screen in line and not found:  #Find HDMI-A-X "HOT WaveShsare 0x00000001 (HDMI-A-X)"
                    found = True
                    continue
                if found and 'Enabled:' in line:
                    is_on = 'yes' in line #check if Enabled: yes
                    break
            else:
                if 'HDMI-A' in line:
                    sc = line.split(' ')[0]
                    hdmi = int(sc.split('-')[-1])
                    screens[hdmi] = {'name':sc}
                    self.log.info('found attached screen: {}'.format(line))
                if 'Enabled:' in line and 'no' in line and sc:
                    sc = None
                    continue
                if 'current' in line and sc:
                    self.log.info(line.strip())
                    x, y = line.strip().split(' ')[0].split('x')
                    screens[hdmi]['res'] = (int(x),int(y))
                if 'Position:' in line and sc:
                    self.log.info(line.strip())
                    x, y = line.strip().split(' ')[1].split(',')
                    screens[hdmi]['pos'] = (int(x),int(y))
                if 'Transform:' in line and sc:
                    self.log.info(line.strip())
                    tr = line.strip().split(' ')[1]
                    screens[hdmi]['rot'] = 0 if tr in ['normal', 'flipped'] else int(tr.replace('flipped-',''))
                    screens[hdmi]['tra'] = tr.strip()
                    #reverse x/y if screen rotated
                    if screens[hdmi]['rot'] in [90, 270]:
                        screens[hdmi]['res'] = screens[hdmi]['res'][::-1]
                    sc = None
                    
        await proc.wait()
        #reverse sort the order of screens (if two connected) as it matters what order they are turned on and off in
        return is_on if screen else dict(sorted(screens.items(), reverse=True))
        
    async def screen_control(self, on=True, hdmi=1, force=False):
        '''
        Turn caption/display screen on or off using:
        wlr-randr --output HDMI-A-1 --off or --on
        check to see if screen is on first if turning on as screen flickers sending --on again, if already on.
        '''
        screen = self.screens.get(hdmi,{}).get('name')
        if screen:   #if our screen is one of the detected screens
            is_on = await self.get_connected_screens_status(screen) if on else False
            if (on and not is_on) or not on or force:
                self.log.info('Turning: {} {}'.format(screen, 'ON' if on else 'OFF'))
                proc = await asyncio.create_subprocess_exec('/usr/bin/wlr-randr',
                                                            '--output', screen,
                                                            '--on' if on else '--off',
                                                            '--transform', self.screens[hdmi].get('tra','normal'),
                                                            #'--pos', '{},{}'.format(*self.screens[hdmi]get('pos',(0,0)))
                                                            )
                # Wait for the subprocess exit.
                await proc.wait()
                return (on and not is_on) or not on #for determining if we need to restart the browsers
        
    async def start_browser_with_delay(self, app, pos, kiosk, delay=5):
        '''
        start browser on display after delay - call as task
        the delay is to allow time for the web server to start up
        '''
        await asyncio.sleep(delay)
        await self.start_browser_on_display(app, pos, kiosk)
        
    async def start_browser_on_display(self, app='http://localhost:5000/caption', pos=(0,0), kiosk=True):
        '''
        display web page (app) on screen in possition given by pos (x, y) - seconds screen would start at 1420, so 1420,0
        derfaults are for the caption display, second display would be app='http://localhost:5000', pos='1420,0'
        Will not return until browser exits
        '''
        if self.multi_screen():
            await self.move_mouse(pos[0], 0)
        self.log.info('starting browser: {}'.format(app))
        proc = await asyncio.create_subprocess_exec('/usr/bin/chromium-browser',
                                                    '--kiosk' if kiosk else '',
                                                    '--noerrdialogs',
                                                    '--disable-infobars',
                                                    '--app={}'.format(app),
                                                    '--start-fullscreen',
                                                    '--window-position={},()'.format(pos[0],pos[1]),
                                                    '--user-data-dir={}'.format(TemporaryDirectory().name),
                                                    '--enable-features=OverlayScrollbar',
                                                    stderr=asyncio.subprocess.DEVNULL)
        self.browsers.append(proc)
        # Wait for the subprocess exit.
        await proc.wait()
        
    def get_text_file_name(self, filename):
        '''
        find text file name from image file name
        case insensitive - ie finds .TXT and .txt files
        '''
        text_file = self.get_Path(filename, suffix=".TXT")
        for file in self.folder.iterdir():
            if file.name.upper() == text_file.name.upper():
                return file
        return None
        
    async def get_text(self, filename, type='modal'):
        '''
        takes an image filename, finds corresponding text file.
        if data does not already exist in self.text and file has not been updated, reads the file from the static folder
        as a dictionary of the json.
        returns None if file not found, or json is invalid and data not in the image exif data
        returns caption data or modal data built from the text or exif data
        '''
        # use lock to prevent multiple simultaneous calls for modal and caption
        async with self.text_lock:
            #default info
            data = {"id": self.get_Path(filename, suffix=""), "name": filename}
            text = {}
            text_file = self.get_text_file_name(filename)
            if text_file:
                try:
                    ts = self.get_last_updated(text_file)
                    if self.text.get(filename,{}).get('timestamp') != ts:
                        self.log.info('reading text file: {}'.format(text_file.name))
                        text = self.app.json.loads(text_file.read_text())
                        self.update_reference_dict(filename, text, ts)
                    else:
                        text = self.text.get(filename,{})
                    self.log.debug('got text for image: {}: {}'.format(filename, text))
                except FileNotFoundError:
                    pass
                except Exception as e:
                    self.log.warning('error: {}: {}'.format(e, text_file))
            #use AI to fill in missing details if we have api_key
            info, text = await self.get_ai_description(self.get_modal_from_exif(filename, text), filename, text_file, text)
            #python 3.10 and above only!
            match type:
                case 'modal':
                    text = info
                case 'caption':
                    text = self.get_caption_from_exif(filename, text)
            if text:
                data.update(text)
                return data
            return None
            
    def get_modal_from_exif(self, filename, text):
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
        try:
            modal = {}
            modal['header'] = self.exif.get_title(filename, text.get('header') or text.get('description'))
            modal['description'] = self.exif.get_description(filename, text.get('description'))
            if modal['header'] and modal['description'] and modal['header'] == modal['description']:
                modal['description'] = None
            if modal['header'] or self.api_key:
                modal['details'] = self.html_markup(self.exif.get_user_comment(filename, text.get('details')))
                modal['time'] = self.exif.get_date_original(filename, text.get('time'))
                modal['location'] = self.exif.get_location(filename, text.get('location'))
                modal['credit'] = self.exif.get_credit(filename, text.get('credit'))
                #add default credit if missing
                if not modal.get('credit'):
                    photographer = self.exif.get_photographer(filename, text.get('photographer', '').strip() or self.photographer) or ''
                    modal['credit'] = 'wildfoto.au' if all(val in photographer.lower() for val in ['paul', 'thompsen']) else photographer or 'unknown'
                return modal
        except Exception as e:
            self.log.exception(e)
        return None
            
    def get_caption_from_exif(self, filename, text):
        '''
        fill in caption data from exif data if it exists or default from text file
        uses exif fields:
        ImageTitle, ImageDescription for caption, if not present, uses 'caption' in text file, or if not present 'header' or 'description' in text file
        GPS address for location, or 'location' in text file if not present
        Photographer or Artist, or 'photographer' in text file, plus month and year from DateTimeOriginal for byline
        Model and FocalLength for camera
        ExposureTime, FNumber (or ApertureValue) and ISOSpeedRatings for settings
        
        caption values are:
        title: 'caption' or 'header' or 'description' in text file
        location
        byline
        camera
        settings
        '''
        try:
            caption = {}
            #get values from exif or defaults from text file
            caption['title'] = self.exif.get_title(filename, text.get('caption') or text.get('header') or text.get('description'))
            if caption['title']:
                caption['location'] =  self.exif.get_caption_location(filename, text.get('location'))
                caption['byline'] = self.exif.get_byline(filename, text.get('photographer', '').strip() or self.photographer)
                caption['camera'] = self.exif.get_camera(filename)
                caption['settings'] = self.exif.get_settings(filename)
                return caption
        except Exception as e:
            self.log.exception(e)
        return None
        
    def update_reference_dict(self, filename, text, ts):
        '''
        update the quick reference dictionary for modals and display
        '''
        text['timestamp'] = ts
        self.text[filename] = text
        
    def save_text_file(self, text, text_file):
        '''
        save image description text file
        '''
        #add default fields or blank
        text['header'] = text.get('header') or ''
        text['description'] = text.get('description') or ''
        text['details'] = text.get('details') or ''
        text['time'] = text.get('time') or ''
        text['location'] = text.get('location') or ''
        text['photographer'] = text.get('photographer') or ''
        text['credit'] = text.get('credit') or ''
        text['caption'] = text.get('caption') or ''
        self.log.info('writing new text file: {}'.format(text_file.name))
        text_file.write_text(self.app.json.dumps(text, indent=2, sort_keys=True))
            
    async def get_ai_description(self, info, image_file, text_file, text):
        '''
        use google AI to fill in details, if we have an API KEY
        '''
        info = info or {}
        if self.api_key and (not info.get('details') or not info.get('header')):
            image_file = self.folder/image_file
            text_file = text_file or image_file.with_suffix(".TXT")
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=self.api_key)
                image = self.get_image_for_ai(image_file, client)
                if image:
                    response = await client.aio.models.generate_content(
                        model='gemini-2.0-flash-001',
                        contents=[
                            'describe this image',
                            'use text only inline html',
                            'description should be the latin name of any animals in html italics or a short description of the scene',
                            'details should be 400 words or less and include behaviour, habitat and simple inline html',
                            'if there are no animals, describe the scene, and do not mention the absence of animals',
                            'do not include the location',
                            'header should be a plain text caption for a picture with less than 45 characters',
                            'do not include links',
                            'file name is () which may be a hint to the subject and/or location'.format(image_file.with_suffix("").name.replace('_',' ')),
                            'location is {}'.format(info['location'] if info.get('location') else 'Austrailia' if info.get('credit') == 'wildfoto.au' else 'possibly Austrailia'), #use default location suggestion if missing
                            '()'.format('subject is {}'.format(info['header'] if info.get('header') else '')),
                            '()'.format('description is {}'.format(info['description'] if info.get('description') else '')),
                            image
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type='application/json',
                            response_schema={
                                'required': [
                                    'header',
                                    'description',
                                    'details'
                                ],
                                'properties': {
                                    'header': {'type': 'STRING'},
                                    'description': {'type': 'STRING'},
                                    'details': {'type': 'STRING'}
                                },
                                'type': 'OBJECT',
                            },
                        )
                    )
                    self.log.info('Google AI info: {}'.format(response.text))
                    if self.update_text(info, text, self.app.json.loads(response.text)):
                        self.save_text_file(text, text_file)
                        self.update_reference_dict(image_file.name, text, self.get_last_updated(text_file))
            except Exception as e:
                self.log.warning(e)
        return info, text
        
async def main():
    args = parseargs()
    logging.basicConfig(format='%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s',
                        force=True,
                        level=logging.DEBUG if args.debug else logging.INFO)
    log = logging.getLogger('Main')
    log.info('Program {} Started, version: {}'.format(__file__, __version__))
    log.info("Python Version: {}".format(sys.version.replace('\n','')))
    log.debug('Debug mode')
    
    if sys.version_info < (3, 10):
        log.critical('Python version must be 3.10 or higher - exiting')
        sys.exit(1)
    
    args.folder = WebServer.get_Path(args.folder)
    
    if not args.folder.is_dir():
        log.warning('folder {} does not exist, exiting'.format(args.folder))
        sys.exit(1)
        
    log.info("running in Kiosk mode: {}".format(args.kiosk))
    log.info('using theme: {}'.format(args.theme))
    log.info('using serif font for caption: {}'.format(args.serif_font))
    log.info('ensure Art Mode: {}'.format(args.art_mode))
    
    #get google api_key for AI
    if WebServer.get_Path(args.api_file).is_file():
        api_key = WebServer.get_Path(args.api_file).read_text().replace('\n','')
    elif args.api_file.upper().endswith('.TXT') or len(args.api_file) != 39:
        api_key = None
    else:
        api_key = args.api_file
        
    if api_key:
        log.info('Using Google AI to fill in image details if missing')
        
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
                     caption_hdmi    = args.caption_hdmi,
                     display_hdmi    = args.display_hdmi,
                     caption_rot     = args.caption_rot,
                     display_rot     = args.display_rot,
                     theme           = args.theme,
                     serif_font      = args.serif_font,
                     exif            = args.exif,
                     kiosk           = args.kiosk,
                     api_key         = api_key)
    
    await web.serve_forever(args.production)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass    

