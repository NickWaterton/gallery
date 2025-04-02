#!/usr/bin/env python3
# exif data class, gets exif data from image, and GPS location (if GPSInfo exists)
# needs PIL (pip install pillow)
# and optionally geopy (pip install geopy) for location

import asyncio
import os, json
from pprint import pprint, pformat
from datetime import datetime
HAVE_PIL = False
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS, IFD
    HAVE_PIL=True
except ImportError:
    pass
HAVE_GEOPY = False
try:
    from geopy.geocoders import Nominatim
    from geopy.adapters import AioHTTPAdapter
    from geopy.extra.rate_limiter import AsyncRateLimiter
    from geopy.exc import GeocoderTimedOut
    HAVE_GEOPY=True
except ImportError:
    pass
import logging

__version__ = '1.0.0'

logging.basicConfig(level=logging.INFO)

class ExifData:
    
    decode = {'XPAuthor': 'UTF-16-LE',
              'XPComment': 'UTF-16-LE',
              'XPTitle': 'UTF-16-LE',
              'XPSubject':'UTF-16-LE',
              'XPKeywords':'UTF-16-LE'}
    ignore = ['59932', 'MakerNote', '59933']    #proprietory tags to ignore
    additional_tags = {42038: 'ImageTitle'}     #additional tags to add
    
    def __init__(self, folder, ip=None):
                           
        self.log = logging.getLogger('Main.'+__class__.__name__)
        self.debug = self.log.getEffectiveLevel() <= logging.DEBUG
        self.folder = folder
        self.ip = ip
        self.exif = {}
        TAGS.update(self.additional_tags)
        self.gps_task = None
        self.filename = './gps_data.json'
        self.get_files()

    def get_files(self, image_names=None):
        '''
        make list from files in static folder
        '''
        if HAVE_PIL and self.folder:
            if not image_names:
                image_names = [img for img in os.listdir(self.folder) if not img.upper().endswith('.TXT')]
            for file in image_names:
                self.update_exif_dict(file)
            #run as task because of rate limiting
            if not self.gps_task or self.gps_task.done():
                self.gps_task = asyncio.create_task(self.update_addresses(image_names))
                
    def load_data(self):
        try:
            with open(self.filename, 'r') as f:
                data = json.load(f)
                [self.exif[file].update(data[file]) for file in self.exif.keys() if data.get(file)]
        except Exception:
            pass
            
    def save_data(self):
        try:
            with open(self.filename, 'w') as f:
                data = {file:{k:v} for file in self.exif.keys() for k, v in self.exif[file].items() if k ==  'GEOPY_Address'}
                self.log.debug('SAVE:\r\n{}'.format(pformat(data)))
                if data:
                    json.dump(data, f, indent=2)
        except Exception as e:
            pass
        
    def update_exif_dict(self, file):
        '''
        only available if PIL is installed (pip install Pillow)
        get exif tags from image file and update self.exif
        so that we can extract 'DateTimeOriginal' and 'GPSInfo'later
        NOTE: have to use _getexif() getexif() is different
        '''
        if HAVE_PIL: #and file not in self.exif.keys():
            self.log.info('{}: getting exif data'.format(file))
            img = Image.open(os.path.join(self.folder, file))
            self.exif[file]={self.tag_name(tag): self.conv_bytes(tag, value) for tag, value in (img._getexif() or {}).items() if self.tag_name(tag) not in self.ignore}
            self.log.debug('{}: exif tags:\r\n{}'.format(file, pformat(self.exif.get(file))))
                
    def conv_bytes(self, tag, value):
        tagname = self.tag_name(tag)
        try:
            return value.decode(self.decode.get(tagname, 'UTF-8')) if isinstance(value, bytes) else value
        except UnicodeDecodeError:
            self.log.warning('error decoding: {}'.format(tagname))
        return value
        
    def tag_name(self, tag):
        return TAGS.get(tag, str(tag))
        
    def get_key(self, file, key):
        if isinstance(key, (tuple, list)):
            return self.get_keys(file, key)
        value = self.exif.get(file, {}).get(key)
        if isinstance(value, tuple):
            return (self.convert_rational(x) for x in value)
        if isinstance(value, str):
            return value.replace('\x00', '').strip()
        return value
        
    def get_keys(self, file, keys=[]):
        for key in keys:
            value = self.get_key(file, key)
            if value:
                return value
        return None

    def convert_rational(self, value):
        if isinstance(value, tuple):
            return float(value[0]/value[1]) if value[1] != 0 else 0
        return value
        
    def get_lat_long(self, file):
        '''
        Extract raw GPS data for latitude (north) and longitude (east)
        '''
        gpsinfo = self.get_key(file, 'GPSInfo')
        if isinstance(gpsinfo, dict) and gpsinfo:
            # Convert latitude and longitude from degrees-minutes-seconds to decimal format
            self.log.debug('{}: GPS info:\r\n{}'.format(file, pformat({'{}({})'.format(GPSTAGS[k], k):v for k, v in gpsinfo.items()}))) 
            lat = self._convert_to_degrees(gpsinfo[2]) * (-1 if gpsinfo[1].upper() != "N" else 1)
            lng = self._convert_to_degrees(gpsinfo[4]) * (-1 if gpsinfo[3].upper() != "E" else 1)
            self.log.debug('got lat: {}, long: {}'.format(lat, lng))
            return lat, lng
        return None, None
                
    def _convert_to_degrees(self, value):
        '''
        Helper function to convert the GPS coordinates stored in the EXIF to degrees in float format
        '''
        if value:
            val = [(lambda x,y: float(x/y))(*x) if isinstance(x, tuple) else x for x in value]
            return sum([float(x)/(60**i) for i, x in enumerate(val)])
        return 0    
        
    async def update_addresses(self, file_list):
        '''
        Use Geopy's Nominatim geocoder to retrieve the address for the coordinates
        This is free, but limited to calling once per second, with a unique user_agent name for the app
        see https://operations.osmfoundation.org/policies/nominatim/
        '''
        if HAVE_GEOPY:
            self.load_data()
            async with Nominatim(user_agent="{}-SamsungtvwsGetLocGallery".format(self.ip or ''), timeout=20, adapter_factory=AioHTTPAdapter) as geolocator:
                reverse  = AsyncRateLimiter(geolocator.reverse, min_delay_seconds=1.5, max_retries=1, swallow_exceptions=False)
                for file in file_list:
                    if 'GEOPY_Address' not in self.exif[file].keys():
                        lat, lng = self.get_lat_long(file)
                        if lat and lng:
                            self.log.info('{}: getting GPS data'.format(file))
                            try:
                                locname = await reverse(f"{lat}, {lng}")
                                if locname:
                                    self.exif[file]['GEOPY_Address'] = locname.raw
                            except (asyncio.exceptions.TimeoutError, GeocoderTimedOut) as e:
                                self.log.warning('geocode failed on {}: {}'.format(file, e))
                                await asyncio.sleep(5)
                            continue
                        self.log.info('{}: NO address found'.format(file))
                        self.exif[file]['GEOPY_Address'] = None
            self.save_data()
           
    def format_address(self, file, locname):
        '''
        format address so it fits in modal footer
        'display_name': 'Greenwood Point Road, Muskoka Lakes Township, District Municipality of Muskoka, Muskoka District, Central Ontario, Ontario, Canada', 'address': {'road': 'Greenwood Point Road', 'city': 'Muskoka Lakes Township', 'municipality': 'District Municipality of Muskoka', 'county': 'Muskoka District', 'state_district': 'Central Ontario', 'state': 'Ontario', 'ISO3166-2-lvl4': 'CA-ON', 'country': 'Canada', 'country_code': 'ca'}
        '''
        address = None
        if locname:
            try:
                self.log.debug('{}: location: {}'.format(file, locname))
                addr = [self.get_dict_keys(locname['address'], ['village', 'town', 'city']),
                        self.get_dict_keys(locname['address'], ['city_district', 'county', 'state_district']),
                        self.get_dict_keys(locname['address'], ['territory', 'province', 'state']),
                        locname['address'].get('country')]
                address = ('{}'.format(', '.join([a for a in addr if a])))
            except Exception as e:
                address = locname.get('display_name')
            self.log.info('{}: address: {}'.format(file, address))
        return address
        
    def get_dict_keys(self, d, keys=[]):
        for key in keys:
            if key in d.keys():
                return d[key]
        return None
        
    def get_location(self, file, default=None):
        '''
        returns formatted address
        '''
        return default or self.format_address(file, self.get_key(file, 'GEOPY_Address'))
        
    def get_caption_location(self, file, default=None):
        '''
        returns location formatted for caption display
        '''
        location = self.get_location(file, default)
        if location:
            return ' - '.join(location.split(',')[:2]) + ' WA' if ('Northern Territory' in location and 'Australia' in location) else location
        return location
        
    def get_date_original(self, file, default=None):
        '''
        returns date photo was taken from exif data, or None
        '''
        return default or self.get_key(file, 'DateTimeOriginal')
        
    def get_date_original_datetime(self, file):
        '''
        returns date photo was taken from exif data as dateime object, or None
        '''
        date = self.get_date_original(file)
        if date:
            date = datetime.fromisoformat(date.replace(':', '-', 2))
        return date
        
    def get_title(self, file, default=None):
        '''
        return image title
        '''
        title = default or self.get_key(file, ['ImageTitle', 'XPTitle'])
        description = self.get_description(file)
        return title or description
        
    def get_description(self, file, default=None):
        '''
        return image description
        '''
        return default or self.get_key(file, ['XPSubject', 'ImageDescription'])
        ''
        
    def get_artist(self, file):
        '''
        return artist
        '''
        return self.get_key(file, 'Artist')
    
    def get_photographer(self, file, default = None):
        '''
        return Photographer
        '''
        return self.get_key(file, ['Photographer', 'Artist', 'XPAuthor']) or default
    
    def get_byline(self, file, default=None):
        '''
        return byline for caption display
        '''
        photographer = self.get_photographer(file, default)
        date = self.get_date_original_datetime(file)
        month = date.strftime('%B') if date else None
        year = str(date.year) if date else None
        if photographer:
            if date and month:
                return '{} {} {}'.format(photographer, month, year)
            return photographer
        return None
        
    def get_copyright(self, file):
        '''
        return Copyright
        '''
        return self.get_key(file, 'Copyright')
        
    def get_credit(self, file, default=None):
        '''
        return credit
        '''
        return self.get_copyright(file) or self.get_photographer(file, default)
        
    def get_user_comment(self, file, default=None):
        '''
        return user comments
        '''
        comments = default or self.get_key(file, ['UserComment', 'XPComment'])
        if comments.startswith("ASCII"):
            return comments.replace('ASCII','')
        return comments
        
    def get_camera(self, file):
        '''
        returns camera type info
        '''
        #make = self.get_key(file, 'Make')
        model = self.get_key(file, 'Model')
        #lens = self.get_key(file, 'LensModel')
        #lens = ''.join([l for l in (lens.split(' ') if lens else []) if 'mm' in l])
        lens = self.get_key(file, 'FocalLength')
        lens = '{}mm'.format(int(lens)) if lens else self.get_key(file, 'LensModel')
        return ' '.join([t for t in [model, lens] if t])
        
    def get_settings(self, file):
        '''
        returns camera settings
        '''
        exposure = self.get_key(file, 'ExposureTime')
        exposure = '1/{}'.format(int(1/exposure)) if exposure else None
        apperture = self.get_key(file, 'ApertureValue')
        f_stop = self.get_key(file, 'FNumber') or round(2**(apperture/2), 1) if apperture else None
        f_stop = 'f{}'.format(f_stop) if f_stop else None
        iso = self.get_key(file, 'ISOSpeedRatings')
        iso = 'ISO{}'.format(iso) if iso else None
        return ' '.join([t for t in [exposure, f_stop, iso] if t])
        
        
