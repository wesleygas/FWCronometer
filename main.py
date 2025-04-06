from machine import Pin, UART, I2C
import time
import micropython
from sensing import TimedSensor, DualPoint
import ustruct as us

micropython.alloc_emergency_exception_buf(100)

# Changed UART pins for Pico (UART0: TX=GP0, RX=GP1)
uart = UART(0, 115200, tx=Pin(0), rx=Pin(1))  

# Changed LED pin for Pico's onboard LED (GP25)
led = Pin(25, Pin.OUT)  # Pico's built-in LED (no need for Signal with invert)

# Remapped GPIO pins for probes - using GP2-GP5 as an example
probes = [TimedSensor(2), TimedSensor(3), TimedSensor(4), TimedSensor(5)]

dps = [DualPoint() for _ in range(len(probes)//2)]

# Changed I2C pins for Pico (default I2C0: SDA=GP8, SCL=GP9)
# i2c = I2C(0, sda=Pin(8), scl=Pin(9))

END_PACKET_DELIMITER = b"akb"

uart_buffer = b""
cmd = b''

def send_uart(data):
    uart.write(data+b'akb')
    
def process_command(cmd):
#     print(cmd)
    led.toggle()
    if(cmd[0] == ord('r')):  # Reset average mode
        id = us.unpack('<B', cmd[1:])[0]
        dps[id].reset()
        send_uart(b'OK')
    elif(cmd[0] == ord('A')):
        id = us.unpack('<B', cmd[1:])[0]        
        tout = b'A' + us.pack('<BL', id, dps[id].get_trip_time())
        send_uart(tout)
    elif(cmd[0] == ord('R')):
        probe_id = us.unpack('<B', cmd[1:])[0]
        probes[probe_id].reset()
        print(f"Reset PID {probe_id}") 
    elif(cmd[0] == ord('U')):
#         print("probe update request")
        probe_id = us.unpack('<B', cmd[1:])[0]
        ptime = probes[probe_id].get_pulse_time()
        tout = b'U' + us.pack('<BL', probe_id, ptime)
#         print(f"Sending time: {ptime} for probe {probe_id} | Started {probes[probe_id].last_set} -> ended {probes[probe_id].last_release}")
        send_uart(tout)
    elif(cmd[0] == ord('C')):
        # Config mode
        if(cmd[1] == ord('A')):
            # Config absolute mode
            id, A_probe, B_probe = us.unpack('<BBB', cmd[2:])
            dps[id].set_probes(probes[A_probe], probes[B_probe])
            # print(f"Configuring probe {A_probe} as A and {B_probe} as B")
            send_uart(b'OK')
        elif(cmd[1] == ord('I')):  # Restore average probes
            id = us.unpack('<B', cmd[2:])
            dps[id].restore_probes()
            send_uart(b'OK')
    elif cmd:
        print("unknown command:", cmd)

def handle_uart():
    global uart_buffer, cmd
    if(uart.any()):
        data = uart.read()
        uart_buffer +=data
        while END_PACKET_DELIMITER in uart_buffer:
            cmd, uart_buffer = uart_buffer.split(END_PACKET_DELIMITER, 1)
            process_command(cmd)
            
def main():
    while 1:
        handle_uart()

main()


