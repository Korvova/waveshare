"""
PZEM-004T Test Script for PC
Run: python pzem_pc_test.py COM7
(replace COM7 with your USB-TTL port)
"""
import serial
import time
import sys

def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def read_pzem(port):
    print(f"Opening {port} at 9600 baud...")

    try:
        ser = serial.Serial(port, 9600, timeout=1)
        print("Port opened!")
    except Exception as e:
        print(f"Error opening port: {e}")
        return

    time.sleep(0.5)

    # Clear buffer
    ser.reset_input_buffer()

    # Try addresses 0x01 and 0xF8 (broadcast)
    for addr in [0x01, 0xF8]:
        print(f"\nTrying address 0x{addr:02X}...")

        # Build command: Read Input Registers (0x04), start 0x0000, count 10
        cmd = bytes([addr, 0x04, 0x00, 0x00, 0x00, 0x0A])
        crc = crc16(cmd)
        cmd = cmd + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        print(f"Sending: {cmd.hex()}")
        ser.write(cmd)

        time.sleep(0.5)

        if ser.in_waiting > 0:
            resp = ser.read(ser.in_waiting)
            print(f"Response ({len(resp)} bytes): {resp.hex()}")

            if len(resp) >= 25:
                # Parse PZEM data
                voltage = (resp[3] << 8 | resp[4]) / 10.0
                current = (resp[5] << 8 | resp[6] | resp[7] << 24 | resp[8] << 16) / 1000.0
                power = (resp[9] << 8 | resp[10] | resp[11] << 24 | resp[12] << 16) / 10.0
                energy = (resp[13] << 8 | resp[14] | resp[15] << 24 | resp[16] << 16)
                freq = (resp[17] << 8 | resp[18]) / 10.0
                pf = (resp[19] << 8 | resp[20]) / 100.0

                print(f"\n{'='*30}")
                print(f"PZEM-004T Data")
                print(f"{'='*30}")
                print(f"Voltage:      {voltage:.1f} V")
                print(f"Current:      {current:.3f} A")
                print(f"Power:        {power:.1f} W")
                print(f"Energy:       {energy} Wh")
                print(f"Frequency:    {freq:.1f} Hz")
                print(f"Power Factor: {pf:.2f}")
                print(f"{'='*30}")
                ser.close()
                return True
        else:
            print("No response")

    ser.close()
    print("\nPZEM not responding!")
    print("Check:")
    print("1. Wiring: PZEM TX -> USB-TTL RX, PZEM RX -> USB-TTL TX")
    print("2. Power: 5V and GND connected")
    print("3. AC: PZEM connected to 220V")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # List available ports
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        print("Available COM ports:")
        for p in ports:
            print(f"  {p.device} - {p.description}")
        print("\nUsage: python pzem_pc_test.py COMx")
    else:
        read_pzem(sys.argv[1])
