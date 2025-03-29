from machine import Pin, Signal, UART, I2C
import time
import micropython
from sensing import TimedSensor, DualPoint
import ustruct as us

micropython.alloc_emergency_exception_buf(100)

uart = UART(1, 115200, tx=17, rx=16)  # init with given baudrate

led = Signal(Pin(2, Pin.OUT), invert=True) 

ts = TimedSensor(18)
ts1 = TimedSensor(19)

dp = DualPoint()

probes = [ts, ts1]

A_probe = 0
B_probe = 1

i2c = I2C(sda=Pin(22), scl=Pin(21))

END_PACKET_DELIMITER = b"akb"

uart_buffer = b""

cmd = b''

def send_uart(data):
    uart.write(data+b'akb')
    
def calc_average_mode():
    if(dp.start_triggered()):
        return dp.get_trip_time()
    else:
        return 0
    
def process_command(cmd):
#     print(cmd)
    if(cmd[0] == ord('P')):
        print("received P command")
    elif(cmd[0] == ord('A')):
        tout = b'A' + us.pack('<L', calc_average_mode())
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
            A_probe, B_probe = us.unpack('<BB', cmd[2:])
            dp.set_probes(probes[A_probe], probes[B_probe])
#             for probe in probes:
#                 probe.reset()
#             print(f"Configuring probe {A_probe} as A and {B_probe} as B")
            send_uart(b'OK')
        elif(cmd[1] == ord('I')):
            dp.restore_probes()
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
    

