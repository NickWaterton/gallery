#!/usr/bin/env python3
# movemouse for Wayland from https://github.com/asweigart/pyautogui/issues/111
# moves the mouse on the screen using zwlr_virtual_pointer_manager_v1 on Wayland devices
# V 1.0.1 30/5/2025 NW various tweaks

import os
import socket
import struct
import sys
import argparse, logging

__version__ = '1.0.1'

def parseargs():
    # Add command line argument parsing
    parser = argparse.ArgumentParser(description='Moouse Clicker for Wayland and X11'.format(__version__))
    parser.add_argument('x', action="store", type=int, default=0, help='x location of mouse click (default: %(default)s))')
    parser.add_argument('-y', action="store", type=int, default=0, help='y location of mouse click (default: %(default)s))')
    parser.add_argument('-D','--debug', action='store_true', default=False, help='Debug mode (default: %(default)s))')
    return parser.parse_args()

def encode_wayland_string(s: str) -> bytes:
    # Format: length (uint32) + string (utf-8) + (null byte) + padding (null bytes)

    if s is None:
        return struct.pack("<I", 0)  # Null string (length 0)

    encoded = s.encode("utf-8") + b"\x00"  # Append null terminator
    length = len(encoded)

    # Calculate padding to align to 32-bit (4-byte) boundary
    padding_size = (4 - (length % 4)) % 4
    padding = b"\x00" * padding_size

    return struct.pack("<I", length) + encoded + padding


class WaylandClient:
    
    interface_names = ["zwlr_virtual_pointer_manager_v1",
                       "zwlr_virtual_pointer_manager_v2",
                       "wlr_virtual_pointer_manager"]
    
    def __init__(self, width=1920, height=1080):
        self.log = logging.getLogger('Main.'+__class__.__name__)
        self.debug = self.log.getEffectiveLevel() <= logging.DEBUG
        self.socket_path = self.get_socket_path()
        self.sock = self.connect_to_wayland()
        self.endianness = "<" if sys.byteorder == "little" else ">"

        self.wl_registry_id = 2  # Arbitrary ID for wl_registry
        self.callback_id = 3     # Arbitrary ID for wl_callback
        self.virtual_pointer_manager_id = (
            4  # Arbitrary ID for zwlr_virtual_pointer_manager_v1
        )
        self.virtual_pointer_id = 5  # Arbitrary ID for zwp_virtual_pointer_v1
        self.width = width
        self.height = height

    def get_socket_path(self):
        wayland_display = os.getenv("WAYLAND_DISPLAY", "wayland-0")
        return f"/run/user/{os.getuid()}/{wayland_display}"

    def connect_to_wayland(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.socket_path)
        self.log.info(f"Connected to Wayland server at {self.socket_path}")
        return sock

    def send_message(self, object_id, opcode, payload):
        message_size = 8 + len(payload)
        message = (
            struct.pack(f"{self.endianness}IHH", object_id, opcode, message_size)
            + payload
        )
        self.sock.sendall(message)

    def send_registry_request(self):
        self.send_message(1, 1, struct.pack(f"{self.endianness}I", self.wl_registry_id))
        self.log.debug("Sent wl_display.get_registry() request...")

    def send_sync_request(self):
        self.send_message(1, 0, struct.pack(f"{self.endianness}I", self.callback_id))
        self.log.debug("Sent wl_display.sync() request...")

    def receive_message(self):
        header = self.sock.recv(8)
        if len(header) < 8:
            return None, None, None  # Connection closed or incomplete data

        object_id, size_opcode = struct.unpack(f"{self.endianness}II", header)
        size = (size_opcode >> 16) & 0xFFFF
        opcode = size_opcode & 0xFFFF
        message_data = self.sock.recv(size - 8)
        return object_id, opcode, message_data

    def handle_events(self):
        found = False
        while True:
            object_id, opcode, message_data = self.receive_message()
            if object_id is None or opcode is None or message_data is None:
                break

            # Handling events from wl_display (object_id 1) for debugging
            if object_id == 1:
                self.log.debug(f"Received event from wl_display: {opcode}")
                self.log.debug(f"Message data: {message_data}")

            # wl_registry.global event from the registry (object_id 2, opcode 0)
            if object_id == 2 and opcode == 0:
                # Parse the global event payload.
                # First 4 bytes are the global object's numeric name.
                global_name = struct.unpack(f"{self.endianness}I", message_data[:4])[0]
                # Next, extract the interface name as a Wayland string.
                name_offset = 4
                string_size = struct.unpack(
                    f"{self.endianness}I", message_data[name_offset : name_offset + 4]
                )[0]
                interface_name = message_data[
                    name_offset + 4 : name_offset + 4 + string_size - 1
                ].decode("utf-8")
                # The final 4 bytes are the version.
                version = struct.unpack(f"{self.endianness}I", message_data[-4:])[0]

                self.log.debug(
                    f"Discovered global: {interface_name} (name {global_name}, version {version})"
                )

                # When we discover the virtual pointer manager, we bind to it.
                if not found and interface_name in self.interface_names:
                    # Build payload:
                    # 1. Global name (uint32)
                    # 2. Interface name (string with length, content, and padding)
                    # 3. Version (uint32)
                    # 4. New object id (uint32)
                    payload = (
                        struct.pack(f"{self.endianness}I", global_name)
                        + encode_wayland_string(interface_name)
                        + struct.pack(
                            f"{self.endianness}II",
                            version,
                            self.virtual_pointer_manager_id,
                        )
                    )
                    # Send the bind request (opcode 0 on wl_registry)
                    self.send_message(self.wl_registry_id, 0, payload)
                    self.log.info("Sent {}.bind() request...".format(interface_name))
                    found = True

            # wl_callback.done event (object_id equal to callback_id, opcode 0)
            elif object_id == self.callback_id and opcode == 0:
                self.log.debug("Received wl_callback.done event.")
                break

    def create_virtual_pointer(self):
        self.send_message(
            self.virtual_pointer_manager_id,
            0,
            struct.pack(f"{self.endianness}II", 0, self.virtual_pointer_id),
        )

    def send_motion_absolute(self, x, y, x_extent, y_extent):
        payload = struct.pack(f"{self.endianness}IIIII", 0, x, y, x_extent, y_extent)
        self.send_message(self.virtual_pointer_id, 1, payload)

    def init(self):
        self.send_registry_request()
        self.send_sync_request()
        self.handle_events()
        self.create_virtual_pointer()

    def move_mouse(self, x, y):
        try:
            self.init()
            self.send_motion_absolute(x, y, self.width, self.height) # Requires the width and height of the screen
            self.log.info('moved mouse to {}, {}'.format(x, y))
        except Exception as e:
            self.log.warning('{}: failed to set mouse to {}, {}'.format(e, x, y))
            

