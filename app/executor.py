"""
Executor: Wake-on-LAN Magic Packet
Kein Docker nötig – nutzt direkte UDP-Sockets
"""

import socket
import struct
import re


class Executor:
    def wake_on_lan(self, mac: str) -> dict:
        """Sendet Magic Packet an MAC-Adresse"""
        try:
            mac_clean = mac.replace(":", "").replace("-", "").upper()
            if len(mac_clean) != 12 or not re.match(r"^[0-9A-F]{12}$", mac_clean):
                return {"success": False, "error": "Ungültige MAC-Adresse"}

            mac_bytes = bytes.fromhex(mac_clean)
            magic = b"\xff" * 6 + mac_bytes * 16

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(magic, ("<broadcast>", 9))

            return {"success": True, "mac": mac}
        except Exception as e:
            return {"success": False, "error": str(e)}
