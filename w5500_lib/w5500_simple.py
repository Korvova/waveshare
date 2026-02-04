"""
Simple W5500 Driver for Waveshare RP2350B
Direct SPI communication without complex library
"""
from machine import Pin, SoftSPI
import time
import struct

class W5500:
    # Block Select Bits
    BSB_COMMON = 0x00
    BSB_SOCKET = 0x01
    BSB_TX = 0x02
    BSB_RX = 0x03

    # Common Registers
    MR = 0x0000      # Mode Register
    GAR = 0x0001     # Gateway Address (4 bytes)
    SUBR = 0x0005    # Subnet Mask (4 bytes)
    SHAR = 0x0009    # Source Hardware Address (6 bytes)
    SIPR = 0x000F    # Source IP Address (4 bytes)
    PHYCFGR = 0x002E # PHY Configuration
    VERSIONR = 0x0039 # Chip Version

    # Socket Registers (offset from socket base)
    Sn_MR = 0x0000   # Socket Mode
    Sn_CR = 0x0001   # Socket Command
    Sn_IR = 0x0002   # Socket Interrupt
    Sn_SR = 0x0003   # Socket Status
    Sn_PORT = 0x0004 # Source Port (2 bytes)
    Sn_TX_FSR = 0x0020 # TX Free Size (2 bytes)
    Sn_TX_RD = 0x0022  # TX Read Pointer (2 bytes)
    Sn_TX_WR = 0x0024  # TX Write Pointer (2 bytes)
    Sn_RX_RSR = 0x0026 # RX Received Size (2 bytes)
    Sn_RX_RD = 0x0028  # RX Read Pointer (2 bytes)

    # Socket Commands
    SOCK_OPEN = 0x01
    SOCK_LISTEN = 0x02
    SOCK_CONNECT = 0x04
    SOCK_DISCON = 0x08
    SOCK_CLOSE = 0x10
    SOCK_SEND = 0x20
    SOCK_RECV = 0x40

    # Socket Status
    SOCK_CLOSED = 0x00
    SOCK_INIT = 0x13
    SOCK_LISTEN_STATUS = 0x14
    SOCK_ESTABLISHED = 0x17
    SOCK_CLOSE_WAIT = 0x1C

    # Socket Modes
    Sn_MR_TCP = 0x01

    def __init__(self, spi, cs_pin, rst_pin=None):
        self.spi = spi
        self.cs = cs_pin
        self.cs.value(1)

        if rst_pin:
            rst_pin.value(0)
            time.sleep_ms(100)
            rst_pin.value(1)
            time.sleep_ms(200)

        # Verify chip
        ver = self.read_reg(self.VERSIONR)
        if ver != 0x04:
            raise Exception(f"W5500 not found! Version: {hex(ver)}")
        print(f"W5500 detected (version 0x{ver:02X})")

    def read_reg(self, addr, block=0):
        """Read single byte from register"""
        ctrl = (block << 3) | 0x00  # Read
        self.cs.value(0)
        self.spi.write(bytes([(addr >> 8) & 0xFF, addr & 0xFF, ctrl]))
        data = self.spi.read(1)
        self.cs.value(1)
        return data[0]

    def write_reg(self, addr, val, block=0):
        """Write single byte to register"""
        ctrl = (block << 3) | 0x04  # Write
        self.cs.value(0)
        self.spi.write(bytes([(addr >> 8) & 0xFF, addr & 0xFF, ctrl, val]))
        self.cs.value(1)

    def read_bytes(self, addr, length, block=0):
        """Read multiple bytes"""
        ctrl = (block << 3) | 0x00
        self.cs.value(0)
        self.spi.write(bytes([(addr >> 8) & 0xFF, addr & 0xFF, ctrl]))
        data = self.spi.read(length)
        self.cs.value(1)
        return data

    def write_bytes(self, addr, data, block=0):
        """Write multiple bytes"""
        ctrl = (block << 3) | 0x04
        self.cs.value(0)
        self.spi.write(bytes([(addr >> 8) & 0xFF, addr & 0xFF, ctrl]) + bytes(data))
        self.cs.value(1)

    def read_reg16(self, addr, block=0):
        """Read 16-bit register"""
        data = self.read_bytes(addr, 2, block)
        return (data[0] << 8) | data[1]

    def write_reg16(self, addr, val, block=0):
        """Write 16-bit register"""
        self.write_bytes(addr, [(val >> 8) & 0xFF, val & 0xFF], block)

    def socket_block(self, sock):
        """Get block number for socket registers"""
        return (sock << 2) + 1

    def tx_block(self, sock):
        """Get block number for TX buffer"""
        return (sock << 2) + 2

    def rx_block(self, sock):
        """Get block number for RX buffer"""
        return (sock << 2) + 3

    def set_mac(self, mac):
        """Set MAC address (6 bytes)"""
        self.write_bytes(self.SHAR, mac)

    def set_ip(self, ip):
        """Set IP address (4 bytes)"""
        self.write_bytes(self.SIPR, ip)

    def set_gateway(self, gw):
        """Set gateway (4 bytes)"""
        self.write_bytes(self.GAR, gw)

    def set_subnet(self, sn):
        """Set subnet mask (4 bytes)"""
        self.write_bytes(self.SUBR, sn)

    def get_ip(self):
        """Get current IP address"""
        return list(self.read_bytes(self.SIPR, 4))

    def get_link_status(self):
        """Check if Ethernet link is up"""
        return (self.read_reg(self.PHYCFGR) & 0x01) == 0x01

    def socket_open(self, sock, port, mode=0x01):
        """Open socket in TCP mode"""
        block = self.socket_block(sock)
        # Set mode
        self.write_reg(self.Sn_MR, mode, block)
        # Set port
        self.write_reg16(self.Sn_PORT, port, block)
        # Open command
        self.write_reg(self.Sn_CR, self.SOCK_OPEN, block)
        while self.read_reg(self.Sn_CR, block) != 0:
            pass
        return self.read_reg(self.Sn_SR, block) == self.SOCK_INIT

    def socket_listen(self, sock):
        """Listen on socket"""
        block = self.socket_block(sock)
        self.write_reg(self.Sn_CR, self.SOCK_LISTEN, block)
        while self.read_reg(self.Sn_CR, block) != 0:
            pass
        return self.read_reg(self.Sn_SR, block) == self.SOCK_LISTEN_STATUS

    def socket_status(self, sock):
        """Get socket status"""
        return self.read_reg(self.Sn_SR, self.socket_block(sock))

    def socket_close(self, sock):
        """Close socket"""
        block = self.socket_block(sock)
        self.write_reg(self.Sn_CR, self.SOCK_CLOSE, block)
        while self.read_reg(self.Sn_CR, block) != 0:
            pass

    def socket_disconnect(self, sock):
        """Disconnect socket"""
        block = self.socket_block(sock)
        self.write_reg(self.Sn_CR, self.SOCK_DISCON, block)
        while self.read_reg(self.Sn_CR, block) != 0:
            pass

    def socket_recv_available(self, sock):
        """Get number of bytes available to receive"""
        return self.read_reg16(self.Sn_RX_RSR, self.socket_block(sock))

    def socket_recv(self, sock, length=None):
        """Receive data from socket"""
        block = self.socket_block(sock)
        avail = self.socket_recv_available(sock)
        if avail == 0:
            return b''
        if length is None or length > avail:
            length = avail

        # Get read pointer
        ptr = self.read_reg16(self.Sn_RX_RD, block)

        # Read data from RX buffer
        data = self.read_bytes(ptr & 0xFFFF, length, self.rx_block(sock))

        # Update read pointer
        ptr += length
        self.write_reg16(self.Sn_RX_RD, ptr, block)

        # Recv command
        self.write_reg(self.Sn_CR, self.SOCK_RECV, block)
        while self.read_reg(self.Sn_CR, block) != 0:
            pass

        return bytes(data)

    def socket_send(self, sock, data):
        """Send data through socket (handles large data by chunking)"""
        block = self.socket_block(sock)
        total = len(data)
        sent = 0

        while sent < total:
            # Get available TX buffer space
            free = self.read_reg16(self.Sn_TX_FSR, block)
            if free == 0:
                time.sleep_ms(1)
                continue

            # Send chunk (max 1024 bytes at a time for safety)
            chunk_size = min(total - sent, free, 1024)
            chunk = data[sent:sent + chunk_size]

            # Get write pointer
            ptr = self.read_reg16(self.Sn_TX_WR, block)

            # Write chunk to TX buffer
            self.write_bytes(ptr & 0xFFFF, chunk, self.tx_block(sock))

            # Update write pointer
            ptr += chunk_size
            self.write_reg16(self.Sn_TX_WR, ptr, block)

            # Send command
            self.write_reg(self.Sn_CR, self.SOCK_SEND, block)
            while self.read_reg(self.Sn_CR, block) != 0:
                pass

            sent += chunk_size

        return total

    def socket_tx_pending(self, sock):
        """Check if TX data is still pending (not yet sent)"""
        block = self.socket_block(sock)
        # Check SEND_OK interrupt bit (0x10)
        ir = self.read_reg(self.Sn_IR, block)
        if ir & 0x10:  # SEND_OK
            # Clear the flag
            self.write_reg(self.Sn_IR, 0x10, block)
            return False  # No pending data
        return True  # Data still pending

    def socket_wait_send_complete(self, sock, timeout_ms=2000):
        """Wait until all TX data is sent"""
        block = self.socket_block(sock)
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            ir = self.read_reg(self.Sn_IR, block)
            if ir & 0x10:  # SEND_OK
                self.write_reg(self.Sn_IR, 0x10, block)  # Clear flag
                return True
            if ir & 0x08:  # TIMEOUT
                self.write_reg(self.Sn_IR, 0x08, block)  # Clear flag
                return False
            time.sleep_ms(10)
        return False