def get_connected_screens_size():
    '''
    detect attached screens and get the screen size
    uses wlr-randr
    '''
    import subprocess
    screens = {}
    sc = None
    width = height = 0
    try:
        result = subprocess.check_output(['/usr/bin/wlr-randr'], text=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed with return code {e.returncode}")
        return width, height
    # Read output and process line by line
    lines = result.split('\n') if result else []
    for i, line in enumerate(lines):
        if 'HDMI-A' in line:
            sc = line.split(' ')[0]
            hdmi = int(sc.split('-')[-1])
            screens[hdmi] = {'name':sc}
            logging.info('found attached screen: {}'.format(line))
        if 'Enabled:' in line and 'no' in line and sc:
            logging.warning('{} is off'.format(sc))
            sc = None
            continue
        if 'current' in line and sc:
            logging.info(line.strip())
            x, y = line.strip().split(' ')[0].split('x')
            screens[hdmi]['res'] = (int(x),int(y))
        if 'Transform:' in line and sc:
            logging.info(line.strip())
            tr = line.strip().split(' ')[1]
            rot = 0 if tr in ['normal', 'flipped'] else int(tr.replace('flipped-',''))
            #reverse x/y if screen rotated
            if rot in [90, 270]:
                screens[hdmi]['res'] = screens[hdmi]['res'][::-1]
            sc = None
                
    for val in screens.values():
        if val.get('res'):
            width += val['res'][0]
            height = max(val['res'][1], height)
    logging.info('{} screens detected, width: {} height: {}'.format(len(screens), width, height))
    return width, height 


if __name__ == "__main__":
    args = parseargs()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    width, height = get_connected_screens_size()
    if width and height:
        if 0 <= args.x <= width and 0 <= args.y <= height:
            client = WaylandClient(width, height)
            client.move_mouse(args.x, args.y)
        else:
            logging.error('x and/or y are outside the screen size')
    else:
        logging.error('no screens detected or they are off')